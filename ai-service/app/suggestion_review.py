"""Review and apply documentation suggestions (LD-357).

A reviewer accepts (possibly after editing the proposed text) or rejects each suggestion of
LD-353 / LD-354. Applying the accepted ones:
- saved document: all accepted suggestions of the document go into ONE new version built on
  its newest version (the pending proposal if there is one, else the current one). A document
  with an owner gets a proposal that still goes through the review workflow; a document
  without an owner gets an accepted version. History is kept: nothing is overwritten.
- Markdown file of the repository: the service cannot write to the repository, so it returns
  the new file text and its diff, for the GitHub integration (or a person) to commit.
Each suggestion's `original` must still be in the text exactly once; otherwise it is marked
`conflict` and its document is not changed at all.
"""
import difflib
import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .drift_models import DocSource
from .models import now
from .suggestions import (Suggestion, SuggestionOperation, SuggestionReview, SuggestionStatus,
                          SuggestionStore, unified)
from .version_models import (DocumentVersion, HistoryAction, SectionAction, SectionChange,
                             VersionOrigin, VersionStatus)
from .versions import VersionError


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(accept|reject)$")
    proposed: Optional[str] = Field(default=None, max_length=200_000)
    """Accept with this text instead of the suggested one (the reviewer's edit)."""
    reviewer: Optional[str] = Field(default=None, max_length=200)
    comment: Optional[str] = Field(default=None, max_length=2000)


class ApplyRequest(BaseModel):
    ids: Optional[List[str]] = Field(default=None, max_length=500)
    batch_id: Optional[str] = Field(default=None, max_length=64)
    """Apply every accepted suggestion of this batch (when `ids` is not given)."""
    actor: Optional[str] = Field(default=None, max_length=200)
    note: Optional[str] = Field(default=None, max_length=1000)


class SuggestionProblem(BaseModel):
    id: str
    reason: str


class AppliedDocument(BaseModel):
    document_id: str
    version: int
    status: VersionStatus           # proposed (owned document: still to be approved) | accepted
    suggestions: List[str]
    sections: List[str]


class AppliedFile(BaseModel):
    path: str
    batch_id: str
    content: str                    # the whole Markdown file after the change
    diff: str
    suggestions: List[str]


class ApplyResult(BaseModel):
    documents: List[AppliedDocument] = Field(default_factory=list)
    files: List[AppliedFile] = Field(default_factory=list)
    conflicts: List[SuggestionProblem] = Field(default_factory=list)
    skipped: List[SuggestionProblem] = Field(default_factory=list)


# ---------- review ----------

def review(s: Suggestion, req: ReviewRequest) -> Suggestion:
    if s.status == SuggestionStatus.applied:
        raise VersionError(409, "The suggestion was already applied")
    edited = req.proposed is not None and req.proposed != s.proposed
    if req.decision == "accept":
        text = req.proposed if req.proposed is not None else s.proposed
        if text is None:
            raise VersionError(422, "This suggestion has no proposed text: send `proposed` to accept it")
        if edited:
            s.proposed = text
            s.diff = unified(s.original, text, s.target.path)
            if s.operation in (SuggestionOperation.review, SuggestionOperation.delete) and text:
                s.operation = SuggestionOperation.replace
            elif not text:
                s.operation = SuggestionOperation.delete
        s.status = SuggestionStatus.accepted
    else:
        s.status = SuggestionStatus.rejected
    s.conflict = None
    s.review = SuggestionReview(decision=req.decision, reviewer=req.reviewer, comment=req.comment,
                                edited=edited)
    return s


# ---------- apply ----------

def replace_once(text: str, original: str, proposed: str) -> Tuple[Optional[str], Optional[str]]:
    """(new text, None) or (None, why it cannot be applied)."""
    n = text.count(original) if original else 0
    if n == 0:
        return None, "the passage is no longer in the documentation (it changed after the suggestion was made)"
    if n > 1:
        return None, "the passage appears more than once in the documentation"
    out = text.replace(original, proposed, 1)
    if not proposed:                                   # deleted passage: no run of blank lines
        out = re.sub(r"\n{3,}", "\n\n", out).strip("\n") + ("\n" if text.endswith("\n") else "")
    return out, None


def _select(store: SuggestionStore, req: ApplyRequest, result: ApplyResult) -> List[Suggestion]:
    if req.ids:
        chosen = []
        for i in dict.fromkeys(req.ids):
            s = store.get(i)
            if s is None:
                result.skipped.append(SuggestionProblem(id=i, reason="not found"))
            elif s.status != SuggestionStatus.accepted:
                result.skipped.append(SuggestionProblem(id=i, reason=f"status is {s.status.value}, not accepted"))
            else:
                chosen.append(s)
        return chosen
    if req.batch_id:
        if store.batch(req.batch_id) is None:
            raise VersionError(404, "Suggestion batch not found")
        return store.list(req.batch_id, SuggestionStatus.accepted.value)
    raise VersionError(422, "Give `ids` or `batch_id`")


def _conflict(s: Suggestion, why: str, result: ApplyResult) -> None:
    s.status, s.conflict = SuggestionStatus.conflict, why
    result.conflicts.append(SuggestionProblem(id=s.id, reason=why))


def apply_to_document(docs, doc_id: str, items: List[Suggestion], req: ApplyRequest,
                      result: ApplyResult) -> None:
    with docs._lock:
        try:
            doc = docs.get(doc_id)
        except VersionError:
            for s in items:
                _conflict(s, "the document no longer exists", result)
            return
        base_no = doc.pending_version or doc.current_version
        base = docs.version(doc_id, base_no)
        sections = [sec.model_copy() for sec in base.sections]
        content = base.content
        by_path = {sec.path: sec for sec in sections} if base.sections_match_content else {}
        problems: List[Tuple[Suggestion, str]] = []
        touched: List[str] = []
        for s in sorted(items, key=lambda x: (x.target.path, -x.target.line_start)):
            sec = by_path.get(s.target.path)
            if sec is not None:
                new, why = replace_once(sec.markdown, s.original, s.proposed or "")
                if new is not None:
                    content_new, why = replace_once(content, sec.markdown, new) if sec.markdown else (None, "empty section")
                    if content_new is not None:
                        sec.markdown, content = new, content_new
            else:
                new, why = replace_once(content, s.original, s.proposed or "")
                if new is not None:
                    content = new
            if why:
                problems.append((s, why))
            elif s.target.path not in touched:
                touched.append(s.target.path)
        if problems:                                  # all or nothing for one document
            for s, why in problems:
                _conflict(s, why, result)
            for s in items:
                if all(s is not p for p, _ in problems):
                    result.skipped.append(SuggestionProblem(
                        id=s.id, reason="not applied: another suggestion of the same document has a conflict"))
            return

        number = len(docs._versions[doc_id]) + 1
        owned = doc.owner_user_id is not None
        ids = [s.id for s in items]
        note = req.note or f"Applied suggestion(s) {', '.join(ids)}"
        if doc.pending_version is not None:
            base.status = VersionStatus.superseded
            base.superseded_by = number
            docs._event(doc_id, HistoryAction.superseded, base.number, req.actor,
                        "Replaced by applied suggestions", related=number)
        status = VersionStatus.proposed if owned else VersionStatus.accepted
        v = DocumentVersion(number=number, status=status, origin=VersionOrigin.edit,
                            base_version=doc.current_version or None, content=content,
                            sections=sections, skipped=list(base.skipped),
                            sections_match_content=base.sections_match_content,
                            changes=[SectionChange(path=p, action=SectionAction.edited) for p in touched],
                            confidence=base.confidence, note=note, created_by=req.actor,
                            decided_by=None if owned else req.actor, decided_at=None if owned else now())
        docs._versions[doc_id].append(v)
        if owned:
            doc.pending_version = number
        else:
            doc.current_version = number
        doc.versions_total = number
        doc.updated_at = now()
        docs._event(doc_id, HistoryAction.proposed if owned else HistoryAction.accepted, number,
                    req.actor, note)
        docs._save()
        for s in items:
            s.status, s.applied_version, s.conflict = SuggestionStatus.applied, number, None
        result.documents.append(AppliedDocument(document_id=doc_id, version=number, status=status,
                                                suggestions=ids, sections=touched))


def apply_to_file(store: SuggestionStore, batch_id: str, path: str, items: List[Suggestion],
                  result: ApplyResult) -> None:
    text = store.files.get(batch_id, {}).get(path)
    if text is None:
        for s in items:
            _conflict(s, "the Markdown file is no longer kept (the batch is too old)", result)
        return
    new, problems = text, []
    for s in sorted(items, key=lambda x: -x.target.line_start):
        out, why = replace_once(new, s.original, s.proposed or "")
        if why:
            problems.append((s, why))
        else:
            new = out
    if problems:
        for s, why in problems:
            _conflict(s, why, result)
        return
    store.files[batch_id][path] = new
    for s in items:
        s.status = SuggestionStatus.applied
    result.files.append(AppliedFile(path=path, batch_id=batch_id, content=new,
                                    diff="\n".join(difflib.unified_diff(
                                        text.split("\n"), new.split("\n"), f"a/{path}", f"b/{path}",
                                        lineterm="")),
                                    suggestions=[s.id for s in items]))


def apply(store: SuggestionStore, docs, req: ApplyRequest) -> ApplyResult:
    result = ApplyResult()
    with store._lock:
        chosen = _select(store, req, result)
        groups: Dict[Tuple, List[Suggestion]] = {}
        for s in chosen:
            if s.proposed is None:
                result.skipped.append(SuggestionProblem(id=s.id, reason="no proposed text"))
                continue
            key = ("doc", s.target.document_id) if s.target.source == DocSource.document \
                else ("file", s.batch_id, s.target.path)
            groups.setdefault(key, []).append(s)
        for key, items in groups.items():
            if key[0] == "doc":
                apply_to_document(docs, key[1], items, req, result)
            else:
                apply_to_file(store, key[1], key[2], items, result)
    return result
