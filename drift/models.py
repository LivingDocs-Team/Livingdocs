"""Shared data model of the documentation drift pipeline (LD-145).

Pipeline:  PR diff --(LD-146)--> EntityChange --(LD-148)--> AffectedReference
           --(LD-147)--> DriftFinding --(LD-149)--> DriftEvidence / report
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class FileStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class ChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    RENAMED = "renamed"   # same file, new name
    MOVED = "moved"       # same name, other file


@dataclass(frozen=True)
class Param:
    name: str
    type: Optional[str] = None
    has_default: bool = False
    variadic: str = ""    # "" | "*" | "**"

    @property
    def required(self) -> bool:
        return not self.has_default and not self.variadic


@dataclass(frozen=True)
class Entity:
    """A documentable code entity: class, function or method."""
    kind: str                       # "class" | "function" | "method"
    name: str                       # qualified inside the file: Class.method
    file: str
    line: int
    end_line: int
    signature: str
    params: Tuple[Param, ...] = ()
    return_type: Optional[str] = None
    routes: Tuple[str, ...] = ()    # "GET /orders/{id}"
    bases: Tuple[str, ...] = ()
    fields: Tuple[str, ...] = ()    # class attributes: "name: type"
    body_digest: str = ""
    language: str = "python"
    source: str = field(default="", compare=False, repr=False)

    @property
    def short_name(self) -> str:
        return self.name.rsplit(".", 1)[-1]

    @property
    def param_names(self) -> Tuple[str, ...]:
        return tuple(p.name for p in self.params)


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str] = field(default_factory=list)  # raw lines with their ' ', '+', '-' prefix

    @property
    def header(self) -> str:
        return f"@@ -{self.old_start},{self.old_count} +{self.new_start},{self.new_count} @@"

    def overlaps(self, line: int, end_line: int, side: str = "new") -> bool:
        start, count = (self.new_start, self.new_count) if side == "new" else (self.old_start, self.old_count)
        hunk_end = start + max(count, 1) - 1
        return start <= end_line and line <= hunk_end


@dataclass
class FileChange:
    path: str                       # path after the change (before it for deleted files)
    status: FileStatus
    old_path: Optional[str] = None  # only for renamed files
    hunks: List[Hunk] = field(default_factory=list)
    binary: bool = False

    @property
    def language(self) -> Optional[str]:
        return language_of(self.path)

    @property
    def is_doc(self) -> bool:
        return is_doc_path(self.path)

    @property
    def added_lines(self) -> int:
        return sum(1 for h in self.hunks for l in h.lines if l.startswith("+"))

    @property
    def removed_lines(self) -> int:
        return sum(1 for h in self.hunks for l in h.lines if l.startswith("-"))

    def hunks_for(self, line: int, end_line: int, side: str = "new") -> List[Hunk]:
        return [h for h in self.hunks if h.overlaps(line, end_line, side)]


@dataclass
class EntityChange:
    change_type: ChangeType
    kind: str
    name: str
    file: str
    before: Optional[Entity] = None
    after: Optional[Entity] = None
    details: List[str] = field(default_factory=list)
    params_added: Tuple[str, ...] = ()
    params_removed: Tuple[str, ...] = ()
    params_changed: Tuple[str, ...] = ()
    return_changed: bool = False
    routes_added: Tuple[str, ...] = ()
    routes_removed: Tuple[str, ...] = ()
    members_added: Tuple[str, ...] = ()
    members_removed: Tuple[str, ...] = ()
    bases_changed: bool = False
    body_changed: bool = False
    renamed_from: Optional[str] = None
    moved_from: Optional[str] = None

    @property
    def signature_changed(self) -> bool:
        return bool(self.params_added or self.params_removed or self.params_changed or self.return_changed)

    @property
    def api_changed(self) -> bool:
        """True when the change can make documentation wrong (not only an implementation edit)."""
        if self.change_type != ChangeType.MODIFIED:
            return True
        return bool(self.signature_changed or self.routes_added or self.routes_removed
                    or self.members_added or self.members_removed or self.bases_changed)

    @property
    def old_name(self) -> Optional[str]:
        return self.before.name if self.before else None

    @property
    def new_name(self) -> Optional[str]:
        return self.after.name if self.after else None


@dataclass
class PullRequestAnalysis:
    files: List[FileChange] = field(default_factory=list)
    entity_changes: List[EntityChange] = field(default_factory=list)
    head_entities: Dict[str, List[Entity]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    base: Optional[str] = None
    head: Optional[str] = None

    @property
    def doc_files_changed(self) -> List[str]:
        return sorted(f.path for f in self.files if f.is_doc)

    @property
    def code_files_changed(self) -> List[str]:
        return sorted(f.path for f in self.files if f.language)

    def file_change(self, path: str) -> Optional[FileChange]:
        for f in self.files:
            if f.path == path or f.old_path == path:
                return f
        return None

    def summary(self) -> Dict[str, int]:
        counts = {t.value: 0 for t in ChangeType}
        for c in self.entity_changes:
            counts[c.change_type.value] += 1
        return {
            "files_changed": len(self.files),
            "code_files_changed": len(self.code_files_changed),
            "doc_files_changed": len(self.doc_files_changed),
            "entities_changed": len(self.entity_changes),
            "api_changes": sum(1 for c in self.entity_changes if c.api_changed),
            **{f"entities_{k}": v for k, v in counts.items()},
        }


CODE_EXTENSIONS = {".py": "python", ".java": "java"}
DOC_EXTENSIONS = (".md", ".markdown", ".mdx", ".rst")


def language_of(path: str) -> Optional[str]:
    lowered = path.lower()
    for ext, lang in CODE_EXTENSIONS.items():
        if lowered.endswith(ext):
            return lang
    return None


def is_doc_path(path: str) -> bool:
    return path.lower().endswith(DOC_EXTENSIONS)
