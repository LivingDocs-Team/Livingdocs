"""Versioned documentation produced by the AI service.

- LD-195  version management: save a job as a document, immutable versions, audit trail
- LD-128  automatic update after a source change (only the changed files are regenerated)
- LD-134  review an update: compare versions, accept / edit / dismiss / regenerate a proposal

Documents are saved to a JSON file (DOCUMENTS_FILE, default data/documents.json, written
atomically) so they survive a restart. Set DOCUMENTS_FILE= (empty) to keep them in memory only.
"""
import difflib
import json
import logging
import os
import pathlib
import re
import threading
import uuid
from typing import Dict, List, Optional, Tuple

from .generator import DocGenerator, get_generator
from .jobs import JobOutput
from .models import ContextDocument, FileAnalysis, GenerateRequest, Scope, Template, now
from .normalize import normalize
from .renderer import render_overview
from .retrieval import build_index, retrieve
from .templates import templates
from .version_models import (ChangeType, CompareResult, Document, DocumentUpdateRequest,
                             DocumentVersion, FileDiff, FileSection, HistoryAction, HistoryEvent,
                             SectionAction, SectionChange, SkippedFile, SourceChange,
                             UpdateResult, VersionOrigin, VersionStatus, VersionSummary)

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


_HEADING = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_SPLIT = re.compile(r"\n[ \t]*---[ \t]*\n")


def split_content(doc: Document, content: str, known: List[str]) -> Optional[Dict[str, str]]:
    """Split a whole document back into per-file Markdown (path -> text).

    Each part between `---` lines must start with `# <path>` of a known file; the first part may
    be the overview (`# <target>`). Returns None when the text cannot be split that way."""
    text = content.strip()
    if doc.scope == Scope.file and len(known) == 1 and not _SPLIT.search(text):
        return {known[0]: text + "\n"}
    out: Dict[str, str] = {}
    for i, part in enumerate(_SPLIT.split(text)):
        part = part.strip()
        if not part:
            continue
        m = _HEADING.match(part)
        title = m.group(1).strip().strip("`") if m else None
        if title in known and title not in out:
            out[title] = part + "\n"
        elif i == 0 and title == doc.target:
            continue                                   # overview, rebuilt from the sections
        else:
            return None
    return out or None


def _diff_counts(a: str, b: str) -> Tuple[int, int]:
    added = removed = 0
    for line in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


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

    # ---------- compare (LD-134) ----------

    def compare(self, doc_id: str, from_version: Optional[int] = None,
                to_version: Optional[int] = None) -> CompareResult:
        """Defaults: from = current version, to = pending proposal (or the newest version)."""
        doc = self.get(doc_id)
        a = self.version(doc_id, from_version if from_version is not None else doc.current_version)
        if to_version is None:
            to_version = doc.pending_version or len(self._versions[doc_id])
        b = self.version(doc_id, to_version)

        def per_file(v: DocumentVersion) -> Dict[str, str]:
            if v.sections_match_content:
                return {s.path: s.markdown for s in v.sections}
            parsed = split_content(doc, v.content, [s.path for s in v.sections])
            return parsed if parsed is not None else {"(document)": v.content}

        fa, fb = per_file(a), per_file(b)
        files: List[FileDiff] = []
        for path in list(dict.fromkeys([*fa, *fb])):
            if path not in fa:
                files.append(FileDiff(path=path, change="added",
                                      added_lines=len(fb[path].splitlines())))
            elif path not in fb:
                files.append(FileDiff(path=path, change="removed",
                                      removed_lines=len(fa[path].splitlines())))
            else:
                add, rem = _diff_counts(fa[path], fb[path])
                files.append(FileDiff(path=path, change="modified" if add or rem else "unchanged",
                                      added_lines=add, removed_lines=rem))
        add, rem = _diff_counts(a.content, b.content)
        diff = "\n".join(difflib.unified_diff(
            a.content.splitlines(), b.content.splitlines(),
            fromfile=f"version {a.number}", tofile=f"version {b.number}", lineterm=""))
        return CompareResult(document_id=doc_id, from_version=a.number, to_version=b.number,
                             files=files, added_lines=add, removed_lines=rem,
                             identical=a.content == b.content, unified_diff=diff)

    # ---------- internal helpers ----------

    def _event(self, doc_id: str, action: HistoryAction, version: int, actor: Optional[str] = None,
               note: Optional[str] = None, related: Optional[int] = None) -> None:
        self._events[doc_id].append(HistoryEvent(action=action, version=version, actor=actor,
                                                 note=note, related_version=related))

    def _add_version(self, doc: Document, version: DocumentVersion) -> DocumentVersion:
        vs = self._versions[doc.id]
        version.number = len(vs) + 1
        vs.append(version)
        doc.versions_total = len(vs)
        doc.updated_at = now()
        return version

    def _template(self, doc: Document, warnings: List[str]) -> Template:
        tpl = templates.get(doc.template_id)
        if tpl is None:
            tpl = templates.get("default")
            warnings.append(f"Template '{doc.template_id}' no longer exists; "
                            f"used '{tpl.id}' for the regenerated files.")
        return tpl

    def _pending(self, doc: Document) -> Optional[DocumentVersion]:
        return self.version(doc.id, doc.pending_version) if doc.pending_version else None

    def _supersede(self, doc: Document, old: DocumentVersion, by: int, actor: Optional[str],
                   note: str) -> None:
        old.status = VersionStatus.superseded
        old.superseded_by = by
        self._event(doc.id, HistoryAction.superseded, old.number, actor, note, related=by)

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

    # ---------- LD-128: update from a source change ----------

    def _apply(self, doc: Document, base: DocumentVersion, steps: List[dict],
               ) -> Tuple[List[FileSection], List[SkippedFile], List[SectionChange], List[str],
                          Optional[str]]:
        """Replay source-change steps on top of `base`. Only changed files are regenerated."""
        warnings: List[str] = []
        if not base.sections_match_content:
            warnings.append(f"Version {base.number} was edited by hand and could not be split per "
                            "file; the updated text is rebuilt from the per-file documentation, "
                            "so those hand edits are not kept.")
        tpl = self._template(doc, warnings)
        gen = self.generator or get_generator()
        sections: Dict[str, FileSection] = {s.path: s for s in base.sections}
        skipped: Dict[str, SkippedFile] = {s.path: s for s in base.skipped}
        changes: Dict[str, SectionChange] = {}
        renamed: Dict[str, str] = {}             # old path -> new path, to keep the file's place

        def record(path: str, action: SectionAction, previous: Optional[str] = None,
                   entities: Optional[List[str]] = None) -> None:
            old = changes.get(path)
            if old and old.action == SectionAction.added and action == SectionAction.updated:
                action = SectionAction.added       # added then changed again: still "added"
            changes[path] = SectionChange(path=path, action=action, previous_path=previous,
                                          entities=entities or [])

        for step in steps:
            change = SourceChange.model_validate(step["source_change"])
            analyses = {f["path"]: FileAnalysis.model_validate(f) for f in step.get("files", [])}
            context = [ContextDocument.model_validate(c) for c in step.get("context", [])]
            for f in analyses.values():
                normalize(f)
            listed = {cf.path for cf in change.files}
            for path in analyses:
                if path not in listed:
                    warnings.append(f"{path}: analysis ignored, the file is not in source change "
                                    f"{change.id}.")

            to_document: List[Tuple[FileAnalysis, List[str], Optional[FileSection]]] = []
            for cf in change.files:
                entities = [f"{e.kind} {e.name} ({e.change.lower()})" for e in cf.entities]
                if cf.change == ChangeType.REMOVED:
                    if cf.path in sections:
                        del sections[cf.path]
                        record(cf.path, SectionAction.removed, entities=entities)
                    skipped.pop(cf.path, None)
                    continue
                renamed_from = None
                if cf.change == ChangeType.RENAMED and cf.previous_path:
                    skipped.pop(cf.previous_path, None)
                    if cf.previous_path in sections:
                        renamed_from = sections.pop(cf.previous_path)
                        changes.pop(cf.previous_path, None)
                        renamed[cf.previous_path] = cf.path
                if cf.skipped_reason:
                    warnings.append(f"{cf.path}: not documented ({cf.skipped_reason}).")
                    continue
                a = analyses.get(cf.path)
                if a is None:
                    if renamed_from is not None:     # keep the old text under the new name
                        md = renamed_from.markdown.replace(f"# {cf.previous_path}", f"# {cf.path}", 1)
                        sections[cf.path] = FileSection(path=cf.path, markdown=md, status="moved",
                                                        confidence=renamed_from.confidence)
                        record(cf.path, SectionAction.renamed, cf.previous_path, entities)
                        warnings.append(f"{cf.path}: renamed from {cf.previous_path} without an "
                                        "analysis; the old documentation was moved, not regenerated.")
                    else:
                        warnings.append(f"{cf.path}: no analysis provided; its documentation "
                                        "was not updated.")
                    continue
                if a.status.value != "ok":
                    reason = (a.error or "").strip() or f"analyzer status '{a.status.value}'"
                    warnings.append(f"{cf.path}: skipped ({reason}); the previous documentation "
                                    "is kept." if cf.path in sections else
                                    f"{cf.path}: skipped ({reason}).")
                    if cf.path not in sections:
                        skipped[cf.path] = SkippedFile(path=cf.path, reason=reason)
                    continue
                to_document.append((a, entities, renamed_from))
                if renamed_from is not None:
                    changes[cf.path] = SectionChange(path=cf.path, action=SectionAction.renamed,
                                                     previous_path=cf.previous_path, entities=entities)

            if not to_document:
                continue
            # retrieval context: other changed files, the documentation of unchanged files, and
            # any extra documents sent with the request
            regenerating = {a.path for a, _, _ in to_document}
            ctx = [*context, *[ContextDocument(path=s.path, title=s.path, content=s.markdown[:200_000])
                               for s in sections.values() if s.path not in regenerating]]
            index = build_index(GenerateRequest(scope=Scope.repository, target=doc.target,
                                                files=[a for a, _, _ in to_document],
                                                output_language=doc.output_language, context=ctx))
            for a, entities, renamed_from in to_document:
                was_renamed = renamed_from is not None
                try:
                    r = gen.document_file(a, tpl, doc.output_language, retrieve(index, a))
                except Exception as exc:  # one bad file never stops the update
                    warnings.append(f"{a.path}: generation failed: {exc}; the previous "
                                    "documentation is kept.")
                    if was_renamed:              # put the old text back under its old name
                        sections[renamed_from.path] = renamed_from
                        changes.pop(a.path, None)
                    continue
                existed = a.path in sections
                sections[a.path] = FileSection(path=a.path, markdown=r.markdown,
                                               status=r.status.value, confidence=r.confidence)
                skipped.pop(a.path, None)
                warnings.extend(r.warnings)
                if not was_renamed:
                    record(a.path, SectionAction.updated if existed else SectionAction.added,
                           entities=entities)

        # keep the original order; new files go to the end
        order = []
        for s in base.sections:
            p, seen = s.path, set()
            while p in renamed and p not in sections and p not in seen:   # a -> b -> c
                seen.add(p)
                p = renamed[p]
            order.append(p)
        ordered = [sections[p] for p in order if p in sections]
        ordered += [s for p, s in sections.items() if p not in order]
        return ordered, list(skipped.values()), list(changes.values()), warnings, tpl.name

    def _build_proposal(self, doc: Document, accepted_base: int, steps: List[dict],
                        origin: VersionOrigin, actor: Optional[str], note: Optional[str],
                        ) -> Tuple[Optional[DocumentVersion], List[str]]:
        base = self.version(doc.id, accepted_base)
        sections, skipped, changes, warnings, tpl_name = self._apply(doc, base, steps)
        if not changes:
            return None, warnings
        refs = []
        for step in steps:
            ref = SourceChange.model_validate(step["source_change"]).ref()
            if ref.id not in {r.id for r in refs}:
                refs.append(ref)
        v = DocumentVersion(number=0, status=VersionStatus.proposed, origin=origin,
                            base_version=accepted_base,
                            content=assemble(doc, sections, skipped, tpl_name),
                            sections=sections, skipped=skipped, changes=changes, warnings=warnings,
                            confidence=_mean([s.confidence for s in sections]),
                            source_changes=refs, note=note, created_by=actor)
        self._add_version(doc, v)
        self._plans[doc.id][v.number] = {"accepted_base": accepted_base, "steps": steps}
        return v, warnings

    def update(self, doc_id: str, req: DocumentUpdateRequest) -> Tuple[UpdateResult, bool]:
        """Returns (result, created). A pending proposal is extended: the new proposal contains
        its changes plus this source change, and the old one is marked superseded."""
        with self._lock:
            doc = self.get(doc_id)
            change_id = req.source_change.id
            pending = self._pending(doc)
            if pending and change_id in {r.id for r in pending.source_changes}:
                return UpdateResult(document_id=doc.id, proposal=pending,
                                    message=f"Source change {change_id} is already in proposal "
                                            f"version {pending.number}."), False
            for v in self._versions[doc.id]:
                if v.status == VersionStatus.accepted and change_id in {r.id for r in v.source_changes}:
                    raise VersionError(409, f"Source change {change_id} was already applied "
                                            f"in version {v.number}")
            step = {"source_change": req.source_change.model_dump(mode="json"),
                    "files": [f.model_dump(mode="json") for f in req.files],
                    "context": [c.model_dump(mode="json") for c in req.context]}
            prior = self._plans[doc.id].get(pending.number) if pending else None
            steps = [*(prior["steps"] if prior else []), step]
            proposal, warnings = self._build_proposal(doc, doc.current_version, steps,
                                                      VersionOrigin.source_change, req.actor, req.note)
            if proposal is None:
                return UpdateResult(document_id=doc.id, message="No documented file was affected "
                                    "by this source change; no new version was created.",
                                    warnings=warnings), False
            if pending:
                self._supersede(doc, pending, proposal.number, req.actor,
                                f"Extended with source change {change_id}")
            doc.pending_version = proposal.number
            self._event(doc.id, HistoryAction.proposed, proposal.number, req.actor,
                        req.note or f"Source change {change_id}", related=doc.current_version)
            self._save()
            return UpdateResult(document_id=doc.id, proposal=proposal, warnings=warnings,
                                message=f"Proposal version {proposal.number} is waiting for "
                                        "review."), True

    # ---------- LD-134: review a proposal ----------

    def _proposal(self, doc: Document, number: int) -> DocumentVersion:
        v = self.version(doc.id, number)
        if v.status != VersionStatus.proposed:
            raise VersionError(409, f"Version {number} is {v.status.value}, not a proposal")
        return v

    def accept(self, doc_id: str, number: int, actor: Optional[str] = None,
               note: Optional[str] = None) -> DocumentVersion:
        with self._lock:
            doc = self.get(doc_id)
            v = self._proposal(doc, number)
            v.status, v.decided_by, v.decided_at = VersionStatus.accepted, actor, now()
            doc.current_version, doc.pending_version, doc.updated_at = v.number, None, now()
            self._event(doc.id, HistoryAction.accepted, v.number, actor, note)
            self._save()
            return v

    def dismiss(self, doc_id: str, number: int, actor: Optional[str] = None,
                note: Optional[str] = None) -> DocumentVersion:
        with self._lock:
            doc = self.get(doc_id)
            v = self._proposal(doc, number)
            v.status, v.decided_by, v.decided_at = VersionStatus.dismissed, actor, now()
            doc.pending_version, doc.updated_at = None, now()
            self._event(doc.id, HistoryAction.dismissed, v.number, actor, note)
            self._save()
            return v

    def regenerate(self, doc_id: str, number: int, actor: Optional[str] = None,
                   note: Optional[str] = None) -> DocumentVersion:
        """Generate the proposal again from the same source changes (e.g. after the AI gave a
        poor result or the template was changed). The old proposal is superseded."""
        with self._lock:
            doc = self.get(doc_id)
            old = self._proposal(doc, number)
            plan = self._plans[doc.id].get(old.number)
            if not plan:
                raise VersionError(409, f"Version {number} has no source change to regenerate from")
            new, _ = self._build_proposal(doc, doc.current_version, plan["steps"],
                                          VersionOrigin.regenerate, actor, note)
            if new is None:
                raise VersionError(409, "Regenerating produced no change compared with "
                                        f"version {doc.current_version}")
            self._supersede(doc, old, new.number, actor, "Regenerated")
            doc.pending_version = new.number
            self._event(doc.id, HistoryAction.regenerated, new.number, actor, note, related=old.number)
            self._save()
            return new

    def _rebase_pending(self, doc: Document, actor: Optional[str], reason: str) -> None:
        """The current version changed (edit, rollback): rebuild a waiting proposal on top of it
        so accepting it never undoes that change."""
        pending = self._pending(doc)
        if not pending:
            return
        plan = self._plans[doc.id].get(pending.number)
        new = None
        if plan:
            new, _ = self._build_proposal(doc, doc.current_version, plan["steps"],
                                          VersionOrigin.regenerate, actor,
                                          f"Rebased on version {doc.current_version} ({reason})")
        if new is None:
            self._supersede(doc, pending, doc.current_version, actor,
                            f"No longer changes anything after {reason}")
            doc.pending_version = None
            return
        self._supersede(doc, pending, new.number, actor, f"Rebased after {reason}")
        doc.pending_version = new.number
        self._event(doc.id, HistoryAction.regenerated, new.number, actor,
                    f"Rebased on version {doc.current_version}", related=pending.number)

    def edit(self, doc_id: str, number: int, content: str, accept: bool = True,
             actor: Optional[str] = None, note: Optional[str] = None) -> DocumentVersion:
        """Edit a proposal or the current version. The edited text is saved as a new version;
        the edited one is never changed."""
        with self._lock:
            doc = self.get(doc_id)
            src = self.version(doc.id, number)
            is_current = src.number == doc.current_version
            if src.status != VersionStatus.proposed and not is_current:
                raise VersionError(409, f"Only a proposal or the current version can be edited; "
                                        f"version {number} is {src.status.value}")
            if content.strip() == src.content.strip():
                raise VersionError(409, "The content is unchanged")

            known = [s.path for s in src.sections]
            parsed = split_content(doc, content, known)
            old = {s.path: s for s in src.sections}
            changes: List[SectionChange] = []
            warnings: List[str] = []
            if parsed is None:
                sections, match = list(src.sections), False
                warnings.append("The edited text could not be split per file (each part between "
                                "'---' lines must start with '# <file path>'); a later source-change "
                                "update will rebuild the text and replace these edits.")
                changes.append(SectionChange(path="(document)", action=SectionAction.edited))
            else:
                sections, match = [], True
                for path, md in parsed.items():
                    prev = old[path]
                    if md.strip() == prev.markdown.strip():
                        sections.append(prev)
                    else:
                        sections.append(FileSection(path=path, markdown=md, status="manual"))
                        changes.append(SectionChange(path=path, action=SectionAction.edited))
                for path in old:
                    if path not in parsed:
                        changes.append(SectionChange(path=path, action=SectionAction.removed))
            plan = self._plans[doc.id].get(src.number) if src.status == VersionStatus.proposed else None
            v = DocumentVersion(number=0, status=VersionStatus.accepted if accept else VersionStatus.proposed,
                                origin=VersionOrigin.edit, base_version=src.number,
                                content=content.rstrip() + "\n", sections=sections,
                                skipped=list(src.skipped), sections_match_content=match,
                                changes=changes or [SectionChange(path="(overview)",
                                                                  action=SectionAction.edited)],
                                warnings=warnings, manual=True,
                                confidence=_mean([s.confidence for s in sections]),
                                source_changes=list(src.source_changes), note=note, created_by=actor,
                                decided_by=actor if accept else None,
                                decided_at=now() if accept else None)
            self._add_version(doc, v)
            if src.status == VersionStatus.proposed:
                self._supersede(doc, src, v.number, actor, "Edited")
                doc.pending_version = None
                if not accept and plan:   # an edited proposal keeps its inputs for regeneration
                    self._plans[doc.id][v.number] = plan
            self._event(doc.id, HistoryAction.edited, v.number, actor, note, related=src.number)
            if accept:
                doc.current_version = v.number
                self._event(doc.id, HistoryAction.accepted, v.number, actor, note)
                if is_current:
                    self._rebase_pending(doc, actor, f"edit of version {src.number}")
            else:
                other = self._pending(doc)
                if other and other.number != v.number:
                    self._supersede(doc, other, v.number, actor, "Replaced by an edited proposal")
                doc.pending_version = v.number
            self._save()
            return v


documents = DocumentStore(os.getenv("DOCUMENTS_FILE", DEFAULT_FILE) or None)
