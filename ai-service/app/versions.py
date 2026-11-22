"""Versioned documentation produced by the AI service.

- LD-195  version management: save a job as a document, immutable versions, audit trail
- LD-177  documentation change log: actor role, trigger source and status on history events

Documents are saved to a JSON file (DOCUMENTS_FILE, default data/documents.json, written
atomically) so they survive a restart. Set DOCUMENTS_FILE= (empty) to keep them in memory only.

LD-402 evidence persistence: a version made by an owner edit (after a review asked for changes)
or by a rollback keeps the evidence of the version it was made from (`evidence_report` for the
manager, `review_report` + `source_snapshot` for the staff reviewer) and says which one in
`evidence_from_version`. Before, such versions had no evidence, so a resubmitted or restored
document could not be reviewed (404). Files saved before the fix are repaired when loaded.
"""
import json
import logging
import os
import pathlib
import re
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from .generator import DocGenerator
from .jobs import JobOutput
from .doc_diff import diff_texts
from .models import (Evidence, EvidenceKind, FileReport, FileResultStatus, JobReport,
                     Scope, SourceSnapshot, now)
from .renderer import render_overview
from .version_models import (ComparedVersion, Document, DocumentDiff, DocumentVersion, FileSection,
                             HistoryAction, HistoryEvent, PreparedRevision, RevisionDraftRequest,
                             RevisionFileChange, SectionAction, SectionChange, SkippedFile,
                             SourceChangeRef, TriggerSource, VersionOrigin, VersionStatus,
                             VersionSummary)

log = logging.getLogger(__name__)
DEFAULT_FILE = "data/documents.json"
SEPARATOR = "\n\n---\n\n"
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^ {0,3}(#{1,2})[ \t]+(.+?)\s*$")


class VersionError(Exception):
    """An operation that cannot be done. `status` is the HTTP status to return."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _not_found(what: str) -> VersionError:
    return VersionError(404, f"{what} not found")


# ---------- Text helpers ----------

def _template_headings(markdown: str) -> list[tuple[str, str]]:
    headings = []
    fence = None
    for line in markdown.splitlines():
        marker = _FENCE.match(line)
        if fence is not None:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
        else:
            heading = _HEADING.match(line)
            if heading:
                headings.append((heading[1], heading[2]))
    return headings

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


EVIDENCE_FIELDS = ("evidence_report", "review_report", "source_snapshot")


def _has_evidence(v: DocumentVersion) -> bool:
    return any(getattr(v, f) is not None for f in EVIDENCE_FIELDS)


def inherit_evidence(version: DocumentVersion, source: Optional[DocumentVersion]) -> None:
    """LD-402: give `version` the generation evidence of `source` (deep copies), unless it has
    its own. The text of an edit may differ, but the code it documents is the same."""
    if source is None or _has_evidence(version) or not _has_evidence(source):
        return
    for f in EVIDENCE_FIELDS:
        value = getattr(source, f)
        setattr(version, f, value.model_copy(deep=True) if value is not None else None)
    version.revision_files = [item.model_copy(deep=True) for item in source.revision_files]
    version.evidence_from_version = source.evidence_from_version or source.number


def _evidence_source(versions: List[DocumentVersion], v: DocumentVersion) -> Optional[DocumentVersion]:
    """The version an edit / rollback was made from, as recorded in the version history."""
    if v.origin == VersionOrigin.rollback:
        n = v.restored_from
    elif v.origin == VersionOrigin.edit:
        replaced = [x.number for x in versions if x.superseded_by == v.number]
        n = replaced[0] if replaced else v.base_version
    else:
        return None
    return versions[n - 1] if n and 1 <= n < v.number else None


def repair_evidence(versions: List[DocumentVersion]) -> int:
    """Fill the evidence of edits / rollbacks saved before LD-402; returns how many were fixed."""
    fixed = 0
    for v in versions:                                  # oldest first: a chain is fixed in order
        if not _has_evidence(v):
            inherit_evidence(v, _evidence_source(versions, v))
            fixed += _has_evidence(v)
    return fixed


def _side(v: DocumentVersion) -> ComparedVersion:
    return ComparedVersion(number=v.number, status=v.status, origin=v.origin, created_at=v.created_at,
                           created_by=v.created_by, note=v.note)


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
        repaired = sum(repair_evidence(vs) for vs in versions.values())
        if repaired:
            log.info("Restored the evidence of %d edited / rolled back version(s) from %s",
                     repaired, self.path)
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
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as output:
                json.dump(data, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(tmp, self.path)
            if os.name == "posix":
                directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            tmp.unlink(missing_ok=True)

    # ---------- queries (LD-195) ----------

    def count_activity(self, start: datetime, end: datetime) -> tuple[int, int]:
        with self._lock:
            created = sum(start <= doc.created_at < end for doc in self._docs.values())
            audit = sum(start <= event.at < end for events in self._events.values() for event in events)
        return created, audit

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

    def latest_number(self, doc_id: str) -> int:
        """The version people see as "current": the proposal under review, else the accepted one."""
        doc = self.get(doc_id)
        return doc.pending_version or doc.current_version or len(self._versions[doc_id])

    def compare(self, doc_id: str, from_number: Optional[int] = None,
                to_number: Optional[int] = None) -> DocumentDiff:
        """LD-183: difference between any two versions (BR-44). Without numbers the latest version
        is compared with the one before it ("current vs previous")."""
        with self._lock:
            self.get(doc_id)
            total = len(self._versions[doc_id])
            if total < 2 and from_number is None and to_number is None:
                raise VersionError(409, "Create a version first to enable comparison.")
            to_n = to_number if to_number is not None else self.latest_number(doc_id)
            from_n = from_number if from_number is not None else to_n - 1
            if from_n == to_n:
                raise VersionError(400, "Select two different versions to compare.")
            older, newer = self.version(doc_id, from_n), self.version(doc_id, to_n)
            result = diff_texts(older.content, newer.content)
            return DocumentDiff(document_id=doc_id, from_version=_side(older), to_version=_side(newer),
                                **result.model_dump())

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

    def _event(
        self,
        doc_id: str,
        action: HistoryAction,
        version: int,
        actor: Optional[str] = None,
        note: Optional[str] = None,
        related: Optional[int] = None,
        actor_role: Optional[str] = None,
        trigger_source: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        self._events[doc_id].append(
            HistoryEvent(
                action=action,
                version=version,
                actor=actor,
                actor_role=actor_role,
                trigger_source=trigger_source,
                status=status,
                note=note,
                related_version=related,
            )
        )

    # ---------- create ----------

    def create_from_job(
        self,
        job_id: str,
        output: JobOutput,
        title: Optional[str] = None,
        actor: Optional[str] = None,
        note: Optional[str] = None,
        owner_user_id: Optional[str] = None,
        report: Optional[JobReport] = None,
        actor_role: Optional[str] = None,
        trigger_source: Optional[str] = None,
    ) -> Document:
        with self._lock:
            if owner_user_id is not None:
                for existing in self._docs.values():
                    if existing.source_job_id == job_id and existing.owner_user_id == owner_user_id:
                        return existing
                    if existing.source_job_id == job_id and existing.owner_user_id not in (None, owner_user_id):
                        raise VersionError(409, "This generation job is already linked to another owner")
            doc = Document(id=uuid.uuid4().hex, title=title or output.target, target=output.target,
                           scope=output.scope, template_id=output.template_id,
                           template_version=getattr(output, "template_version", None),
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
            self._event(
                doc.id,
                HistoryAction.created,
                1,
                actor,
                note or f"From job {job_id}",
                actor_role=actor_role or ("DEVELOPER" if owner_user_id else ("USER" if actor else "SYSTEM")),
                trigger_source=trigger_source or TriggerSource.ai_generation.value,
                status=v.status.value,
            )
            self._save()
            return doc

    def revision_candidates(self, repository_id: str) -> List[Document]:
        with self._lock:
            return [
                doc.model_copy(deep=True)
                for doc in self._docs.values()
                if doc.owner_user_id and doc.current_version
                and (snapshot := self.version(doc.id).source_snapshot)
                and snapshot.repository_id == repository_id
            ]

    def _revision_base(self, doc_id: str, owner: str, request: RevisionDraftRequest):
        """Called under the store lock, before generation and again before persisting."""
        doc = self.get_owned(doc_id, owner)
        base = self.version(doc_id, request.base_version)
        snapshot = request.source_snapshot
        if (not base.source_snapshot
                or base.source_snapshot.repository_id != snapshot.repository_id
                or base.source_snapshot.repository_full_name.casefold() != snapshot.repository_full_name.casefold()):
            raise VersionError(409, "Document belongs to a different repository")
        for version in self._versions[doc_id]:
            if (version.origin == VersionOrigin.source_change
                    and any(
                        ref.id == request.source_change_id
                        and ref.trigger == request.trigger
                        and ref.commit_sha == snapshot.commit_sha
                        and ref.pull_request_number == request.pull_request_number
                        for ref in version.source_changes)):
                return doc, base, version
        if doc.current_version != request.base_version or doc.pending_version is not None:
            raise VersionError(409, "The document changed or already has a pending version")
        return doc, base, None

    @staticmethod
    def _revision_operations(doc: Document, base: DocumentVersion, request: RevisionDraftRequest):
        paths = {section.path for section in base.sections}
        if not request.file_changes:
            return [RevisionFileChange(path=file.path, action="updated")
                    for file in request.files if file.path in paths]

        files = {file.path for file in request.files}
        targets, sources = set(), set()
        operations = []
        module = doc.target.replace(".", "/").rstrip("/") + "/"
        for change in request.file_changes:
            path, action, previous = change.path, change.action, change.previous_path
            if (path in targets or (action == "renamed") != bool(previous)
                    or (action == "removed") != (change.blob_sha is None)
                    or (action != "removed" and path not in files)):
                raise VersionError(409, "Invalid source evidence for the revision")
            targets.add(path)
            if action == "added":
                if path not in paths and (doc.scope == Scope.repository
                        or doc.scope == Scope.module and path.startswith(module)):
                    operations.append(change)
            elif action == "renamed":
                if previous in paths:
                    if path in paths or previous in sources:
                        raise VersionError(409, "The rename overlaps another document section")
                    operations.append(change)
                    sources.add(previous)
            elif path in paths:
                operations.append(change)
                sources.add(path)
        if any(change.previous_path in targets for change in operations if change.previous_path):
            raise VersionError(409, "The rename source also has a revision operation")
        return operations

    def prepare_revision(self, doc_id: str, owner: str, request: RevisionDraftRequest, generate):
        with self._lock:
            doc, base, existing = self._revision_base(doc_id, owner, request)
            if existing is not None:
                return PreparedRevision()
            if not base.sections_match_content:
                return None
            operations = self._revision_operations(doc, base, request)
            if not operations:
                return None
            paths = {change.path for change in operations if change.action != "removed"}
            files = [file for file in request.files if file.path in paths]

        replacements, report = generate(doc, files)
        return PreparedRevision(replacements=replacements, report=report)

    def propose_revision(self, doc_id: str, owner: str, request: RevisionDraftRequest, generate):
        prepared = self.prepare_revision(doc_id, owner, request, generate)
        if prepared is None:
            return None
        return self.commit_revision(doc_id, owner, request, prepared)

    def commit_revision(self, doc_id: str, owner: str, request: RevisionDraftRequest,
                        prepared: PreparedRevision, lease_expires_at: Optional[datetime] = None):
        with self._lock:
            self._require_revision_lease(lease_expires_at)
            doc, base, existing = self._revision_base(doc_id, owner, request)
            if existing is not None:
                return existing
            replacements, report = prepared.replacements, prepared.report
            if report is None or not base.sections_match_content:
                return None
            operations = self._revision_operations(doc, base, request)
            expected = {change.path for change in operations if change.action != "removed"}
            if replacements.keys() != expected or any(path != section.path for path, section in replacements.items()):
                raise VersionError(409, "Prepared sections do not match the revision")
            by_source = {change.previous_path or change.path: change for change in operations
                         if change.action != "added"}
            sections = []
            for section in base.sections:
                change = by_source.get(section.path)
                if change is None:
                    sections.append(section)
                elif change.action != "removed":
                    sections.append(replacements[change.path])
            sections.extend(replacements[change.path] for change in operations if change.action == "added")
            obsolete = set(by_source) | expected
            skipped = [item for item in base.skipped if item.path not in obsolete]
            content = assemble(doc, sections, skipped, report.template_name)
            if content == base.content and all(change.action in ("updated", "dependent") for change in operations):
                return None
            number = doc.versions_total + 1
            version = DocumentVersion(
                number=number, status=VersionStatus.proposed, origin=VersionOrigin.source_change,
                base_version=base.number, content=content, sections=sections, skipped=skipped,
                created_by="AI", source_snapshot=request.source_snapshot,
                evidence_report=report, review_report=report,
                source_changes=[SourceChangeRef(
                    id=request.source_change_id, trigger=request.trigger,
                    commit_sha=request.source_snapshot.commit_sha,
                    pull_request_number=request.pull_request_number)],
                revision_files=operations if request.file_changes else [],
                changes=[SectionChange(path=change.path, previous_path=change.previous_path,
                                       action=SectionAction.updated if change.action == "dependent"
                                       else SectionAction(change.action)) for change in operations],
            )
            self._require_revision_lease(lease_expires_at)
            previous = doc.model_copy(deep=True)
            self._versions[doc_id].append(version)
            doc.pending_revision = request.source_snapshot
            doc.pending_version = doc.versions_total = number
            doc.updated_at = now()
            self._event(doc_id, HistoryAction.proposed, number, "AI",
                        f"Source revision {request.source_snapshot.commit_sha}", related=base.number)
            try:
                self._save()
            except OSError:
                self._versions[doc_id].pop()
                self._events[doc_id].pop()
                self._docs[doc_id] = previous
                raise
            return version

    @staticmethod
    def _require_revision_lease(lease_expires_at: Optional[datetime]) -> None:
        if lease_expires_at is not None and now() >= lease_expires_at:
            raise VersionError(409, "The revision job lease expired")

    def propose_drift(self, owner, repository_id, report, finding):
        target = finding.document
        pr = report.pull_request
        if not (target.document_id and target.version and report.repository and pr.head_sha and pr.head_branch):
            raise VersionError(409, "This finding has no versioned document or source revision")
        snapshot = SourceSnapshot(repository_id=repository_id, repository_full_name=report.repository,
                                  branch=pr.head_branch, commit_sha=pr.head_sha,
                                  pull_request_number=pr.number, pull_request_base_sha=pr.base_head_sha)
        resolution = finding.resolution
        key = f"drift:{report.id}:{finding.id}"
        if resolution.rejected_draft_version is not None:
            key += f":after:{resolution.rejected_draft_version}"
        request = RevisionDraftRequest(source_change_id=key, trigger="PULL_REQUEST",
                                       pull_request_number=pr.number, source_snapshot=snapshot,
                                       base_version=target.version, files=[])
        audit = {"report_id": report.id, "finding_id": finding.id, "decision": resolution.decision,
                 "proposed": resolution.proposed, "evidence": [
                     item.model_dump(mode="json") for item in finding.evidence]}
        with self._lock:
            doc, base, existing = self._revision_base(target.document_id, owner, request)
            if existing is not None:
                if existing.drift_finding != audit:
                    raise VersionError(409, "This finding already has a different draft decision")
                return existing.number
            section = next((item for item in base.sections if item.path == target.path), None)
            if (not base.sections_match_content or section is None or not section.markdown
                    or base.content.count(section.markdown) != 1):
                raise VersionError(409, "The affected section cannot be updated safely")
            template_snapshot = base.review_report or base.evidence_report
            proposed = resolution.proposed
            if template_snapshot and template_snapshot.template_sections:
                title = section.markdown.splitlines()[0]
                if not proposed.startswith("# "):
                    passage = next((item.excerpt for item in finding.evidence
                                    if item.kind == "documentation" and item.path == section.path
                                    and item.excerpt), None)
                    if passage is None or section.markdown.count(passage) != 1:
                        raise VersionError(409, "The drift suggestion cannot be located in the affected section")
                    replacement = f"{title}\n\n{proposed}" if passage == title else proposed
                    proposed = section.markdown.replace(passage, replacement, 1)
                # The renderer omits sections without applicable entities. Preserve the
                # headings present in this file rather than requiring inapplicable ones.
                if proposed.splitlines()[0] != title or _template_headings(proposed) != _template_headings(section.markdown):
                    raise VersionError(409, "The drift draft changes the documentation template headings")
            sections = [item.model_copy(update={"markdown": proposed, "status": "manual"})
                        if item.path == target.path else item for item in base.sections]
            evidence = [Evidence(id=item.id, kind=EvidenceKind.doc if item.kind == "documentation"
                                 else EvidenceKind.source, path=item.path or finding.file,
                                 line_start=item.line_start, line_end=item.line_end, excerpt=item.excerpt)
                        for item in finding.evidence]
            review = JobReport(job_id=key, template_id=doc.template_id, method="drift",
                               template_name=template_snapshot.template_name if template_snapshot else None,
                               template_version=template_snapshot.template_version if template_snapshot else doc.template_version,
                               template_instructions=template_snapshot.template_instructions if template_snapshot else None,
                               template_sections=template_snapshot.template_sections if template_snapshot else [],
                               files=[FileReport(path=finding.file, status=FileResultStatus.generated,
                                                 context_used=evidence)])
            number = doc.versions_total + 1
            version = DocumentVersion(
                number=number, status=VersionStatus.proposed, origin=VersionOrigin.source_change,
                base_version=base.number, created_by=owner, manual=True,
                content=base.content.replace(section.markdown, proposed, 1),
                sections=sections, skipped=base.skipped, source_snapshot=snapshot,
                source_changes=[SourceChangeRef(id=key, trigger="PULL_REQUEST", commit_sha=pr.head_sha,
                                               pull_request_number=pr.number)],
                changes=[SectionChange(path=target.path, action=SectionAction.edited)],
                evidence_report=review, review_report=review, drift_finding=audit)
            previous = doc.model_copy(deep=True)
            self._versions[doc.id].append(version)
            doc.pending_version = doc.versions_total = number
            doc.pending_revision = snapshot
            doc.updated_at = now()
            self._event(doc.id, HistoryAction.proposed, number, owner, key, related=base.number)
            try:
                self._save()
            except OSError:
                self._versions[doc.id].pop()
                self._events[doc.id].pop()
                self._docs[doc.id] = previous
                raise
            return number

    def get_owned(self, doc_id: str, owner_user_id: str) -> Document:
        with self._lock:
            doc = self.get(doc_id)
            if doc.owner_user_id is None or doc.owner_user_id != owner_user_id:
                raise _not_found("Document")
            return doc

    def edit_owned(
        self,
        doc_id: str,
        owner_user_id: str,
        expected_version: int,
        content: str,
        note: Optional[str] = None,
        actor_role: Optional[str] = None,
        trigger_source: Optional[str] = None,
    ) -> DocumentVersion:
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
            resolved_role = actor_role or "DEVELOPER"
            resolved_trigger = trigger_source or TriggerSource.manual_edit.value
            if doc.pending_version is not None:
                base.status = VersionStatus.superseded
                base.superseded_by = number
                self._event(
                    doc_id,
                    HistoryAction.superseded,
                    base.number,
                    owner_user_id,
                    "Replaced after another changes request",
                    related=number,
                    actor_role=resolved_role,
                    trigger_source=resolved_trigger,
                    status=VersionStatus.superseded.value,
                )
            version = DocumentVersion(
                number=number,
                status=VersionStatus.proposed,
                origin=VersionOrigin.edit,
                base_version=doc.current_version,
                content=content,
                sections=list(base.sections),
                skipped=list(base.skipped),
                sections_match_content=False,
                source_changes=[ref.model_copy(deep=True) for ref in base.source_changes],
                manual=True,
                note=note,
                created_by=owner_user_id,
            )
            inherit_evidence(version, base)     # LD-402: the resubmission can be reviewed
            self._versions[doc_id].append(version)
            doc.pending_version = number
            doc.versions_total = number
            doc.updated_at = now()
            self._event(
                doc_id,
                HistoryAction.proposed,
                number,
                owner_user_id,
                note or "Owner edited after changes requested",
                actor_role=resolved_role,
                trigger_source=resolved_trigger,
                status=VersionStatus.proposed.value,
            )
            self._save()
            return version

    def edit_staff_draft(self, doc_id: str, owner: str, expected: int, actor: str,
                         content: str, reason: str) -> DocumentVersion:
        with self._lock:
            doc = self.get_owned(doc_id, owner)
            if doc.pending_version is None:
                raise VersionError(409, "No document version is awaiting review")
            pending = self.version(doc_id, doc.pending_version)
            if pending.number != expected:
                if (pending.evidence_from_version == expected and pending.created_by == actor
                        and pending.content == content and pending.note == reason):
                    return pending
                raise VersionError(409, "The submitted document version has changed")
            report = pending.review_report or pending.evidence_report
            if report and report.template_sections:
                if _template_headings(content) != _template_headings(pending.content):
                    raise VersionError(409, "The Staff edit changes the documentation template headings")
            sections = pending.sections
            matches = doc.scope == Scope.file and len(sections) == 1 and not pending.skipped
            if matches:
                sections = [sections[0].model_copy(update={"markdown": content, "status": "manual"})]
            previous = doc.model_copy(deep=True)
            edited = pending.model_copy(deep=True, update={
                "number": doc.versions_total + 1, "content": content, "sections": sections,
                "sections_match_content": matches,
                "evidence_from_version": pending.number, "created_by": actor, "created_at": now(),
                "manual": True, "note": reason,
            })
            pending.status = VersionStatus.superseded
            pending.superseded_by = edited.number
            self._versions[doc.id].append(edited)
            doc.pending_version = doc.versions_total = edited.number
            doc.updated_at = now()
            self._event(doc.id, HistoryAction.edited, edited.number, actor, reason, related=pending.number)
            try:
                self._save()
            except OSError:
                self._versions[doc.id].pop()
                self._events[doc.id].pop()
                self._docs[doc.id] = previous
                pending.status = VersionStatus.proposed
                pending.superseded_by = None
                raise
            return edited

    def rollback_owned(
        self,
        doc_id: str,
        owner_user_id: str,
        source_version_number: int,
        actor_user_id: str,
        note: Optional[str] = None,
        actor_role: Optional[str] = None,
        trigger_source: Optional[str] = None,
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
                sections_match_content=source.sections_match_content,
            )
            inherit_evidence(version, source)   # LD-402: all evidence, not only evidence_report

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
                actor_role=actor_role or "DEVELOPER",
                trigger_source=trigger_source or TriggerSource.rollback.value,
                status=VersionStatus.proposed.value,
            )

            self._save()
            return version

    def require_workflow_decision(self, doc_id: str, version_number: int, decision: str,
                                  actor_user_id: str, note: Optional[str]) -> DocumentVersion:
        action, status = {
            "APPROVED": (HistoryAction.accepted, VersionStatus.accepted),
            "REJECTED": (HistoryAction.dismissed, VersionStatus.dismissed),
        }[decision]
        with self._lock:
            version = self.version(doc_id, version_number)
            events = [event for event in self._events.get(doc_id, [])
                      if event.version == version_number and event.action == action]
            if (version.status != status or version.decided_by != actor_user_id or len(events) != 1
                    or events[0].actor != actor_user_id or events[0].note != note):
                raise VersionError(409, "No matching Manager decision for this version, actor and note")
            return version

    def resolve_workflow_version(
        self,
        doc_id: str,
        owner_user_id: str,
        version_number: int,
        decision: str,
        actor_user_id: str,
        note: Optional[str] = None,
        *,
        replay: bool = False,
        actor_role: Optional[str] = None,
        trigger_source: Optional[str] = None,
    ) -> None:
        with self._lock:
            doc = self.get_owned(doc_id, owner_user_id)
            if decision not in ("APPROVED", "REJECTED"):
                raise VersionError(400, "Unknown review decision")
            if doc.pending_version is None or (replay and doc.pending_version != version_number):
                if not replay and decision == "APPROVED" and doc.current_version != version_number:
                    raise VersionError(409, "The current document version has changed")
                self.require_workflow_decision(doc_id, version_number, decision, actor_user_id, note)
                # A visible rename from a previous attempt may not have been synced yet.
                self._save()
                return
            if doc.pending_version != version_number:
                raise VersionError(409, "The pending document version has changed")
            version = self.version(doc_id, version_number)
            if version.status != VersionStatus.proposed:
                raise VersionError(409, "The document version is no longer pending")
            previous_document = doc.model_copy(deep=True)
            previous_version = version.model_copy(deep=True)
            if decision == "APPROVED":
                version.status = VersionStatus.accepted
                doc.current_version = version_number
                action = HistoryAction.accepted
            else:
                version.status = VersionStatus.dismissed
                action = HistoryAction.dismissed
            version.decided_by = actor_user_id
            version.decided_at = now()
            version.note = note or version.note
            doc.pending_revision = None
            doc.pending_version = None
            doc.updated_at = now()
            self._event(
                doc_id,
                action,
                version_number,
                actor_user_id,
                note,
                actor_role=actor_role or "REVIEWER",
                trigger_source=trigger_source or TriggerSource.review_workflow.value,
                status=version.status.value,
            )
            try:
                self._save()
            except OSError:
                self._docs[doc_id] = previous_document
                versions = self._versions[doc_id]
                versions[versions.index(version)] = previous_version
                self._events[doc_id].pop()
                raise


documents = DocumentStore(os.getenv("DOCUMENTS_FILE", DEFAULT_FILE) or None)