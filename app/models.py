class GroundingEvidence(BaseModel):
    """LD-107: Bằng chứng nguồn gốc mã nguồn"""
    file_path: str = Field(..., description="Đường dẫn tệp code")
    start_line: int = Field(..., description="Dòng bắt đầu trong code")
    end_line: int = Field(..., description="Dòng kết thúc trong code")
    code_snippet: str = Field(..., description="Đoạn mã đối chiếu")

class GenerationStatus(BaseModel):
    """LD-109: Trạng thái sinh tài liệu theo thời gian thực"""
    doc_id: str
    status: str = Field("processing", description="processing | completed | failed")
    progress_percentage: int = 0
    message: Optional[str] = None

class DocumentationSubmission(BaseModel):
    """LD-110: Yêu cầu gửi phê duyệt tài liệu"""
    doc_id: str
    status: str = Field("submitted", description="draft | submitted | approved | rejected")
    submitted_by: Optional[str] = "LH"
    evidences: List[GroundingEvidence] = Field(default_factory=list)
