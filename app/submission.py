from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, List
from datetime import datetime
import uuid

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

STATUS_STORE: Dict[str, Dict[str, Any]] = {}
SUBMISSION_STORE: Dict[str, Dict[str, Any]] = {}
EVIDENCE_STORE: Dict[str, List[Dict[str, Any]]] = {}

@router.get("/status/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    # 1. Job không tồn tại -> Trả 404
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
    # 1. Job không tồn tại -> Trả 404
    if job_id not in STATUS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found"
        )
    
    job_info = STATUS_STORE[job_id]
    
    # 2. ƯU TIÊN KIỂM TRA TRẠNG THÁI: Job chưa completed -> Trả 400 Bad Request
    if job_info.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not completed yet"
        )
    
    # 3. Job đã completed nhưng không có source code evidence -> Trả 404
    evidences = EVIDENCE_STORE.get(job_id, [])
    if not evidences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No source code evidence available for this job"
        )
    
    return [EvidenceItem(**item) for item in evidences]

@router.post("/submit", response_model=SubmissionResponse)
def submit_evidence(req: SubmissionRequest):
    # 1. Job không tồn tại -> Trả 404
    if req.job_id not in STATUS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{req.job_id}' not found"
        )
    
    # 2. ƯU TIÊN VALIDATE EVIDENCES: Thiếu evidence -> Trả 400 Bad Request
    if not req.evidence_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Submission must contain at least one evidence item"
        )
    
    # 3. ƯU TIÊN VALIDATE DUPLICATE: Job đã submit rồi -> Trả 400 Bad Request
    if req.job_id in SUBMISSION_STORE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job '{req.job_id}' has already been submitted"
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
