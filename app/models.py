from typing import List, Optional
from pydantic import BaseModel, Field

class FileInput(BaseModel):
    """Input data for a source file."""
    path: str = Field(..., description="Path of the source file.")
    content: str = Field(..., description="Source code content.")
    language: Optional[str] = Field(
        None,
        description="Programming language, e.g. python or java."
    )
class RepoAnalysisRequest(BaseModel):
    """Payload gửi lên API POST /api/v1/analyze-repo"""
    target: str = Field(..., description="Tên repository, ví dụ owner/repo")
    scope: str = Field("repository", description="Phạm vi phân tích: file | module | repository")
    files: List[FileInput] = Field(default_factory=list, description="Danh sách các tệp mã nguồn cần phân tích")
    options: Optional[dict] = Field(default_factory=dict, description="Cấu hình bổ sung")

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

class ClassInfo(BaseModel):
    name: str
    bases: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    methods: List[Function] = Field(default_factory=list)

class Endpoint(BaseModel):
    http_method: str
    path: str
    handler: Optional[str] = None
    parameters: List[Parameter] = Field(default_factory=list)
    request_body: Optional[str] = None
    response: Optional[str] = None

class FileAnalysis(BaseModel):
    path: str
    language: Optional[str] = None
    module: Optional[str] = None
    status: str = "ok"  # ok | empty | invalid | unsupported
    error: Optional[str] = None
    classes: List[ClassInfo] = Field(default_factory=list)
    functions: List[Function] = Field(default_factory=list)
    endpoints: List[Endpoint] = Field(default_factory=list)

class RepoAnalysisResponse(BaseModel):
    """Kết quả phân tích trả về cho toàn bộ Repository"""
    scope: str
    target: str
    files: List[FileAnalysis] = Field(default_factory=list)
