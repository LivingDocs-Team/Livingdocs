"""Generate drift evidence (LD-149).

Each finding becomes a self-contained piece of evidence a reviewer can verify without opening
the repository: the exact documentation lines, the code before/after, the diff hunk, why it was
flagged and what to change. Code evidence uses the field names of the project's
`GroundingEvidence` (file_path, start_line, end_line, code_snippet, commit_hash).
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .affected import AffectedDocument
from .detector import RULES, DriftFinding
from .doc_scanner import DocIndex
from .models import ChangeType, FileChange, Hunk, PullRequestAnalysis

SCHEMA_VERSION = "1.0"
CONTEXT_LINES = 2
MAX_DIFF_LINES = 40
MAX_SNIPPET_CHARS = 600


@dataclass
class DocEvidence:
    path: str
    line: int
    section: str
    matched_text: str
    excerpt: List[Dict[str, Any]] = field(default_factory=list)   # [{"line": 12, "text": "...", "highlight": true}]


@dataclass
class CodeEvidence:
    file_path: str
    start_line: Optional[int]
    end_line: Optional[int]
    change_type: str
    code_snippet: str = ""
    commit_hash: Optional[str] = None
    before_signature: Optional[str] = None
    after_signature: Optional[str] = None
    details: List[str] = field(default_factory=list)
    diff_excerpt: str = ""


@dataclass
class DriftEvidence:
    id: str
    rule_id: str
    drift_type: str
    severity: str
    confidence: float
    entity: str
    kind: str
    summary: str
    reasons: List[str]
    suggestion: str
    doc: DocEvidence
    code: CodeEvidence
    doc_updated_in_pr: bool = False


@dataclass
class DriftReport:
    schema_version: str
    generated_at: str
    repository: Optional[str]
    base: Optional[str]
    head: Optional[str]
    commit_hash: Optional[str]
    summary: Dict[str, Any]
    evidence: List[DriftEvidence] = field(default_factory=list)
    affected_documents: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        return bool(self.evidence)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def _trim_hunk(h: Hunk, start: int, end: int, side: str, context: int = 1) -> List[str]:
    """Keep only the lines of a hunk around lines start..end (numbers of the given side)."""
    rows = []  # (line, old counter before, new counter before, position on `side`)
    o, n = h.old_start, h.new_start
    for line in h.lines:
        tag = line[:1]
        before = (o, n)
        if tag == "+":
            pos = n if side == "new" else o
            n += 1
        elif tag == "-":
            pos = o if side == "old" else n
            o += 1
        else:
            pos = n if side == "new" else o
            o, n = o + 1, n + 1
        rows.append((line, before, pos))
    keep = [i for i, (_, _, pos) in enumerate(rows) if start - context <= pos <= end + context]
    if not keep:
        return [h.header] + h.lines
    sub = rows[keep[0]:keep[-1] + 1]
    old_n = sum(1 for l, _, _ in sub if l[:1] in (" ", "-"))
    new_n = sum(1 for l, _, _ in sub if l[:1] in (" ", "+"))
    o0, n0 = sub[0][1]
    return [f"@@ -{o0},{old_n} +{n0},{new_n} @@"] + [l for l, _, _ in sub]


def _diff_excerpt(fc: Optional[FileChange], start: Optional[int], end: Optional[int], side: str) -> str:
    if fc is None or start is None:
        return ""
    lines: List[str] = []
    for h in fc.hunks_for(start, end or start, side):
        lines += _trim_hunk(h, start, end or start, side)
    if len(lines) > MAX_DIFF_LINES:
        lines = lines[:MAX_DIFF_LINES] + [f"... ({len(lines) - MAX_DIFF_LINES} more lines)"]
    return "\n".join(lines)


def _code_evidence(f: DriftFinding, analysis: PullRequestAnalysis, commit: Optional[str]) -> CodeEvidence:
    change = f.change
    if change is None:  # file-level finding (deleted / renamed file)
        fc = f.file_change
        return CodeEvidence(file_path=fc.old_path or fc.path if fc else f.code_file, start_line=None, end_line=None,
                            change_type=fc.status.value if fc else f.change_type, commit_hash=commit,
                            details=[f"file {fc.status.value}" + (f": {fc.old_path} -> {fc.path}" if fc and fc.old_path else "")]
                            if fc else [])
    ent = change.after or change.before
    side = "new" if change.after is not None else "old"
    fc = analysis.file_change(ent.file) or analysis.file_change(change.file)
    if change.change_type == ChangeType.MOVED and change.before is not None:
        fc = analysis.file_change(change.before.file) or fc
    return CodeEvidence(
        file_path=ent.file, start_line=ent.line, end_line=ent.end_line,
        change_type=change.change_type.value,
        code_snippet=(ent.source or "")[:MAX_SNIPPET_CHARS], commit_hash=commit,
        before_signature=change.before.signature if change.before else None,
        after_signature=change.after.signature if change.after else None,
        details=list(change.details),
        diff_excerpt=_diff_excerpt(fc, ent.line, ent.end_line, side))


def _doc_evidence(f: DriftFinding, index: DocIndex) -> DocEvidence:
    doc = index.docs[f.doc_path]
    lo, hi = max(1, f.doc_line - CONTEXT_LINES), min(len(doc.lines), f.doc_line + CONTEXT_LINES)
    return DocEvidence(
        path=f.doc_path, line=f.doc_line, section=f.section_title,
        matched_text=f.ref.reference.matched if f.ref else "",
        excerpt=[{"line": n, "text": doc.lines[n - 1], "highlight": n == f.doc_line} for n in range(lo, hi + 1)])


def build_evidence(f: DriftFinding, index: DocIndex, analysis: PullRequestAnalysis,
                   commit: Optional[str] = None) -> DriftEvidence:
    drift_type, description = RULES[f.rule_id]
    return DriftEvidence(
        id=f.id, rule_id=f.rule_id, drift_type=drift_type, severity=f.severity,
        confidence=f.confidence, entity=f.entity, kind=f.kind,
        summary=f"{description}: `{f.entity}` in {f.doc_path}:{f.doc_line}",
        reasons=list(f.reasons), suggestion=f.suggestion,
        doc=_doc_evidence(f, index), code=_code_evidence(f, analysis, commit),
        doc_updated_in_pr=f.doc_updated_in_pr)


def build_report(findings: List[DriftFinding], affected: List[AffectedDocument], index: DocIndex,
                 analysis: PullRequestAnalysis, repository: Optional[str] = None,
                 commit: Optional[str] = None, now: Optional[_dt.datetime] = None) -> DriftReport:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    evidence = [build_evidence(f, index, analysis, commit) for f in findings]
    by_sev = {s: sum(1 for e in evidence if e.severity == s) for s in ("high", "medium", "low")}
    summary = {
        **analysis.summary(),
        "documents_scanned": len(index),
        "documents_affected": len(affected),
        "documents_with_drift": len({e.doc.path for e in evidence}),
        "drift_findings": len(evidence),
        "by_severity": by_sev,
    }
    drift_by_doc: Dict[str, int] = {}
    for e in evidence:
        drift_by_doc[e.doc.path] = drift_by_doc.get(e.doc.path, 0) + 1
    affected_out = [{
        "path": d.path, "updated_in_pr": d.updated_in_pr, "references": len(d.references),
        "subjects": d.subjects, "drift_findings": drift_by_doc.get(d.path, 0)} for d in affected]
    return DriftReport(
        schema_version=SCHEMA_VERSION, generated_at=now.replace(microsecond=0).isoformat(),
        repository=repository, base=analysis.base, head=analysis.head, commit_hash=commit,
        summary=summary, evidence=evidence, affected_documents=affected_out,
        warnings=list(analysis.warnings))
