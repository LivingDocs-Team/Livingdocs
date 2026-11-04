from fastapi import APIRouter, HTTPException, status
from typing import List, Dict
from app.models import SubmissionRequest, DocumentationSubmission, GroundingEvidence

router = APIRouter(prefix="/api/v1/submission", tags=["Evidence & Submission"])

# In-Memory Store cho đợt Demo Sprint (LD106-R3)
SUBMISSION_STORE: Dict[str, DocumentationSubmission] = {}
EVIDENCE_STORE: Dict[str, List[GroundingEvidence]] = {}

class EvidenceCollector:
    @staticmethod
    def add_evidence(job_id: str, evidence: GroundingEvidence):
        if job_id not in EVIDENCE_STORE:
            EVIDENCE_STORE[job_id] = []
        EVIDENCE_STORE[job_id].append(evidence)

    @staticmethod
    def get_evidences(job_id: str) -> List[GroundingEvidence]:
        return EVIDENCE_STORE.get(job_id, [])

class SubmissionWorkflow:
    @staticmethod
    def create_submission(req: SubmissionRequest) -> DocumentationSubmission:
        # LD106-R2: Kiểm tra đối chiếu evidence gửi lên với EVIDENCE_STORE của job_id
        if req.job_id and req.job_id in EVIDENCE_STORE:
            valid_evidences = EVIDENCE_STORE[req.job_id]
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

@router.post("/submit", response_model=DocumentationSubmission)
async def submit_documentation(req: SubmissionRequest):
    return SubmissionWorkflow.create_submission(req)

@router.get("/{doc_id}", response_model=DocumentationSubmission)
async def get_submission(doc_id: str):
    if doc_id not in SUBMISSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission không tồn tại")
    return SUBMISSION_STORE[doc_id]
