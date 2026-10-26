class GroundingEvidence(BaseModel):
    """LD-107: Bằng chứng nguồn gốc mã nguồn dùng để sinh tài liệu"""
    file_path: str = Field(..., description="Đường dẫn tệp mã nguồn")
    start_line: int = Field(..., description="Dòng bắt đầu trong code")
    end_line: int = Field(..., description="Dòng kết thúc trong code")
    code_snippet: str = Field(..., description="Đoạn mã nguồn đối chiếu")

class DocumentationSubmission(BaseModel):
    """LD-110: Yêu cầu gửi phê duyệt tài liệu"""
    doc_id: str = Field(..., description="Mã tài liệu")
    status: str = Field("submitted", description="Trạng thái: draft | submitted | approved | rejected")
    submitted_by: Optional[str] = Field("LH", description="Người gửi")
    evidences: List[GroundingEvidence] = Field(default_factory=list)
