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
from .models import JobReport, Scope, now
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

    def list_public(self) -> List[Document]:
        """Legacy public API remains limited to documents without verified ownership."""
        return [doc for doc in self.list() if doc.owner_user_id is None]

    def get(self, doc_id: str) -> Document:
        doc = self._docs.get(doc_id)
        if doc is None:
            raise _not_found("Document")
        return doc

    def get_public(self, doc_id: str) -> Document:
        doc = self.get(doc_id)
        if doc.owner_user_id is not None:
            raise _not_found("Document")
        return doc

    def versions(self, doc_id: str) -> List[VersionSummary]:
        """All versions, newest first, without their text."""
        self.get(doc_id)
        return [
            VersionSummary.model_validate(
                v.model_dump(exclude={
                    "content",
                    "sections",
                    "skipped",
                    "sections_match_content",
                    "evidence_report",
                })
            )
            for v in reversed(self._versions[doc_id])
        ]

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

    def review_comparison(self, doc_id: str):
        """Compare the pending version with the latest approved version."""
        import difflib

        doc = self.get(doc_id)

        if doc.pending_version is None:
            raise VersionError(409, "No document version is awaiting review")

        pending = self.version(doc_id, doc.pending_version)

        approved = (
            self.version(doc_id, doc.current_version)
            if doc.current_version > 0
            else None
        )

        diff = ""
        if approved is not None:
            diff = "".join(
                difflib.unified_diff(
                    approved.content.splitlines(keepends=True),
                    pending.content.splitlines(keepends=True),
                    fromfile=f"approved-v{approved.number}",
                    tofile=f"pending-v{pending.number}",
                )
            )

        return {
            "pending_version": pending,
            "approved_version": approved,
            "has_approved_version": approved is not None,
            "diff": diff,
            "changes": pending.changes,
        }
    # ---------- internal helpers ----------

    def _event(self, doc_id: str, action: HistoryAction, version: int, actor: Optional[str] = None,
               note: Optional[str] = None, related: Optional[int] = None) -> None:
        self._events[doc_id].append(HistoryEvent(action=action, version=version, actor=actor,
                                                 note=note, related_version=related))

    # ---------- create ----------

    def create_from_job(self, job_id: str, output: JobOutput, title: Optional[str] = None,
                        actor: Optional[str] = None, note: Optional[str] = None,
                        owner_user_id: Optional[str] = None,report: Optional[JobReport] = None) -> Document:
        with self._lock:
            if owner_user_id is not None:
                for existing in self._docs.values():
                    if existing.source_job_id == job_id and existing.owner_user_id == owner_user_id:
                        return existing
                    if existing.source_job_id == job_id and existing.owner_user_id not in (None, owner_user_id):
                        raise VersionError(409, "This generation job is already linked to another owner")
            doc = Document(id=uuid.uuid4().hex, title=title or output.target, target=output.target,
                           scope=output.scope, template_id=output.template_id,
                           output_language=output.output_language, source_job_id=job_id,
                           owner_user_id=owner_user_id,
                           current_version=0 if owner_user_id is not None else 1,
                           pending_version=1 if owner_user_id is not None else None)
            sections = [FileSection(path=p, markdown=md, status=st, confidence=c)
                        for p, md, st, c in output.sections]
            skipped = [SkippedFile(path=p, reason=r) for p, r in output.skipped]
            v = DocumentVersion(number=1,
                                status=VersionStatus.proposed if owner_user_id is not None else VersionStatus.accepted,
                                origin=VersionOrigin.generated,
                                content=assemble(doc, sections, skipped, output.template_name),
                                                                sections=sections, skipped=skipped, confidence=output.confidence,
                                review_report=report,
                                evidence_report=output.evidence_report,
                                changes=[SectionChange(path=s.path, action=SectionAction.added)
                                         for s in sections],
                                note=note, created_by=actor,
                                source_snapshot=output.source_snapshot,
                                decided_by=None if owner_user_id is not None else actor,
                                decided_at=None if owner_user_id is not None else now())
            self._docs[doc.id] = doc
            self._versions[doc.id] = [v]
            self._events[doc.id] = []
            self._plans[doc.id] = {}
            self._event(doc.id, HistoryAction.created, 1, actor, note or f"From job {job_id}")
            self._save()
            return doc

    def get_owned(self, doc_id: str, owner_user_id: str) -> Document:
        with self._lock:
            doc = self.get(doc_id)
            if doc.owner_user_id is None or doc.owner_user_id != owner_user_id:
                raise _not_found("Document")
            return doc

    def edit_owned(self, doc_id: str, owner_user_id: str, expected_version: int, content: str,
                   note: Optional[str] = None) -> DocumentVersion:
        with self._lock:
            doc = self.get_owned(doc_id, owner_user_id)
            if doc.pending_version is not None:
                if doc.pending_version != expected_version:
                    raise VersionError(409, "The submitted document version has changed")
                base = self.version(doc_id, doc.pending_version)
            else:
                if doc.current_version != expected_version:
                    raise VersionError(409, "The submitted document version has changed")
                base = self.version(doc_id, doc.current_version)
            number = len(self._versions[doc_id]) + 1
            if doc.pending_version is not None:
                base.status = VersionStatus.superseded
                base.superseded_by = number
                self._event(doc_id, HistoryAction.superseded, base.number, owner_user_id,
                            "Replaced after another changes request", related=number)
            version = DocumentVersion(
                number=number,
                status=VersionStatus.proposed,
                origin=VersionOrigin.edit,
                base_version=doc.current_version,
                content=content,
                sections=list(base.sections),
                skipped=list(base.skipped),
                sections_match_content=False,
                manual=True,
                note=note,
                created_by=owner_user_id,
            )
            self._versions[doc_id].append(version)
            doc.pending_version = number
            doc.versions_total = number
            doc.updated_at = now()
            self._event(doc_id, HistoryAction.proposed, number, owner_user_id, note or "Owner edited after changes requested")
            self._save()
            return version
    def rollback_owned(
        self,
        doc_id: str,
        owner_user_id: str,
        source_version_number: int,
        actor_user_id: str,
        note: Optional[str] = None,
    ) -> DocumentVersion:
        with self._lock:
            doc = self.get_owned(doc_id, owner_user_id)

            # Allow safe retry if the previous request already created
            # the same rollback proposal.
            if doc.pending_version is not None:
                pending = self.version(doc_id, doc.pending_version)

                if (
                    pending.origin == VersionOrigin.rollback
                    and pending.restored_from == source_version_number
                    and pending.created_by == actor_user_id
                    and pending.note == note
                ):
                    return pending

                raise VersionError(
                    409,
                    "A document version is already awaiting review",
                )

            source = self.version(doc_id, source_version_number)

            if source.status != VersionStatus.accepted:
                raise VersionError(
                    409,
                    "Only an accepted document version can be restored",
                )

            number = len(self._versions[doc_id]) + 1

            version = DocumentVersion(
                number=number,
                status=VersionStatus.proposed,
                origin=VersionOrigin.rollback,
                base_version=doc.current_version,
                restored_from=source.number,
                content=source.content,
                sections=[
                    section.model_copy(deep=True)
                    for section in source.sections
                ],
                skipped=[
                    item.model_copy(deep=True)
                    for item in source.skipped
                ],
                changes=[],
                source_changes=[
                    item.model_copy(deep=True)
                    for item in source.source_changes
                ],
                warnings=list(source.warnings),
                confidence=source.confidence,
                manual=source.manual,
                note=note,
                created_by=actor_user_id,
                evidence_report=(
                    source.evidence_report.model_copy(deep=True)
                    if source.evidence_report is not None
                    else None
                ),
                sections_match_content=source.sections_match_content,
            )

            self._versions[doc_id].append(version)
            doc.pending_version = number
            doc.versions_total = number
            doc.updated_at = now()

            self._event(
                doc_id,
                HistoryAction.rolled_back,
                number,
                actor_user_id,
                note or f"Restored from version {source.number}",
                related=source.number,
            )

            self._save()
            return version
    def resolve_workflow_version(self, doc_id: str, owner_user_id: str, version_number: int,
                                 decision: str, actor_user_id: str,
                                 note: Optional[str] = None) -> None:
        with self._lock:
            doc = self.get_owned(doc_id, owner_user_id)
            if doc.pending_version is None:
                version = self.version(doc_id, version_number)
                if decision == "APPROVED" and doc.current_version == version_number \
                        and version.status == VersionStatus.accepted:
                    return  # Idempotent retry after the workflow transaction committed remotely first.
                if decision == "REJECTED" and version.status == VersionStatus.dismissed:
                    return
                raise VersionError(409, "No matching proposed version is awaiting a decision")
            if doc.pending_version != version_number:
                raise VersionError(409, "The pending document version has changed")
            version = self.version(doc_id, version_number)
            if decision == "APPROVED":
                version.status = VersionStatus.accepted
                doc.current_version = version_number
                action = HistoryAction.accepted
            elif decision == "REJECTED":
                version.status = VersionStatus.dismissed
                action = HistoryAction.dismissed
            else:
                raise VersionError(400, "Unknown review decision")
            version.decided_by = actor_user_id
            version.decided_at = now()
            version.note = note or version.note
            doc.pending_version = None
            doc.updated_at = now()
            self._event(doc_id, action, version_number, actor_user_id, note)
            self._save()


documents = DocumentStore(os.getenv("DOCUMENTS_FILE", DEFAULT_FILE) or None)



