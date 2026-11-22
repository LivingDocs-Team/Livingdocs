"""LD-183 Documentation diff & comparison (LD-185 Implement Documentation Diff).

Compares two texts (two versions of a document) line by line and returns rows for a side-by-side
view (UC-30, BR-44):

    unchanged   the same line on both sides
    added       only in the newer text (LD-186)
    removed     only in the older text (LD-186)
    modified    a line that was edited: both sides, with the changed words marked (LD-187)

How lines are paired: difflib finds the blocks that stayed the same; inside a replaced block an
old and a new line are shown as one *modified* row when they are similar enough
(MODIFIED_SIMILARITY of their characters), otherwise as a removed and an added row. The changed
words of a modified row come from a second, word-level comparison.

Every row also carries the Markdown section (nearest `#` / `##` heading) it belongs to, so the
result can say which sections were added, removed or modified.
"""
import difflib
import re
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

MODIFIED_SIMILARITY = 0.5         # below this an edited line is shown as removed + added
HEADING = re.compile(r"^(#{1,2})\s+(.+?)\s*#*\s*$")
TOKEN = re.compile(r"\s+|\w+|[^\w\s]")
NO_SECTION = "(top of document)"


class DiffLineKind(str, Enum):
    unchanged = "unchanged"
    added = "added"
    removed = "removed"
    modified = "modified"


class InlineSegment(BaseModel):
    text: str
    changed: bool = False


class DiffRow(BaseModel):
    """One row of the side-by-side view; a side is None when the line does not exist there."""
    kind: DiffLineKind
    old_number: Optional[int] = None
    new_number: Optional[int] = None
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    old_segments: List[InlineSegment] = Field(default_factory=list)   # modified rows only
    new_segments: List[InlineSegment] = Field(default_factory=list)
    section: str = NO_SECTION


class DiffStats(BaseModel):
    added: int = 0
    removed: int = 0
    modified: int = 0
    unchanged: int = 0


class SectionStatus(str, Enum):
    added = "added"
    removed = "removed"
    modified = "modified"
    unchanged = "unchanged"


class SectionDiff(BaseModel):
    section: str
    status: SectionStatus
    added: int = 0
    removed: int = 0
    modified: int = 0


class TextDiff(BaseModel):
    identical: bool
    stats: DiffStats
    sections: List[SectionDiff] = Field(default_factory=list)   # in document order
    rows: List[DiffRow] = Field(default_factory=list)


def _lines(text: Optional[str]) -> List[str]:
    return (text or "").splitlines()


def inline_segments(old: str, new: str) -> Tuple[List[InlineSegment], List[InlineSegment]]:
    """Word-level difference of two lines: which parts of each side changed (LD-187)."""
    a, b = TOKEN.findall(old), TOKEN.findall(new)
    old_parts: List[InlineSegment] = []
    new_parts: List[InlineSegment] = []

    def add(parts: List[InlineSegment], text: str, changed: bool) -> None:
        if not text:
            return
        if parts and parts[-1].changed == changed:
            parts[-1].text += text
        else:
            parts.append(InlineSegment(text=text, changed=changed))

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        add(old_parts, "".join(a[i1:i2]), op != "equal")
        add(new_parts, "".join(b[j1:j2]), op != "equal")
    return old_parts, new_parts


def _similar(old: str, new: str) -> bool:
    if not old.strip() or not new.strip():
        return False
    return difflib.SequenceMatcher(None, old, new, autojunk=False).ratio() >= MODIFIED_SIMILARITY


def _replace_rows(old: List[str], new: List[str], i0: int, j0: int) -> List[DiffRow]:
    """Rows for a replaced block: pair similar lines in order, the rest are removed / added."""
    rows: List[DiffRow] = []
    i = j = 0
    while i < len(old) or j < len(new):
        if i < len(old) and j < len(new) and _similar(old[i], new[j]):
            o, n = inline_segments(old[i], new[j])
            rows.append(DiffRow(kind=DiffLineKind.modified, old_number=i0 + i + 1, new_number=j0 + j + 1,
                                old_text=old[i], new_text=new[j], old_segments=o, new_segments=n))
            i += 1
            j += 1
        elif i < len(old) and (j >= len(new) or not any(_similar(old[i], x) for x in new[j:j + 3])):
            rows.append(DiffRow(kind=DiffLineKind.removed, old_number=i0 + i + 1, old_text=old[i]))
            i += 1
        else:
            rows.append(DiffRow(kind=DiffLineKind.added, new_number=j0 + j + 1, new_text=new[j]))
            j += 1
    return rows


def _heading(line: Optional[str]) -> Optional[str]:
    m = HEADING.match(line or "")
    return m.group(2).strip() if m else None


def _assign_sections(rows: List[DiffRow]) -> None:
    old_section = new_section = NO_SECTION
    for r in rows:
        old_section = _heading(r.old_text) or old_section if r.old_text is not None else old_section
        new_section = _heading(r.new_text) or new_section if r.new_text is not None else new_section
        r.section = old_section if r.kind == DiffLineKind.removed else new_section


def _sections(rows: List[DiffRow]) -> List[SectionDiff]:
    old_heads = {_heading(r.old_text) for r in rows if r.old_text is not None} - {None}
    new_heads = {_heading(r.new_text) for r in rows if r.new_text is not None} - {None}
    found: Dict[str, SectionDiff] = {}
    for r in rows:
        s = found.setdefault(r.section, SectionDiff(section=r.section, status=SectionStatus.unchanged))
        if r.kind == DiffLineKind.added:
            s.added += 1
        elif r.kind == DiffLineKind.removed:
            s.removed += 1
        elif r.kind == DiffLineKind.modified:
            s.modified += 1
    for s in found.values():
        if s.section != NO_SECTION and s.section in new_heads and s.section not in old_heads:
            s.status = SectionStatus.added
        elif s.section != NO_SECTION and s.section in old_heads and s.section not in new_heads:
            s.status = SectionStatus.removed
        elif s.added or s.removed or s.modified:
            s.status = SectionStatus.modified
    return list(found.values())


def diff_texts(old: Optional[str], new: Optional[str]) -> TextDiff:
    """Side-by-side difference of two texts (older first)."""
    a, b = _lines(old), _lines(new)
    rows: List[DiffRow] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            rows += [DiffRow(kind=DiffLineKind.unchanged, old_number=i1 + k + 1, new_number=j1 + k + 1,
                             old_text=a[i1 + k], new_text=b[j1 + k]) for k in range(i2 - i1)]
        elif op == "delete":
            rows += [DiffRow(kind=DiffLineKind.removed, old_number=k + 1, old_text=a[k]) for k in range(i1, i2)]
        elif op == "insert":
            rows += [DiffRow(kind=DiffLineKind.added, new_number=k + 1, new_text=b[k]) for k in range(j1, j2)]
        else:
            rows += _replace_rows(a[i1:i2], b[j1:j2], i1, j1)
    _assign_sections(rows)
    stats = DiffStats(**{k.value: sum(1 for r in rows if r.kind == k) for k in DiffLineKind})
    return TextDiff(identical=a == b, stats=stats, sections=_sections(rows), rows=rows)
