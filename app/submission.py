from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, List
from datetime import datetime
import uuid

# Import Pydantic models từ file độc lập LD-106
try:
    from app.evidence_models import (
        EvidenceItem,
        JobStatusResponse,
        SubmissionRequest,
        SubmissionResponse
    )
except ImportError:
    from evidence_models import (
        EvidenceItem,
        JobStatusResponse,
        SubmissionRequest,
        SubmissionResponse
    )

router = APIRouter()

# Bộ nhớ tạm trong RAM (In-memory persistence)
STATUS_STORE: Dict[str, Dict[str, Any]] = {}
SUBMISSION_STORE: Dict[str, Dict[str, Any]] = {}
EVIDENCE_STORE: Dict[str, List[Dict[str, Any]]] = {}

@router.get("/status/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    """Bám sát Yêu cầu 4 của Lead: Job không tồn tại trả về 404"""
    if job_id not in STATUS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found"
        )
    job_data = STATUS_STORE[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=job_data.get("status", "processing"),
        progress=job_data.get("progress", 0),
        message=job_data.get("message")
    )

@router.get("/evidence/{job_id}", response_model=List[EvidenceItem])
def get_job_evidence(job_id: str):
    """Bám sát Yêu cầu 2 của Lead: Không có source_code thật thì trả 404, không tự chế chuỗi giả định"""
    if job_id not in STATUS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found"
        )
    
    job_info = STATUS_STORE[job_id]
    if job_info.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not completed yet"
        )
    
    evidences = EVIDENCE_STORE.get(job_id, [])
    if not evidences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No source code evidence available for this job"
        )
    
    return [EvidenceItem(**item) for item in evidences]

@router.post("/submit", response_model=SubmissionResponse)
def submit_evidence(req: SubmissionRequest):
    """Bám sát Yêu cầu 4 của Lead: Kiểm thử validation lỗi 400 đối với submit thiếu evidence hoặc trùng lặp"""
    if req.job_id not in STATUS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{req.job_id}' not found"
        )
    
    if req.job_id in SUBMISSION_STORE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job '{req.job_id}' has already been submitted"
        )
    
    if not req.evidence_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Submission must contain at least one evidence item"
        )
    
    sub_id = str(uuid.uuid4())
    sub_data = {
        "submission_id": sub_id,
        "job_id": req.job_id,
        "status": "submitted",
        "timestamp": datetime.utcnow().isoformat()
    }
    SUBMISSION_STORE[req.job_id] = sub_data
    
    return SubmissionResponse(**sub_data)
