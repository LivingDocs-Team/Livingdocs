from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class GroundingEvidence(BaseModel):
    evidence_id: str
    file_path: str
    start_line: int
    end_line: int
    code_snippet: str      # Phải là mã nguồn thực tế
    commit_hash: str

class GenerationStatus(BaseModel):
    document_id: str
    status: str = Field(..., description="processing | completed | failed")
    progress_percentage: int = Field(..., ge=0, le=100)
    current_step: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class DocumentationSubmission(BaseModel):
    submission_id: str
    document_id: str
    submitted_by: str
    status: str = Field(default="submitted")
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    evidence_ids: List[str] = Field(default_factory=list)
