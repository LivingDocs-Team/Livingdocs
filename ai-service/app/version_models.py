"""Data models for versioned documentation (LD-195).

A *document* is the saved result of a generation job. Every change to it is a new, immutable
*version* (LD-195): the first one comes from the job, later ones from source changes (LD-128),
review actions (LD-134) or rollback (LD-189). Versions are never modified or deleted.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .models import Scope, now


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
