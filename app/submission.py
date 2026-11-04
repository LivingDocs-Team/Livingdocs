from fastapi import APIRouter, HTTPException, status
from typing import List, Dict
from app.models import SubmissionRequest, DocumentationSubmission, GroundingEvidence

# Tách riêng router tránh xung đột với /health và contract cũ (Sửa L01)
router = APIRouter(prefix="/api/v1/submission", tags=["Evidence & Submission"])

# In-memory stores (LD106-R3)
SUBMISSION_STORE: Dict[str, DocumentationSubmission] = {}
EVIDENCE_STORE: Dict[str, List[GroundingEvidence]] = {}

@router.post("/submit", response_model=DocumentationSubmission)
async def submit_documentation(req: SubmissionRequest):
    # Sửa LD106-R2: Kiểm tra tính hợp lệ của evidence theo job_id nếu có
    if req.job_id and req.job_id in EVIDENCE_STORE:
        valid_evidences = EVIDENCE_STORE[req.job_id]
        # Validate xem evidence gửi lên có nằm trong tập evidence sinh ra không
        for ev in req.evidences:
            matched = any(
                v.file_path == ev.file_path and v.start_line <= ev.start_line and v.end_line >= ev.end_line
                for v in valid_evidences
            )
            if not matched:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Evidence {ev.file_path}:{ev.start_line}-{ev.end_line} không khớp với job {req.job_id}"
                )

    submission = DocumentationSubmission(
        doc_id=req.doc_id,
        job_id=req.job_id,
        status="submitted",
        submitted_by=req.submitted_by or "Lâm Gia Huy",
        evidences=req.evidences
    )
    SUBMISSION_STORE[req.doc_id] = submission
    return submission

@router.get("/{doc_id}", response_model=DocumentationSubmission)
async def get_submission(doc_id: str):
    if doc_id not in SUBMISSION_STORE:
        raise HTTPException(status_code=404, detail="Submission không tồn tại")
    return SUBMISSION_STORE[doc_id]
