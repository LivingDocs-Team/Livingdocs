"""Data models: input from the code analyzer, templates, and generation jobs."""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Input: source code already analyzed (parsed) ----------

class Parameter(BaseModel):
    name: str
    type: Optional[str] = None
    default: Optional[str] = None
    description: Optional[str] = None


class Function(BaseModel):
    name: str
    signature: Optional[str] = None
    parameters: List[Parameter] = Field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    source: Optional[str] = None  # optional code snippet, helps the AI explain logic


class ClassInfo(BaseModel):
    name: str
    bases: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    methods: List[Function] = Field(default_factory=list)


class Endpoint(BaseModel):
    http_method: str            # GET, POST, ...
    path: str                   # /users/{id}
    handler: Optional[str] = None
    parameters: List[Parameter] = Field(default_factory=list)
    request_body: Optional[str] = None
    response: Optional[str] = None


class FileAnalysis(BaseModel):
    path: str
    language: Optional[str] = None
    module: Optional[str] = None
    classes: List[ClassInfo] = Field(default_factory=list)
    functions: List[Function] = Field(default_factory=list)
    endpoints: List[Endpoint] = Field(default_factory=list)


class Scope(str, Enum):
    file = "file"
    module = "module"
    repository = "repository"


class GenerateRequest(BaseModel):
    scope: Scope
    target: str                       # file path, module name or repository name
    files: List[FileAnalysis] = Field(min_length=1)
    template_id: str = "default"
    output_language: str = "vi"       # language of the generated docs


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
    result: Optional[str] = None      # generated Markdown
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
