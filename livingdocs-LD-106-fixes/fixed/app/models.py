from typing import List, Optional
from pydantic import BaseModel, Field

# --- Contract với ai-service (xem ai-service/CONTRACT.md) ---
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
    source: Optional[str] = None
    lineno: Optional[int] = None
    end_lineno: Optional[int] = None


# --- ERR-BE-02: Khai báo thông tin thuộc tính/trường dữ liệu ---
class FieldInfo(BaseModel):
    name: str
    type: Optional[str] = None
    default: Optional[str] = None
    description: Optional[str] = None

# --- ERR-BE-01 & ERR-BE-02: Bổ sung fields, lineno, end_lineno ---
class ClassInfo(BaseModel):
    name: str
    bases: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    methods: List[Function] = Field(default_factory=list)
    fields: List[FieldInfo] = Field(default_factory=list)  # ERR-BE-02
    lineno: Optional[int] = None                          # ERR-BE-01
    end_lineno: Optional[int] = None                      # ERR-BE-01

class Endpoint(BaseModel):
    http_method: str
    path: str
    handler: Optional[str] = None
    parameters: List[Parameter] = Field(default_factory=list)
    request_body: Optional[str] = None
    response: Optional[str] = None
    lineno: Optional[int] = None                          # ERR-BE-01
    end_lineno: Optional[int] = None                      # ERR-BE-01

# --- LD-395: Kết quả phân tích từng file + request/response của /analyze-repo ---
class FileAnalysis(BaseModel):
    path: str
    language: Optional[str] = None
    module: Optional[str] = None
    status: str = "ok"  # ok | empty | invalid | unsupported
    error: Optional[str] = None
    classes: List[ClassInfo] = Field(default_factory=list)
    functions: List[Function] = Field(default_factory=list)
    endpoints: List[Endpoint] = Field(default_factory=list)


class SourceFileInput(BaseModel):
    path: str = Field(min_length=1)
    content: str = ""
    language: Optional[str] = None


class AnalyzeRequest(BaseModel):
    scope: str = "repository"
    target: str = Field(min_length=1)
    # files rỗng -> HTTP 422 (khớp tests/test_api.py, tests/test_analysis.py)
    files: List[SourceFileInput] = Field(min_length=1)
    # LD-328 (cũ): danh sách đường dẫn; chấp nhận nhưng không dùng để đọc đĩa
    file_paths: List[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    scope: str
    target: str
    files: List[FileAnalysis]


# --- ERR-BE-03 & LD-106: Workflow Evidence & Submission ---
class GroundingEvidence(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    code_snippet: str

class SubmissionRequest(BaseModel):
    doc_id: str
    job_id: Optional[str] = None
    submitted_by: Optional[str] = "Lâm Gia Huy"
    evidences: List[GroundingEvidence] = Field(default_factory=list)

class DocumentationSubmission(BaseModel):
    doc_id: str
    job_id: Optional[str] = None
    status: str = "submitted"  # draft | submitted | approved | rejected
    submitted_by: str = "Lâm Gia Huy"
    evidences: List[GroundingEvidence] = Field(default_factory=list)
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None


class EvidenceRegisterRequest(BaseModel):
    """Ghi nhận evidence hợp lệ của một job sinh tài liệu (LD-106: record generation result)."""
    evidences: List[GroundingEvidence] = Field(min_length=1)


class ReviewRequest(BaseModel):
    reviewer: str = Field(min_length=1)
    note: Optional[str] = None
