"""Data models for versioned documentation (LD-195).

A *document* is the saved result of a generation job. Every change to it is a new, immutable
*version* (LD-195): the first one comes from the job, later ones from source changes (LD-128),
review actions (LD-134) or rollback (LD-189). Versions are never modified or deleted.
"""
from datetime import datetime
from enum import Enum
from typing import Literal, List, Optional

from pydantic import AwareDatetime, BaseModel, Field
from .models import FileAnalysis, JobReport, ReviewEvidenceResponse, Scope, SourceSnapshot, now


class SourceChangeRef(BaseModel):
    id: str
    trigger: Optional[str] = None
    commit_sha: Optional[str] = None
    pull_request_number: Optional[int] = None


# ---------- Requests ----------

class RevisionFileChange(BaseModel):
    path: str = Field(min_length=1)
    action: Literal["added", "updated", "removed", "renamed", "dependent"]
    previous_path: Optional[str] = None
    blob_sha: Optional[str] = Field(default=None, pattern="^[0-9a-fA-F]{40}$")


class RevisionReviewEvidence(ReviewEvidenceResponse):
    revision_files: List[RevisionFileChange] = Field(default_factory=list)


class RevisionDraftRequest(BaseModel):
    source_change_id: str = Field(min_length=1)
    trigger: str = Field(pattern="^(COMMIT|PULL_REQUEST)$")
    pull_request_number: Optional[int] = Field(default=None, ge=1)
    source_snapshot: SourceSnapshot
    base_version: int = Field(ge=1)
    files: List[FileAnalysis] = Field(max_length=20)
    file_changes: List[RevisionFileChange] = Field(default_factory=list, max_length=50)


class _Actor(BaseModel):
    actor: Optional[str] = Field(default=None, max_length=200)   # who did it (user id / name)
    note: Optional[str] = Field(default=None, max_length=1000)


class DocumentCreate(_Actor):
    """Save the result of a completed generation job as version 1 of a new document."""
    job_id: str = Field(min_length=1)
    title: Optional[str] = Field(default=None, max_length=200)


class InternalDocumentCreate(BaseModel):
    """Internal save request. Owner is taken from a trusted service header, never this body."""
    job_id: str = Field(min_length=1)
    title: Optional[str] = Field(default=None, max_length=200)
    note: Optional[str] = Field(default=None, max_length=1000)
    actor_role: Optional[str] = Field(default=None, min_length=1, max_length=40)


class DocumentContentEdit(BaseModel):
    content: str = Field(min_length=1, max_length=2_000_000)
    expected_version: int = Field(ge=1)
    note: Optional[str] = Field(default=None, max_length=1000)
    actor_role: Optional[str] = Field(default=None, min_length=1, max_length=40)


class InternalVersionDecision(BaseModel):
    replay: bool = False
    version: int = Field(ge=1)
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    note: Optional[str] = Field(default=None, max_length=1000)
class InternalRollbackRequest(BaseModel):
    source_version: int = Field(ge=1)
    note: Optional[str] = Field(default=None, max_length=1000)

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
    # LD-402: an edit or a rollback keeps the generation evidence (evidence_report, review_report,
    # source_snapshot) of the version it was made from; this is that version (None: its own)
    evidence_from_version: Optional[int] = None


class PreparedRevision(BaseModel):
    replacements: dict[str, FileSection] = Field(default_factory=dict)
    report: Optional[JobReport] = None


class RevisionDraftCommit(RevisionDraftRequest):
    prepared: PreparedRevision
    lease_expires_at: AwareDatetime


class DocumentVersion(VersionSummary):
    content: str
    owner_edit_from: Optional[int] = None
    saved_actor_role: Optional[str] = None
    drift_finding: Optional[dict] = None
    sections: List[FileSection] = Field(default_factory=list)
    revision_files: List[RevisionFileChange] = Field(default_factory=list)
    skipped: List[SkippedFile] = Field(default_factory=list)
    sections_match_content: bool = True
    evidence_report: Optional[JobReport] = None
    """False when a manual edit could not be split back into per-file sections; a later update
    then rebuilds the text from `sections` and the hand edits are lost (a warning says so)."""
    review_report: Optional[JobReport] = None
    source_snapshot: Optional[SourceSnapshot] = None



class InitialGenerationSave(BaseModel):
    job_id: str
    version: int
    actor_user_id: str
    actor_role: Optional[str]
    saved_at: AwareDatetime


class Document(BaseModel):
    id: str
    title: str
    target: str
    scope: Scope
    template_id: str
    template_version: Optional[int] = None  # LD-227: template version the document was generated with
    output_language: str
    source_job_id: Optional[str] = None
    initial_generation_save: Optional[InitialGenerationSave] = None
    # Absent on legacy documents; never backfilled from the untrusted historical actor field.
    owner_user_id: Optional[str] = None
    current_version: int = 1               # newest accepted version
    pending_version: Optional[int] = None  # proposal waiting for review, if any
    pending_revision: Optional[SourceSnapshot] = None
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
class VersionComparison(BaseModel):
    """Compare a pending documentation version with the latest approved version."""

    pending_version: DocumentVersion
    approved_version: Optional[DocumentVersion] = None
    has_approved_version: bool = False
    diff: str = ""
    changes: List[SectionChange] = Field(default_factory=list)


class ComparedVersion(BaseModel):
    """LD-184: one side of a comparison."""
    number: int
    status: VersionStatus
    origin: VersionOrigin
    created_at: datetime
    created_by: Optional[str] = None
    note: Optional[str] = None


class DocumentDiff(BaseModel):
    """LD-183: the difference between any two versions of one document (UC-30, BR-44).
    `from_version` is the older side (left), `to_version` the newer side (right)."""
    document_id: str
    from_version: ComparedVersion
    to_version: ComparedVersion
    identical: bool
    stats: "DiffStats"
    sections: List["SectionDiff"] = Field(default_factory=list)
    rows: List["DiffRow"] = Field(default_factory=list)


from .doc_diff import DiffRow, DiffStats, SectionDiff  # noqa: E402

DocumentDiff.model_rebuild()
