from pydantic import BaseModel, Field
from typing import List, Optional

class GroundingEvidence(BaseModel):
    file_path: str = Field(..., description="Đường dẫn file mã nguồn")
    start_line: int = Field(..., description="Dòng bắt đầu")
    end_line: int = Field(..., description="Dòng kết thúc")
    code_snippet: Optional[str] = Field(None, description="Đoạn code minh chứng")

class EvidenceSubmissionRequest(BaseModel):
    doc_id: str = Field(..., description="ID tài liệu")
    status: str = Field(..., description="Trạng thái submission")
    evidences: List[GroundingEvidence] = Field(default_factory=list, description="Danh sách minh chứng")

class EvidenceSubmissionResponse(BaseModel):
    success: bool
    message: str
    submission_id: Optional[str] = None
