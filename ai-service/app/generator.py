"""Documentation generation from analyzed source code (LD-340).

Flow for one file:
  analysis --prompt--> AI --JSON--> validate (FileDoc) --> render Markdown

Failure handling:
  - AI call raises (network, rate limit, timeout)  -> retry with backoff
  - AI returns invalid JSON / wrong shape          -> retry with a repair prompt
  - still failing after all attempts               -> fallback: render from analysis
                                                      data only (docstrings), status=fallback
Without ANTHROPIC_API_KEY the generator runs in offline mode (no AI).
"""
import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from .doc_schema import FileDoc, InvalidAIOutput, parse_file_doc
from .models import FileAnalysis, FileResultStatus, Template
from .prompts import SYSTEM_PROMPT, build_file_prompt, build_repair_prompt
from .renderer import missing_entities, render_file, unknown_entities

log = logging.getLogger(__name__)


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


class DocGenerator:
    def __init__(self, client: Optional[LLMClient] = None,
                 max_attempts: int = 3, backoff_seconds: float = 1.0) -> None:
        self.client = client
        self.max_attempts = max(1, max_attempts)
        self.backoff_seconds = backoff_seconds

    @property
    def mode(self) -> str:
        return "ai" if self.client else "offline"

    def document_file(self, f: FileAnalysis, tpl: Template, lang: str) -> FileDocResult:
        if self.client is None:
            return FileDocResult(render_file(f, FileDoc(), tpl, lang), FileResultStatus.offline)

        if f.entity_count() == 0:
            # nothing for the AI to describe; avoid a pointless call
            return FileDocResult(render_file(f, FileDoc(), tpl, lang), FileResultStatus.generated)

        warnings: List[str] = []
        doc = self._ask_with_retries(f, tpl, lang, warnings)
        if doc is None:
            warnings.append(
                f"{f.path}: AI did not return a valid result after {self.max_attempts} "
                "attempt(s); documentation was built from analysis data only."
            )
            return FileDocResult(render_file(f, FileDoc(), tpl, lang),
                                 FileResultStatus.fallback, warnings)

        missing = missing_entities(f, doc)
        if missing:
            warnings.append(f"{f.path}: AI gave no description for {', '.join(missing)}.")
        extra = unknown_entities(f, doc)
        if extra:
            warnings.append(f"{f.path}: ignored entities not in the analysis: {', '.join(extra)}.")
        return FileDocResult(render_file(f, doc, tpl, lang), FileResultStatus.generated, warnings)

    def _ask_with_retries(self, f: FileAnalysis, tpl: Template, lang: str,
                          warnings: List[str]) -> Optional[FileDoc]:
        messages = [{"role": "user", "content": build_file_prompt(f, tpl, lang)}]
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
