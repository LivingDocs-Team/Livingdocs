"""Data models: input from the code analyzer (LD-328), templates, and generation jobs."""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Input: source code analyzed by LD-328 (see CONTRACT.md) ----------

class Parameter(BaseModel):
    name: str = Field(min_length=1)
    type: Optional[str] = None
    default: Optional[str] = None
    description: Optional[str] = None


class Function(BaseModel):
    name: str = Field(min_length=1)
    signature: Optional[str] = None
    parameters: List[Parameter] = Field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    source: Optional[str] = None  # optional code snippet, helps the AI explain logic


class ClassInfo(BaseModel):
    name: str = Field(min_length=1)
    bases: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    methods: List[Function] = Field(default_factory=list)


class Endpoint(BaseModel):
    http_method: str
    path: str = Field(min_length=1)
    handler: Optional[str] = None
    parameters: List[Parameter] = Field(default_factory=list)
    request_body: Optional[str] = None
    response: Optional[str] = None

    @field_validator("http_method")
    @classmethod
    def _check_method(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in HTTP_METHODS:
            raise ValueError(f"invalid HTTP method '{v}'")
        return v


class AnalysisStatus(str, Enum):
    ok = "ok"
    empty = "empty"              # file has no content
    invalid = "invalid"          # parse error / not valid source
    unsupported = "unsupported"  # language not supported by the analyzer


class FileAnalysis(BaseModel):
    path: str = Field(min_length=1)
    language: Optional[str] = None
    module: Optional[str] = None
    status: AnalysisStatus = AnalysisStatus.ok
    error: Optional[str] = None       # analyzer message when status != ok
    classes: List[ClassInfo] = Field(default_factory=list)
    functions: List[Function] = Field(default_factory=list)
    endpoints: List[Endpoint] = Field(default_factory=list)

    def entity_count(self) -> int:
        methods = sum(len(c.methods) for c in self.classes)
        return len(self.classes) + methods + len(self.functions) + len(self.endpoints)


class Scope(str, Enum):
    file = "file"
    module = "module"
    repository = "repository"


class GenerateRequest(BaseModel):
    scope: Scope
    target: str = Field(min_length=1)          # file path, module name or repository name
    files: List[FileAnalysis] = Field(min_length=1)
    template_id: str = "default"
    output_language: str = "vi"                # "vi" or "en"

    @field_validator("output_language")
    @classmethod
    def _check_lang(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"vi", "en"}:
            raise ValueError("output_language must be 'vi' or 'en'")
        return v

    @field_validator("files")
    @classmethod
    def _unique_paths(cls, files: List[FileAnalysis]) -> List[FileAnalysis]:
        paths = [f.path for f in files]
        dupes = sorted({p for p in paths if paths.count(p) > 1})
        if dupes:
            raise ValueError(f"duplicate file paths: {', '.join(dupes)}")
        return files


# ---------- Managed templates ----------

class TemplateIn(BaseModel):
    name: str
    description: str = ""
    instructions: str                 # how the AI should write the docs
    sections: List[str]               # ordered headings each file doc must contain


class Template(TemplateIn):
    id: str
    built_in: bool = False


# ---------- Generation jobs (status + result) ----------

class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class FileResultStatus(str, Enum):
    generated = "generated"   # documented by the AI
    offline = "offline"       # documented without AI (no API key configured)
    fallback = "fallback"     # AI failed, documented from analysis data only
    skipped = "skipped"       # analyzer could not process the file
    failed = "failed"         # unexpected error for this file


class FileResult(BaseModel):
    path: str
    status: FileResultStatus
    message: Optional[str] = None


class Job(BaseModel):
    id: str
    scope: Scope
    target: str
    template_id: str
    status: JobStatus = JobStatus.pending
    progress: float = 0.0             # 0.0 -> 1.0
    message: str = "Queued"
    files_total: int = 0
    files_done: int = 0
    file_results: List[FileResult] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    result: Optional[str] = None      # generated Markdown
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
