from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# ERR-BE-02: Model lưu thông tin thuộc tính/trường dữ liệu
class FieldInfo(BaseModel):
    name: str
    type: Optional[str] = None
    default: Optional[str] = None
    description: Optional[str] = None

# ERR-BE-01 & ERR-BE-02: Thêm fields, lineno, end_lineno cho ClassInfo
class ClassInfo(BaseModel):
    name: str
    kind: str = "class"  # class | interface | enum | record | annotation
    bases: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    methods: List[Dict[str, Any]] = Field(default_factory=list)
    fields: List[FieldInfo] = Field(default_factory=list)
    lineno: Optional[int] = None
    end_lineno: Optional[int] = None

# ERR-BE-01: Thêm lineno, end_lineno cho Endpoint
class Endpoint(BaseModel):
    http_method: str
    path: str
    handler: Optional[str] = None
    parameters: List[Dict[str, Any]] = Field(default_factory=list)
    request_body: Optional[str] = None
    response: Optional[str] = None
    lineno: Optional[int] = None
    end_lineno: Optional[int] = None

# ERR-BE-03 & LD-106: Workflow Grounding Evidence & Submission
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
