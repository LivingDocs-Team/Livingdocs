"""LD-149 Generate drift evidence.

Every drift finding carries the evidence a reviewer needs to check it without opening GitHub
(BR-50: code diff, commit and related ticket):

    X1..  code_diff       the lines of the Pull Request diff that changed the entity (or, without
                          a diff, the signature and changed docstring before -> after)
    D1..  documentation   each place where the documentation still describes the old code,
                          including what LD-151 found it still says (old parameter, type,
                          default, exception, status code, value, docstring, line reference)
    C1    commit          head commit and Pull Request number / link
    T1..  ticket          Jira keys named in the PR title, branch or description
"""
from typing import List, Optional, Tuple

from .drift_affected import Hit
from .drift_changes import numbered
from .drift_models import (DiffHunk, DocMatch, DriftEvidence, DriftEvidenceKind, EntityChange,
                           FileChangeSummary, PullRequestAnalysis)

MAX_DIFF_LINES = 30
MAX_DIFF_CHARS = 1500
MAX_DOC_MATCHES = 5
CONTEXT = 2            # unchanged lines kept around the entity's changed lines


def _range(start: Optional[int], end: Optional[int]) -> Optional[Tuple[int, int]]:
    if start is None:
        return None
    return start, end if end and end >= start else start


def _clip(lines: List[str]) -> str:
    out, size = [], 0
    for line in lines[:MAX_DIFF_LINES]:
        if size + len(line) > MAX_DIFF_CHARS:
            break
        out.append(line)
        size += len(line) + 1
    if len(out) < len(lines):
        out.append(f"… ({len(lines) - len(out)} more line(s))")
    return "\n".join(out)


def diff_excerpt(hunks: List[DiffHunk], change: Optional[EntityChange]) -> Optional[Tuple[str, int, int]]:
    """Diff lines of `change` (the whole first hunk for a file-level finding):
    (excerpt, first line, last line) where lines are head-commit lines when known."""
    if not hunks:
        return None
    if change is None:
        h = hunks[0]
        head = f"@@ -{h.old_start},{h.old_lines} +{h.new_start},{h.new_lines} @@ {h.header}".rstrip()
        return _clip([head, *h.lines]), h.new_start, h.new_start + max(h.new_lines - 1, 0)
    new_r = _range(change.line_start, change.line_end)
    old_r = _range(change.old_line_start, change.old_line_end)
    if new_r and new_r[0] == new_r[1] and change.source == "patch":
        new_r = (new_r[0], new_r[0] + MAX_DIFF_LINES)   # patch mode knows only the first line
    if old_r and old_r[0] == old_r[1] and change.source == "patch":
        old_r = (old_r[0], old_r[0] + MAX_DIFF_LINES)
    for h in hunks:
        rows = list(numbered(h))
        inside = [i for i, (o, n, line) in enumerate(rows)
                  if (n is not None and new_r and new_r[0] <= n <= new_r[1])
                  or (o is not None and old_r and old_r[0] <= o <= old_r[1])]
        changed = [i for i in inside if rows[i][2][:1] in "+-"]
        if not changed:
            continue
        lo, hi = max(changed[0] - CONTEXT, inside[0]), min(changed[-1] + CONTEXT, inside[-1])
        picked = rows[lo:hi + 1]
        news = [n for _, n, _ in picked if n is not None]
        olds = [o for o, _, _ in picked if o is not None]
        head = f"@@ -{h.old_start},{h.old_lines} +{h.new_start},{h.new_lines} @@ {h.header}".rstrip()
        first = news[0] if news else (olds[0] if olds else None)
        last = news[-1] if news else (olds[-1] if olds else None)
        return _clip([head, *[line for _, _, line in picked]]), first, last
    return None


def signature_lines(change: EntityChange) -> List[str]:
    """Code evidence without a diff: signature before -> after (once when it did not change) and
    the docstring before -> after when that is what changed."""
    old, new = change.old_signature, change.new_signature
    if old and old == new:
        lines = [f"  {old}"]
    else:
        lines = ([f"- {old}"] if old else []) + ([f"+ {new}"] if new else [])
    if change.old_docstring != change.new_docstring:
        if change.old_docstring:
            lines.append(f'-     """{change.old_docstring}"""')
        if change.new_docstring:
            lines.append(f'+     """{change.new_docstring}"""')
    return lines


def build_evidence(hit: Hit, analysis: PullRequestAnalysis,
                   details: Optional[List[DocMatch]] = None) -> List[DriftEvidence]:
    pr = analysis.pull_request
    f: FileChangeSummary = hit.target.file
    change = hit.target.change
    out: List[DriftEvidence] = []

    diff = diff_excerpt(f.hunks, change)
    if diff is not None:
        text, first, last = diff
        out.append(DriftEvidence(id="X1", kind=DriftEvidenceKind.code_diff, path=f.path,
                                 line_start=first, line_end=last, excerpt=text,
                                 commit_sha=pr.head_sha, pull_request_number=pr.number))
    elif change is not None and (change.old_signature or change.new_signature):
        lines = signature_lines(change)
        out.append(DriftEvidence(id="X1", kind=DriftEvidenceKind.code_diff, path=f.path,
                                 line_start=change.line_start or change.old_line_start,
                                 line_end=change.line_end or change.old_line_end,
                                 excerpt="\n".join(lines), commit_sha=pr.head_sha,
                                 pull_request_number=pr.number))
    elif change is None:
        text = (f"deleted: {f.path}" if f.previous_path is None
                else f"renamed: {f.previous_path} -> {f.path}")
        out.append(DriftEvidence(id="X1", kind=DriftEvidenceKind.code_diff, path=f.path,
                                 excerpt=text, commit_sha=pr.head_sha, pull_request_number=pr.number))

    doc = hit.doc
    shown = sorted(hit.matches, key=lambda m: (not m.in_code, m.line))[:MAX_DOC_MATCHES]
    seen = {m.line for m in shown}
    shown += [m for m in hit.param_matches + (details or []) if m.line not in seen]
    for n, m in enumerate(sorted(shown, key=lambda m: m.line), start=1):
        out.append(DriftEvidence(id=f"D{n}", kind=DriftEvidenceKind.documentation, path=doc.path,
                                 document_id=doc.document_id, version=doc.version,
                                 line_start=m.line, line_end=m.line, excerpt=m.excerpt))
    if not hit.matches and hit.documents_file:
        # file-level / undocumented finding: point at the section itself
        first = next((i for i, line in enumerate(doc.lines) if line.strip()), 0)
        out.append(DriftEvidence(id="D1", kind=DriftEvidenceKind.documentation, path=doc.path,
                                 document_id=doc.document_id, version=doc.version,
                                 line_start=first + 1, line_end=first + 1,
                                 excerpt=doc.lines[first].strip() if doc.lines else None))

    if pr.head_sha or pr.url:
        out.append(DriftEvidence(id="C1", kind=DriftEvidenceKind.commit, commit_sha=pr.head_sha,
                                 pull_request_number=pr.number, url=pr.url,
                                 excerpt=f"PR #{pr.number}: {pr.title}".strip().rstrip(":")))
    for n, key in enumerate(analysis.tickets, start=1):
        out.append(DriftEvidence(id=f"T{n}", kind=DriftEvidenceKind.ticket, ticket=key))
    return out



