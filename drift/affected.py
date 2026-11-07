"""Identify affected documentation (LD-148).

For every code change of the PR, find the documents that talk about the changed code:
by entity name, by HTTP route, or by file path. A reference is only *a candidate*;
`detector.py` decides whether the document is really out of date.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .doc_scanner import DocIndex, DocReference, is_distinctive
from .models import ChangeType, EntityChange, FileChange, FileStatus, PullRequestAnalysis


@dataclass
class AffectedReference:
    reference: DocReference
    via: str                                   # "name" | "route" | "path"
    change: Optional[EntityChange] = None
    file_change: Optional[FileChange] = None
    matched_name: str = ""                     # the name / route / path that was found
    strength: float = 0.0                      # how sure we are that the text is about this code

    @property
    def subject(self) -> str:
        if self.change is not None:
            return self.change.name
        return self.file_change.path if self.file_change else ""


@dataclass
class AffectedDocument:
    path: str
    updated_in_pr: bool = False
    references: List[AffectedReference] = field(default_factory=list)

    @property
    def subjects(self) -> List[str]:
        return sorted({r.subject for r in self.references if r.subject})


def reference_strength(ref: DocReference, name: str) -> float:
    """How likely a text match really is about the code entity (0..1)."""
    distinctive = is_distinctive(name)
    if ref.kind in ("code_span", "heading", "link"):
        return 0.9 if distinctive else 0.7
    if ref.kind == "code_block":
        called = ref.text[ref.col_end:ref.col_end + 1] == "("
        if distinctive:
            return 0.85
        return 0.6 if called else 0.0
    return 0.55 if distinctive else 0.0     # plain prose: only distinctive names


def _is_member_access(ref: DocReference) -> bool:
    rest = ref.text[ref.col_end:]
    return len(rest) > 1 and rest[0] == "." and (rest[1].isalpha() or rest[1] == "_") \
        and not re.match(r"\.(?:py|java|md|json|ya?ml|js|ts|txt|xml|html)\b", rest)


def names_of(change: EntityChange) -> List[str]:
    names: List[str] = []
    for ent in (change.before, change.after):
        if ent is not None and ent.name not in names:
            names.append(ent.name)
    return names


def routes_of(change: EntityChange) -> List[str]:
    routes: List[str] = []
    for ent in (change.before, change.after):
        if ent is not None:
            routes += [r for r in ent.routes if r not in routes]
    return routes


def identify_affected_documentation(index: DocIndex, analysis: PullRequestAnalysis
                                    ) -> List[AffectedDocument]:
    """Documents (at the PR head) that mention changed code, with every reference found."""
    touched = set(analysis.doc_files_changed)
    by_doc: Dict[str, AffectedDocument] = {}
    seen: Set[Tuple[str, int, int, str, str]] = set()

    spans: Dict[Tuple[str, int, str], List[Tuple[int, int]]] = {}

    def add(ref: DocReference, via: str, strength: float, matched: str,
            change: Optional[EntityChange] = None, fc: Optional[FileChange] = None) -> None:
        subject = change.name if change else (fc.path if fc else "")
        key = (ref.doc_path, ref.line, ref.col_start, via, subject)
        if key in seen or strength <= 0:
            return
        covered = spans.setdefault((ref.doc_path, ref.line, subject), [])
        if via == "name" and any(a <= ref.col_start and ref.col_end <= b for a, b in covered):
            return  # `Cart.add` already matched; do not also report its bare `add`
        covered.append((ref.col_start, ref.col_end))
        seen.add(key)
        doc = by_doc.setdefault(ref.doc_path, AffectedDocument(ref.doc_path, ref.doc_path in touched))
        doc.references.append(AffectedReference(ref, via, change, fc, matched, strength))

    for change in analysis.entity_changes:
        if change.change_type == ChangeType.MODIFIED and not change.api_changed:
            continue  # implementation-only edit: documentation of the API stays valid
        searched = list(names_of(change))
        if change.kind == "method":      # docs often write `cart.add_item(...)` instead of `Cart.add_item`
            for n in names_of(change):
                short = n.rsplit(".", 1)[-1]
                if is_distinctive(short) and short not in searched:
                    searched.append(short)
        for name in searched:
            for ref in index.find_name(name):
                if change.kind == "class" and _is_member_access(ref):
                    continue         # `Cart.add` is about the method, not about the class
                add(ref, "name", reference_strength(ref, name), name, change=change)
        for route in routes_of(change):
            for ref in index.find_route(route):
                add(ref, "route", 0.9, route, change=change)

    # an added endpoint is "affected" through its siblings: docs listing the other routes of the file
    for fc in analysis.files:
        if fc.is_doc or not fc.language:
            continue
        if fc.status in (FileStatus.DELETED, FileStatus.RENAMED):
            for ref in index.find_path(fc.old_path or fc.path):
                add(ref, "path", 0.9 if ref.kind == "link" else 0.85, fc.old_path or fc.path, fc=fc)
        elif fc.status == FileStatus.MODIFIED:
            for ref in index.find_path(fc.path):
                add(ref, "path", 0.5, fc.path, fc=fc)
    # deleted / renamed documents: links from other documents are broken now
    for fc in analysis.files:
        if fc.is_doc and fc.status in (FileStatus.DELETED, FileStatus.RENAMED):
            for ref in index.find_path(fc.old_path or fc.path):
                if ref.doc_path != (fc.old_path or fc.path):
                    add(ref, "path", 0.9, fc.old_path or fc.path, fc=fc)

    docs = sorted(by_doc.values(), key=lambda d: d.path)
    for d in docs:
        d.references.sort(key=lambda r: (r.reference.line, r.reference.col_start))
    return docs
