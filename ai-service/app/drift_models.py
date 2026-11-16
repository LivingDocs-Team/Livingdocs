"""Data models for documentation drift detection (LD-145) and classification (LD-151).

- LD-146  input: a Pull Request and its changed files; output: the code entities it changed
- LD-147  drift findings, classified Referential / Signature / Semantic with a severity
- LD-148  documentation affected by the change (saved documents + Markdown files of the repo)
- LD-149  evidence behind every finding: code diff, documentation passage, commit, ticket
- LD-151  finer classification: a `kind` inside each drift type, `breaking`, and the rules that
          fired (LD-152 referential, LD-153 signature, LD-154 semantic)
- LD-156  severity assessment: the rules behind each level, a score, the evidence for each rule,
          the level of each affected document and of the whole report
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
    ai_review: bool = True
    """LD-346: let the AI review every finding (offline explanation when no API key is set)."""

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


class ParameterChangeKind(str, Enum):
    removed = "removed"
    added = "added"
    renamed = "renamed"                    # same position and type, other name
    type_changed = "type_changed"
    default_removed = "default_removed"    # optional -> required
    default_added = "default_added"        # required -> optional
    default_changed = "default_changed"
    reordered = "reordered"


class ParameterChange(BaseModel):
    """LD-153: one change of a parameter (functions, methods, endpoints) or field (classes)."""
    name: str                              # name after the change (before, for a removed one)
    change: ParameterChangeKind
    old_name: Optional[str] = None         # renamed
    old_type: Optional[str] = None
    new_type: Optional[str] = None
    old_default: Optional[str] = None
    new_default: Optional[str] = None
    breaking: bool = False                 # existing callers / documented usage stop working


class SemanticSignal(BaseModel):
    """LD-154: what the new code does differently, read from the source or the diff."""
    kind: str                              # docstring | exceptions | status_codes | values
    removed: List[str] = Field(default_factory=list)
    added: List[str] = Field(default_factory=list)


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
    # LD-151 classification input
    aspects: List[str] = Field(default_factory=list)
    """signature_changed: parameters | return_type | http_method | request_body | response |
    kind | bases | fields"""
    parameter_changes: List[ParameterChange] = Field(default_factory=list)
    old_return_type: Optional[str] = None
    new_return_type: Optional[str] = None
    breaking: Optional[bool] = None            # signature_changed: does it break callers?
    signals: List[SemanticSignal] = Field(default_factory=list)   # behavior_changed


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
    kind: str = "name"
    """name | path | module | line_ref | parameter | type | default | exception | status_code |
    value | docstring (LD-151: what the documentation still says)"""
    note: Optional[str] = None         # e.g. the new line range of a stale line reference


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
    severity: Optional["Severity"] = None    # LD-158: most severe finding in this part
    findings: int = 0


# ---------- Findings (LD-147) and evidence (LD-149) ----------

class DriftType(str, Enum):
    referential = "referential"        # documentation names code that no longer exists / moved
    signature = "signature"            # documented parameters, types or contract changed
    semantic = "semantic"              # behaviour changed, or new code is not documented


DRIFT_KINDS: Dict[str, List[str]] = {
    # LD-152
    "referential": ["entity_removed", "endpoint_removed", "entity_renamed", "endpoint_moved",
                    "file_removed", "file_moved", "module_removed", "module_moved",
                    "line_reference_stale"],
    # LD-153
    "signature": ["endpoint_method_changed", "parameter_removed", "parameter_renamed",
                  "parameter_type_changed", "parameter_order_changed", "return_type_changed",
                  "endpoint_contract_changed", "class_contract_changed", "parameter_added",
                  "parameter_default_changed", "signature_changed"],
    # LD-154
    "semantic": ["status_codes_changed", "exceptions_changed", "values_changed",
                 "docstring_changed", "implementation_changed", "undocumented_entity"],
}
"""Kinds of each drift type (LD-151); in each list the more specific / severe kind first."""


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


class SeverityAdjustment(BaseModel):
    """LD-157: one rule that raised or lowered the level, with the evidence that proves it."""
    rule: str                          # id in app.drift_severity.RULES
    delta: int                         # +1 / -1 level
    label: str
    reason: str
    evidence: List[str] = Field(default_factory=list)   # DriftEvidence ids (X1, D2, ...)


class SeverityAssessment(BaseModel):
    """LD-156: why a finding has its severity."""
    level: Severity
    score: int                         # 0-100, inside the level's band (LD-158)
    base_rule: str
    base_level: Severity
    base_label: str
    base_reason: str
    base_evidence: List[str] = Field(default_factory=list)
    adjustments: List[SeverityAdjustment] = Field(default_factory=list)
    capped_at: Optional[Severity] = None
    summary: str = ""                  # one line: "High: breaking change (medium), ... (+1)."


class AIVerdict(str, Enum):
    confirmed = "confirmed"            # the documentation is outdated, as the rules found
    disputed = "disputed"              # the AI thinks the documentation is still correct
    uncertain = "uncertain"            # the evidence does not settle it
    not_reviewed = "not_reviewed"      # offline mode, or the AI gave no valid answer


class AIDriftReview(BaseModel):
    """LD-346: AI second opinion on one finding. It never changes the rule-based type or severity;
    reviewers see it and decide (resolution below)."""
    mode: str = "offline"              # ai | offline
    verdict: AIVerdict = AIVerdict.not_reviewed
    explanation: str = ""              # plain-language explanation of the drift
    evidence: List[str] = Field(default_factory=list)   # DriftEvidence ids the explanation cites
    suggested_update: Optional[str] = None               # replacement text for the documentation
    model: Optional[str] = None
    invalid_citations: List[str] = Field(default_factory=list)   # LD-356: ids not in the evidence


class ResolutionStatus(str, Enum):
    open = "open"                      # not handled yet
    acknowledged = "acknowledged"      # someone will update the documentation
    resolved = "resolved"              # the documentation was updated
    dismissed = "dismissed"            # not a real drift (a reason is required)


class ResolutionEvent(BaseModel):
    status: ResolutionStatus
    actor: Optional[str] = None
    note: Optional[str] = None
    at: datetime = Field(default_factory=now)


class FindingResolution(BaseModel):
    """LD-346: review and resolution of one finding, with its history."""
    status: ResolutionStatus = ResolutionStatus.open
    actor: Optional[str] = None
    note: Optional[str] = None
    updated_at: Optional[datetime] = None
    history: List[ResolutionEvent] = Field(default_factory=list)


class ResolutionUpdate(BaseModel):
    status: ResolutionStatus
    actor: Optional[str] = Field(default=None, max_length=200)
    note: Optional[str] = Field(default=None, max_length=2000)


class ReviewStatus(str, Enum):
    not_required = "not_required"      # no drift
    pending = "pending"                # every finding still open
    in_progress = "in_progress"
    completed = "completed"            # no finding open


class ReviewProgress(BaseModel):
    status: ReviewStatus = ReviewStatus.not_required
    open: int = 0
    acknowledged: int = 0
    resolved: int = 0
    dismissed: int = 0
    ai_mode: str = "offline"
    ai_confirmed: int = 0
    ai_disputed: int = 0
    ai_uncertain: int = 0


class DriftFinding(BaseModel):
    id: str                            # F1, F2, ...
    type: DriftType
    kind: str = ""                     # LD-151, one of DRIFT_KINDS[type]
    breaking: bool = False             # documented usage no longer works (wrong call / URL)
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)   # LD-356: always bounded (confidence.bounded)
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
    rules: List[str] = Field(default_factory=list)   # LD-151: classification rules that applied
    severity_assessment: Optional[SeverityAssessment] = None   # LD-156
    ai_review: Optional[AIDriftReview] = None                  # LD-346
    resolution: FindingResolution = Field(default_factory=FindingResolution)   # LD-346

class DriftStatus(str, Enum):
    no_drift = "no_drift"
    drift_detected = "drift_detected"


class DriftSummary(BaseModel):
    findings: int = 0
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_severity: Dict[str, int] = Field(default_factory=dict)
    by_kind: Dict[str, int] = Field(default_factory=dict)       # LD-151, only kinds found
    breaking: int = 0                                          # findings with breaking = True
    highest_severity: Optional[Severity] = None
    severity_score: int = 0                                    # LD-158: highest finding score
    recommendation: Optional[str] = None                       # action for highest_severity
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
    review: ReviewProgress = Field(default_factory=ReviewProgress)   # LD-346
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
    review: ReviewProgress = Field(default_factory=ReviewProgress)   # LD-346
    created_at: datetime


AffectedDocument.model_rebuild()
