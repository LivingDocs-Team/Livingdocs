"""Versioned documentation produced by the AI service.

- LD-195  version management: save a job as a document, immutable versions, audit trail

Documents are saved to a JSON file (DOCUMENTS_FILE, default data/documents.json, written
atomically) so they survive a restart. Set DOCUMENTS_FILE= (empty) to keep them in memory only.
"""
import json
import logging
import os
import pathlib
import threading
import uuid
from typing import Dict, List, Optional

from .generator import DocGenerator
from .jobs import JobOutput
from .models import Scope, now
from .renderer import render_overview
from .version_models import (Document, DocumentVersion, FileSection, HistoryAction, HistoryEvent,
                             SectionAction, SectionChange, SkippedFile, VersionOrigin,
                             VersionStatus, VersionSummary)

log = logging.getLogger(__name__)
DEFAULT_FILE = "data/documents.json"
SEPARATOR = "\n\n---\n\n"


class VersionError(Exception):
    """An operation that cannot be done. `status` is the HTTP status to return."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _not_found(what: str) -> VersionError:
    return VersionError(404, f"{what} not found")


# ---------- Text helpers ----------

def _mean(values: List[Optional[float]]) -> Optional[float]:
    xs = [v for v in values if v is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def assemble(doc: Document, sections: List[FileSection], skipped: List[SkippedFile],
             template_name: Optional[str]) -> str:
    """Same layout as a generation job (FR-AI-01.11): one file alone, or overview + files."""
    if doc.scope == Scope.file and len(sections) == 1 and not skipped:
        return sections[0].markdown
    overview = render_overview(doc.target, [(s.path, s.status, s.confidence) for s in sections],
                               [(s.path, s.reason) for s in skipped], doc.output_language,
                               _mean([s.confidence for s in sections]),
                               template_name=template_name)
    return SEPARATOR.join([overview, *[s.markdown for s in sections]])


# ---------- Store ----------

class DocumentStore:
    def __init__(self, path: Optional[str] = None,
                 generator: Optional[DocGenerator] = None) -> None:
        self._lock = threading.RLock()
        self.path = pathlib.Path(path) if path else None
        self.generator = generator          # tests inject one; None = get_generator() per call
        self._docs: Dict[str, Document] = {}
        self._versions: Dict[str, List[DocumentVersion]] = {}
        self._events: Dict[str, List[HistoryEvent]] = {}
        # inputs needed to rebuild a proposal (regenerate, rebase):
        # doc id -> version number -> {"accepted_base": int, "steps": [step, ...]}
        self._plans: Dict[str, Dict[int, dict]] = {}
        self._load()

    # ---------- persistence ----------

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            docs = {d["id"]: Document.model_validate(d) for d in raw.get("documents", [])}
            versions = {k: [DocumentVersion.model_validate(v) for v in vs]
                        for k, vs in raw.get("versions", {}).items()}
            events = {k: [HistoryEvent.model_validate(e) for e in es]
                      for k, es in raw.get("events", {}).items()}
            plans = {k: {int(n): p for n, p in ps.items()} for k, ps in raw.get("plans", {}).items()}
        except Exception as exc:  # corrupt file: keep it for inspection, start clean
            backup = self.path.with_suffix(f".corrupt-{now():%Y%m%d%H%M%S}.json")
            self.path.rename(backup)
            log.error("Could not read %s (%s); moved it to %s", self.path, exc, backup.name)
            return
        self._docs, self._versions, self._events, self._plans = docs, versions, events, plans

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "documents": [d.model_dump(mode="json") for d in self._docs.values()],
            "versions": {k: [v.model_dump(mode="json") for v in vs] for k, vs in self._versions.items()},
            "events": {k: [e.model_dump(mode="json") for e in es] for k, es in self._events.items()},
            "plans": {k: {str(n): p for n, p in ps.items()} for k, ps in self._plans.items()},
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: a crash never leaves a half-written file

    # ---------- queries (LD-195) ----------

    def list(self) -> List[Document]:
        return sorted(self._docs.values(), key=lambda d: d.updated_at, reverse=True)

    def get(self, doc_id: str) -> Document:
        doc = self._docs.get(doc_id)
        if doc is None:
            raise _not_found("Document")
        return doc

    def versions(self, doc_id: str) -> List[VersionSummary]:
        """All versions, newest first, without their text."""
        self.get(doc_id)
        return [VersionSummary.model_validate(v.model_dump(exclude={"content", "sections", "skipped",
                                                                    "sections_match_content"}))
                for v in reversed(self._versions[doc_id])]

    def version(self, doc_id: str, number: Optional[int] = None) -> DocumentVersion:
        doc = self.get(doc_id)
        n = doc.current_version if number is None else number
        vs = self._versions[doc_id]
        if not 1 <= n <= len(vs):
            raise _not_found(f"Version {n}")
        return vs[n - 1]

    def history(self, doc_id: str) -> List[HistoryEvent]:
        """Audit trail, oldest first."""
        self.get(doc_id)
        return list(self._events[doc_id])

    # ---------- internal helpers ----------

    def _event(self, doc_id: str, action: HistoryAction, version: int, actor: Optional[str] = None,
               note: Optional[str] = None, related: Optional[int] = None) -> None:
        self._events[doc_id].append(HistoryEvent(action=action, version=version, actor=actor,
                                                 note=note, related_version=related))

    # ---------- create ----------

    def create_from_job(self, job_id: str, output: JobOutput, title: Optional[str] = None,
                        actor: Optional[str] = None, note: Optional[str] = None) -> Document:
        with self._lock:
            doc = Document(id=uuid.uuid4().hex, title=title or output.target, target=output.target,
                           scope=output.scope, template_id=output.template_id,
                           output_language=output.output_language, source_job_id=job_id)
            sections = [FileSection(path=p, markdown=md, status=st, confidence=c)
                        for p, md, st, c in output.sections]
            skipped = [SkippedFile(path=p, reason=r) for p, r in output.skipped]
            v = DocumentVersion(number=1, status=VersionStatus.accepted,
                                origin=VersionOrigin.generated,
                                content=assemble(doc, sections, skipped, output.template_name),
                                sections=sections, skipped=skipped, confidence=output.confidence,
                                changes=[SectionChange(path=s.path, action=SectionAction.added)
                                         for s in sections],
                                note=note, created_by=actor, decided_by=actor, decided_at=now())
            self._docs[doc.id] = doc
            self._versions[doc.id] = [v]
            self._events[doc.id] = []
            self._plans[doc.id] = {}
            self._event(doc.id, HistoryAction.created, 1, actor, note or f"From job {job_id}")
            self._save()
            return doc


documents = DocumentStore(os.getenv("DOCUMENTS_FILE", DEFAULT_FILE) or None)
