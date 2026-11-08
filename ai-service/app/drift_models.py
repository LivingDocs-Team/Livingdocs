"""Data models for documentation drift detection (LD-145).

- LD-146  input: a Pull Request and its changed files; output: the code entities it changed
- LD-147  drift findings, classified Referential / Signature / Semantic with a severity
- LD-148  documentation affected by the change (saved documents + Markdown files of the repo)
- LD-149  evidence behind every finding: code diff, documentation passage, commit, ticket
"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from .models import ContextDocument, FileAnalysis, now


# ---------- Input (LD-146) ----------

class ChangeStatus(str, Enum):
    """Same values as `status` of GitHub's "list pull request files" API."""
    added = "added"
    modified = "modified"
    removed = "removed"
    renamed = "renamed"
    copied = "copied"
    changed = "changed"        # GitHub: only the file mode changed
    unchanged = "unchanged"


class PullRequestInfo(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(default="", max_length=500)
    body: Optional[str] = Field(default=None, max_length=20_000)
    url: Optional[str] = Field(default=None, max_length=500)
    author: Optional[str] = Field(default=None, max_length=200)
    head_branch: Optional[str] = Field(default=None, max_length=300)
    base_branch: Optional[str] = Field(default=None, max_length=300)
    head_sha: Optional[str] = Field(default=None, max_length=64)   # commit the PR is checked at
    base_sha: Optional[str] = Field(default=None, max_length=64)


class ChangedFile(BaseModel):
    """One file of the Pull Request.

    `patch` is the unified diff GitHub returns for the file. `before` / `after` are the code
    analyzer's results (LD-328, see CONTRACT.md) for the file at the base and head commit; with
    them, entity changes are exact. With only the patch, they are read from the diff lines."""
    path: str = Field(min_length=1)
    status: ChangeStatus = ChangeStatus.modified
    previous_path: Optional[str] = None
    patch: Optional[str] = Field(default=None, max_length=1_000_000)
    before: Optional[FileAnalysis] = None
    after: Optional[FileAnalysis] = None


class DriftAnalyzeRequest(BaseModel):
    repository: Optional[str] = Field(default=None, max_length=300)   # "owner/name"
    pull_request: PullRequestInfo
    files: List[ChangedFile] = Field(min_length=1)
    docs: List[ContextDocument] = Field(default_factory=list)
    """Markdown files of the repository (README, docs/...) to check besides saved documents."""
    document_ids: Optional[List[str]] = None
    """Saved documents to check; None = every saved document."""

    @field_validator("files")
    @classmethod
    def _unique_paths(cls, files: List[ChangedFile]) -> List[ChangedFile]:
        paths = [f.path for f in files]
        dupes = sorted({p for p in paths if paths.count(p) > 1})
        if dupes:
            raise ValueError(f"duplicate file paths: {', '.join(dupes)}")
        return files


# ---------- Pull Request analysis (LD-146) ----------

class DiffHunk(BaseModel):
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    header: str = ""                       # text after the second @@ (enclosing def/class)
    lines: List[str] = Field(default_factory=list)   # raw lines with their ' ', '+', '-' prefix


class EntityChangeType(str, Enum):
    added = "added"
    removed = "removed"
    renamed = "renamed"
    signature_changed = "signature_changed"   # parameters, return type, bases, endpoint contract
    behavior_changed = "behavior_changed"     # body or docstring changed, same signature


class EntityChange(BaseModel):
    path: str                                  # file at the head commit
    previous_path: Optional[str] = None        # file at the base commit, when renamed
    kind: str                                  # class | method | function | endpoint
    name: str                                  # Class | Class.method | function | "GET /path"
    change: EntityChangeType
    old_name: Optional[str] = None             # renamed: the name before
    old_signature: Optional[str] = None
    new_signature: Optional[str] = None
    old_docstring: Optional[str] = None        # only when the docstring changed (analysis mode)
    new_docstring: Optional[str] = None
    details: List[str] = Field(default_factory=list)       # what exactly changed, readable
    removed_parameters: List[str] = Field(default_factory=list)
    added_parameters: List[str] = Field(default_factory=list)
    line_start: Optional[int] = None           # head commit
    line_end: Optional[int] = None
    old_line_start: Optional[int] = None       # base commit
    old_line_end: Optional[int] = None
    changed_lines: int = 0                     # diff lines inside the entity
    source: str = "analysis"                   # analysis (before/after) | patch (diff only)


class FileChangeSummary(BaseModel):
    path: str
    status: ChangeStatus
    previous_path: Optional[str] = None
    language: Optional[str] = None
    additions: int = 0
    deletions: int = 0
    hunks: List[DiffHunk] = Field(default_factory=list)
    entity_changes: List[EntityChange] = Field(default_factory=list)
    method: str = "none"                       # analysis | patch | none
    warnings: List[str] = Field(default_factory=list)


class PullRequestAnalysis(BaseModel):
    repository: Optional[str] = None
    pull_request: PullRequestInfo
    tickets: List[str] = Field(default_factory=list)       # Jira keys found in title/branch/body
    files: List[FileChangeSummary] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    entity_changes: int = 0


# ---------- Affected documentation (LD-148) ----------

class DocSource(str, Enum):
    document = "document"              # a saved, versioned document of the AI service
    repository = "repository"          # a Markdown file sent in the request (README, docs/...)


class DocMatch(BaseModel):
    """One place where the documentation refers to changed code."""
    term: str                          # text found (entity name, endpoint, file path, parameter)
    target: str                        # entity name or file path it stands for
    line: int                          # 1-based line in the document / section text
    excerpt: str
    in_code: bool = False              # inside `code`, a code block or a heading
    exact: bool = True                 # full name / path (False: bare method name or file name)


class AffectedDocument(BaseModel):
    source: DocSource
    path: str                          # section path (saved document) or Markdown file path
    document_id: Optional[str] = None
    title: Optional[str] = None
    version: Optional[int] = None
    documents_file: Optional[str] = None
    """Changed source file this section was generated from (saved documents only)."""
    reasons: List[str] = Field(default_factory=list)
    matches: List[DocMatch] = Field(default_factory=list)


# ---------- Findings (LD-147) and evidence (LD-149) ----------

class DriftType(str, Enum):
    referential = "referential"        # documentation names code that no longer exists / moved
    signature = "signature"            # documented parameters, types or contract changed
    semantic = "semantic"              # behaviour changed, or new code is not documented


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


SEVERITY_ORDER = [Severity.low, Severity.medium, Severity.high, Severity.critical]


class DriftEvidenceKind(str, Enum):
    code_diff = "code_diff"
    documentation = "documentation"
    commit = "commit"
    ticket = "ticket"


class DriftEvidence(BaseModel):
    id: str                            # X1 (diff), D1 (doc), C1 (commit), T1 (ticket)
    kind: DriftEvidenceKind
    path: Optional[str] = None
    document_id: Optional[str] = None
    version: Optional[int] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    excerpt: Optional[str] = None
    commit_sha: Optional[str] = None
    pull_request_number: Optional[int] = None
    url: Optional[str] = None
    ticket: Optional[str] = None


class DriftFinding(BaseModel):
    id: str                            # F1, F2, ...
    type: DriftType
    severity: Severity
    confidence: float                  # 0-1
    confidence_level: str              # high | medium | low (same thresholds as LD-340)
    entity: Optional[str] = None       # changed code entity (None for a whole-file finding)
    entity_kind: Optional[str] = None
    change: str                        # EntityChangeType or file_removed / file_renamed
    file: str                          # changed source file
    document: AffectedDocument         # where the stale documentation is (matches of this finding)
    message: str
    before: Optional[str] = None       # signature / name / path documented so far
    after: Optional[str] = None        # what the code has now
    suggestion: str
    evidence: List[DriftEvidence] = Field(default_factory=list)
    factors: Dict[str, float] = Field(default_factory=dict)


class DriftStatus(str, Enum):
    no_drift = "no_drift"
    drift_detected = "drift_detected"


class DriftSummary(BaseModel):
    findings: int = 0
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_severity: Dict[str, int] = Field(default_factory=dict)
    highest_severity: Optional[Severity] = None
    affected_documents: int = 0
    changed_files: int = 0
    entity_changes: int = 0


class DriftReport(BaseModel):
    id: str
    status: DriftStatus
    repository: Optional[str] = None
    pull_request: PullRequestInfo
    tickets: List[str] = Field(default_factory=list)
    summary: DriftSummary
    findings: List[DriftFinding] = Field(default_factory=list)
    affected_documents: List[AffectedDocument] = Field(default_factory=list)
    analysis: PullRequestAnalysis
    warnings: List[str] = Field(default_factory=list)
    method: str = ""
    created_at: datetime = Field(default_factory=now)


class DriftReportSummary(BaseModel):
    """Row of GET /drift/reports (without findings and analysis)."""
    id: str
    status: DriftStatus
    repository: Optional[str] = None
    pull_request_number: int
    pull_request_title: str = ""
    head_sha: Optional[str] = None
    summary: DriftSummary
    created_at: datetime
