"""Data models for versioned documentation (LD-195, LD-128, LD-134, LD-189).

A *document* is the saved result of a generation job. Every change to it is a new, immutable
*version* (LD-195): the first one comes from the job, later ones from source changes (LD-128),
review actions (LD-134) or rollback (LD-189). Versions are never modified or deleted.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from .models import ContextDocument, FileAnalysis, Scope, now


def _alias(*names: str, default=None, **kw):
    """LD-116 (Java) sends camelCase; Python callers may send snake_case. Accept both."""
    return Field(default=default, validation_alias=AliasChoices(*names), **kw)


# ---------- Input: a source change detected by LD-116 ----------

class ChangeType(str, Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    REMOVED = "REMOVED"
    RENAMED = "RENAMED"


class ChangedEntity(BaseModel):
    """A class / method / function / endpoint touched by the change (LD-116 EntityResponse)."""
    model_config = ConfigDict(populate_by_name=True)
    kind: str
    name: str
    change: str
    start_line: Optional[int] = _alias("start_line", "startLine")
    end_line: Optional[int] = _alias("end_line", "endLine")


class ChangedFile(BaseModel):
    """One file of a source change (LD-116 FileResponse)."""
    model_config = ConfigDict(populate_by_name=True)
    path: str = Field(min_length=1)
    previous_path: Optional[str] = _alias("previous_path", "previousPath")
    change: ChangeType
    language: Optional[str] = None
    additions: Optional[int] = None
    deletions: Optional[int] = None
    skipped_reason: Optional[str] = _alias("skipped_reason", "skippedReason")
    entities: List[ChangedEntity] = Field(default_factory=list)

    @field_validator("change", mode="before")
    @classmethod
    def _upper(cls, v):
        return v.strip().upper() if isinstance(v, str) else v


class SourceChange(BaseModel):
    """A commit or Pull Request head detected by LD-116 (SourceChangeResponse)."""
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(min_length=1)
    trigger: Optional[str] = None                     # COMMIT | PULL_REQUEST
    commit_sha: Optional[str] = _alias("commit_sha", "commitSha")
    pull_request_number: Optional[int] = _alias("pull_request_number", "pullRequestNumber")
    files: List[ChangedFile] = Field(min_length=1)

    @field_validator("id", mode="before")
    @classmethod
    def _id_text(cls, v):
        return str(v) if v is not None else v

    def ref(self) -> "SourceChangeRef":
        return SourceChangeRef(id=self.id, trigger=self.trigger, commit_sha=self.commit_sha,
                               pull_request_number=self.pull_request_number)


class SourceChangeRef(BaseModel):
    id: str
    trigger: Optional[str] = None
    commit_sha: Optional[str] = None
    pull_request_number: Optional[int] = None


# ---------- Requests ----------

class _Actor(BaseModel):
    actor: Optional[str] = Field(default=None, max_length=200)   # who did it (user id / name)
    note: Optional[str] = Field(default=None, max_length=1000)


class DocumentCreate(_Actor):
    """Save the result of a completed generation job as version 1 of a new document."""
    job_id: str = Field(min_length=1)
    title: Optional[str] = Field(default=None, max_length=200)


class DocumentUpdateRequest(_Actor):
    """LD-128: update a document after a source change.

    `files` are the Code Analyzer results for the changed files *after* the change (ADDED,
    MODIFIED and RENAMED files). REMOVED files need no analysis."""
    source_change: SourceChange
    files: List[FileAnalysis] = Field(default_factory=list)
    context: List[ContextDocument] = Field(default_factory=list)

    @field_validator("files")
    @classmethod
    def _unique_paths(cls, files: List[FileAnalysis]) -> List[FileAnalysis]:
        paths = [f.path for f in files]
        dupes = sorted({p for p in paths if paths.count(p) > 1})
        if dupes:
            raise ValueError(f"duplicate file paths: {', '.join(dupes)}")
        return files


class ReviewRequest(_Actor):
    """Accept, dismiss or regenerate a proposed version (LD-134)."""


class EditRequest(_Actor):
    """Replace the content of a proposed or the current version (LD-134)."""
    content: str = Field(min_length=1, max_length=2_000_000)
    accept: bool = True            # True: the edited text becomes the current version at once


class RollbackRequest(_Actor):
    """Make an earlier accepted version current again (LD-189). History is kept."""
    version: int = Field(ge=1)


# ---------- Stored data ----------

class VersionStatus(str, Enum):
    proposed = "proposed"       # waiting for review (created from a source change or regeneration)
    accepted = "accepted"       # approved; the newest accepted one is the document's current version
    dismissed = "dismissed"     # rejected by a reviewer
    superseded = "superseded"   # replaced by a newer proposal before anyone reviewed it


class VersionOrigin(str, Enum):
    generated = "generated"         # first version, from a generation job
    source_change = "source_change"  # LD-128
    edit = "edit"                   # LD-134 manual edit
    regenerate = "regenerate"       # LD-134 regenerate a proposal (or rebase it)
    rollback = "rollback"           # LD-189 restore an earlier version


class FileSection(BaseModel):
    """Documentation of one source file inside a version."""
    path: str
    markdown: str
    status: str                     # generated | offline | fallback | manual | moved
    confidence: Optional[float] = None


class SkippedFile(BaseModel):
    path: str
    reason: str


class SectionAction(str, Enum):
    added = "added"
    updated = "updated"
    removed = "removed"
    renamed = "renamed"
    edited = "edited"


class SectionChange(BaseModel):
    """What a version changed compared with the version it was built on."""
    path: str
    action: SectionAction
    previous_path: Optional[str] = None
    entities: List[str] = Field(default_factory=list)   # changed code entities (from LD-116)


class VersionSummary(BaseModel):
    number: int
    status: VersionStatus
    origin: VersionOrigin
    base_version: Optional[int] = None      # version this one was built on
    restored_from: Optional[int] = None     # rollback: the version that was restored
    superseded_by: Optional[int] = None
    source_changes: List[SourceChangeRef] = Field(default_factory=list)
    changes: List[SectionChange] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    manual: bool = False                    # content was edited by hand
    note: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=now)
    decided_by: Optional[str] = None        # who accepted / dismissed it
    decided_at: Optional[datetime] = None


class DocumentVersion(VersionSummary):
    content: str
    sections: List[FileSection] = Field(default_factory=list)
    skipped: List[SkippedFile] = Field(default_factory=list)
    sections_match_content: bool = True
    """False when a manual edit could not be split back into per-file sections; a later update
    then rebuilds the text from `sections` and the hand edits are lost (a warning says so)."""


class Document(BaseModel):
    id: str
    title: str
    target: str
    scope: Scope
    template_id: str
    output_language: str
    source_job_id: Optional[str] = None
    current_version: int = 1               # newest accepted version
    pending_version: Optional[int] = None  # proposal waiting for review, if any
    versions_total: int = 1
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class HistoryAction(str, Enum):
    created = "created"
    proposed = "proposed"
    accepted = "accepted"
    edited = "edited"
    dismissed = "dismissed"
    regenerated = "regenerated"
    superseded = "superseded"
    rolled_back = "rolled_back"


class HistoryEvent(BaseModel):
    at: datetime = Field(default_factory=now)
    action: HistoryAction
    version: int
    related_version: Optional[int] = None
    actor: Optional[str] = None
    note: Optional[str] = None


class UpdateResult(BaseModel):
    """Response of LD-128. `proposal` is null when no documented file was affected."""
    document_id: str
    proposal: Optional[DocumentVersion] = None
    message: str
    warnings: List[str] = Field(default_factory=list)


# ---------- Comparison (LD-134) ----------

class FileDiff(BaseModel):
    path: str
    change: str                  # added | removed | modified | unchanged
    added_lines: int = 0
    removed_lines: int = 0


class CompareResult(BaseModel):
    document_id: str
    from_version: int
    to_version: int
    files: List[FileDiff] = Field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0
    identical: bool = False
    unified_diff: str = ""
