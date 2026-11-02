"""Documentation generation from analyzed source code (LD-340).

Flow for one file:
  analysis --prompt--> AI --JSON--> validate (FileDoc) --> render Markdown

Failure handling:
  - AI call raises (network, rate limit, timeout)  -> retry with backoff
  - AI returns invalid JSON / wrong shape          -> retry with a repair prompt
  - still failing after all attempts               -> fallback: render from analysis
                                                      data only (docstrings), status=fallback
Each file also gets an evidence catalog (its own code + retrieved related code and
documentation, see retrieval.py / evidence.py) and a confidence score per entity
(confidence.py). Without ANTHROPIC_API_KEY the generator runs in offline mode (no AI).
"""
import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from .doc_schema import FileDoc, InvalidAIOutput, parse_file_doc
from .confidence import average, level_of, score_entity
from .evidence import EvidenceCatalog, build_catalog, entities
from .models import SECTION_KINDS, FileAnalysis, FileReport, FileResultStatus, Template
from .prompts import SYSTEM_PROMPT, build_file_prompt, build_repair_prompt
from .renderer import doc_items, missing_entities, render_file, unknown_entities
from .retrieval import Retrieved

log = logging.getLogger(__name__)


def template_entities(f: FileAnalysis, tpl: Template):
    """Entities of the file that the template's sections document (others are not rendered)."""
    kinds = set().union(*(SECTION_KINDS.get(s, set()) for s in tpl.sections))
    return [e for e in entities(f) if e.kind in kinds]


class LLMClient(Protocol):
    def complete(self, system: str, messages: List[dict]) -> str: ...


class AnthropicClient:
    def __init__(self) -> None:
        import anthropic  # imported lazily so offline mode needs no package

        self.client = anthropic.Anthropic(
            timeout=float(os.getenv("LLM_TIMEOUT", "60")),
            max_retries=0,  # retries are handled by DocGenerator
        )
        self.model = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    def complete(self, system: str, messages: List[dict]) -> str:
        msg = self.client.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            system=system, messages=messages,
        )
        return "".join(b.text for b in msg.content if b.type == "text")


@dataclass
class FileDocResult:
    markdown: str
    status: FileResultStatus
    warnings: List[str] = field(default_factory=list)
    report: Optional[FileReport] = None

    @property
    def confidence(self) -> Optional[float]:
        return self.report.confidence if self.report else None


class DocGenerator:
    def __init__(self, client: Optional[LLMClient] = None,
                 max_attempts: int = 3, backoff_seconds: float = 1.0) -> None:
        self.client = client
        self.max_attempts = max(1, max_attempts)
        self.backoff_seconds = backoff_seconds

    @property
    def mode(self) -> str:
        return "ai" if self.client else "offline"

    def document_file(self, f: FileAnalysis, tpl: Template, lang: str,
                      retrieved: Optional[Retrieved] = None) -> FileDocResult:
        catalog = build_catalog(f, retrieved)
        if self.client is None:
            return self._finish(f, FileDoc(), False, FileResultStatus.offline, catalog, tpl, lang, [])

        if f.entity_count() == 0:
            # nothing for the AI to describe; avoid a pointless call
            return self._finish(f, FileDoc(), True, FileResultStatus.generated, catalog, tpl, lang, [])

        warnings: List[str] = []
        doc = self._ask_with_retries(f, tpl, lang, catalog, warnings)
        if doc is None:
            warnings.append(
                f"{f.path}: AI did not return a valid result after {self.max_attempts} "
                "attempt(s); documentation was built from analysis data only."
            )
            return self._finish(f, FileDoc(), False, FileResultStatus.fallback, catalog, tpl, lang,
                                warnings)

        in_tpl = {e.key for e in template_entities(f, tpl)}
        missing = [m for m in missing_entities(f, doc) if m in in_tpl]
        if missing:
            warnings.append(f"{f.path}: AI gave no description for {', '.join(missing)}.")
        extra = unknown_entities(f, doc)
        if extra:
            warnings.append(f"{f.path}: ignored entities not in the analysis: {', '.join(extra)}.")
        return self._finish(f, doc, True, FileResultStatus.generated, catalog, tpl, lang, warnings)

    def _finish(self, f: FileAnalysis, doc: FileDoc, ai_mode: bool, status: FileResultStatus,
                catalog: EvidenceCatalog, tpl: Template, lang: str,
                warnings: List[str]) -> FileDocResult:
        """Score every entity, attach evidence, render Markdown."""
        items = doc_items(doc)
        reports = [score_entity(ent, items.get(ent.key), catalog, ai_mode)
                   for ent in template_entities(f, tpl)]
        by_key = {r.name: r for r in reports}

        cited_ids: List[str] = list(doc.overview_evidence)
        for item in items.values():
            cited_ids += item.evidence
        found, unknown = catalog.resolve(cited_ids)
        if unknown:
            warnings.append(f"{f.path}: ignored citations not in the evidence catalog: "
                            f"{', '.join(sorted(set(unknown)))}.")
        context_used = [e for e in found if e.kind.value != "source"]

        file_conf = average([r.confidence for r in reports])
        report = FileReport(path=f.path, status=status, confidence=file_conf,
                            level=level_of(file_conf), entities=reports, context_used=context_used)
        md = render_file(f, doc, tpl, lang, by_key, file_conf, context_used)
        return FileDocResult(md, status, warnings, report)

    def _ask_with_retries(self, f: FileAnalysis, tpl: Template, lang: str,
                          catalog: EvidenceCatalog, warnings: List[str]) -> Optional[FileDoc]:
        messages = [{"role": "user", "content": build_file_prompt(f, tpl, lang, catalog)}]
        for attempt in range(1, self.max_attempts + 1):
            try:
                text = self.client.complete(SYSTEM_PROMPT, messages)
            except Exception as exc:  # API / network error
                log.warning("AI call failed for %s (attempt %d): %s", f.path, attempt, exc)
                warnings.append(f"{f.path}: AI call failed (attempt {attempt}): {exc}")
                self._sleep(attempt)
                continue
            try:
                return parse_file_doc(text)
            except InvalidAIOutput as exc:
                log.warning("Invalid AI output for %s (attempt %d): %s", f.path, attempt, exc)
                warnings.append(f"{f.path}: invalid AI output (attempt {attempt}): {exc}")
                messages = messages + [
                    {"role": "assistant", "content": text or "(empty)"},
                    {"role": "user", "content": build_repair_prompt(str(exc))},
                ]
        return None

    def _sleep(self, attempt: int) -> None:
        if attempt < self.max_attempts and self.backoff_seconds > 0:
            time.sleep(self.backoff_seconds * 2 ** (attempt - 1))


def get_generator() -> DocGenerator:
    if os.getenv("ANTHROPIC_API_KEY"):
        return DocGenerator(AnthropicClient(),
                            max_attempts=int(os.getenv("LLM_MAX_ATTEMPTS", "3")))
    return DocGenerator(None)
