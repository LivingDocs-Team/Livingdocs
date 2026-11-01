from pydantic import BaseModel
from typing import List, Optional

class EvidenceItem(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    commit_hash: str
    source_code: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    message: Optional[str] = None

class SubmissionRequest(BaseModel):
    job_id: str
    repository: str
    commit_hash: str
    evidence_list: List[EvidenceItem]

class SubmissionResponse(BaseModel):
    submission_id: str
    job_id: str
    status: str
    timestamp: str
