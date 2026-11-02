import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.evidence_extractor import extract_evidence
from app.evidence_models import (
    EvidenceItem,
    JobCreateRequest,
    JobStatusResponse,
    SubmissionRequest,
    SubmissionResponse,
)

router = APIRouter()

STATUS_STORE: Dict[str, Dict[str, Any]] = {}
SUBMISSION_STORE: Dict[str, Dict[str, Any]] = {}
EVIDENCE_STORE: Dict[str, List[Dict[str, Any]]] = {}


def _repos_base() -> Path:
    return Path(os.environ.get("REPOS_BASE_DIR", "/repos")).resolve()


def _run_job(job_id: str, repo_root: Path, commit_hash: str) -> None:
    try:
        STATUS_STORE[job_id].update(status="processing", progress=10)
        evidences = extract_evidence(repo_root, commit_hash)
        EVIDENCE_STORE[job_id] = evidences
        STATUS_STORE[job_id].update(
            status="completed",
            progress=100,
            message=None if evidences else "No source code evidence could be extracted",
        )
    except Exception as exc:  # noqa: BLE001
        STATUS_STORE[job_id].update(status="failed", progress=100, message=str(exc))


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED, response_model=JobStatusResponse)
def create_job(req: JobCreateRequest, background: BackgroundTasks):
    if req.job_id in STATUS_STORE:
        raise HTTPException(status_code=400, detail=f"Job '{req.job_id}' already exists")

    base = _repos_base()
    repo_root = (base / req.repo_path).resolve()
    # Chặn path traversal: repo phải nằm trong REPOS_BASE_DIR
    if repo_root != base and base not in repo_root.parents:
        raise HTTPException(status_code=400, detail="repo_path is outside the allowed directory")
    if not repo_root.is_dir():
        raise HTTPException(status_code=404, detail=f"Repository path '{req.repo_path}' not found")

    STATUS_STORE[req.job_id] = {"status": "processing", "progress": 0}
    background.add_task(_run_job, req.job_id, repo_root, req.commit_hash)
    return JobStatusResponse(job_id=req.job_id, status="processing", progress=0)


@router.get("/status/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    if job_id not in STATUS_STORE:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    data = STATUS_STORE[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=data.get("status", "processing"),
        progress=data.get("progress", 0),
        message=data.get("message"),
    )


@router.get("/evidence/{job_id}", response_model=List[EvidenceItem])
def get_job_evidence(job_id: str):
    if job_id not in STATUS_STORE:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if STATUS_STORE[job_id].get("status") != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed yet")
    evidences = EVIDENCE_STORE.get(job_id, [])
    if not evidences:
        raise HTTPException(status_code=404, detail="No source code evidence available for this job")
    return [EvidenceItem(**item) for item in evidences]


@router.post("/submit", response_model=SubmissionResponse)
def submit_evidence(req: SubmissionRequest):
    if req.job_id not in STATUS_STORE:
        raise HTTPException(status_code=404, detail=f"Job '{req.job_id}' not found")
    if not req.evidence_list:
        raise HTTPException(status_code=400, detail="Submission must contain at least one evidence item")
    if STATUS_STORE[req.job_id].get("status") != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed yet")
    for ev in req.evidence_list:
        if ev.start_line < 1 or ev.end_line < ev.start_line or not ev.source_code.strip():
            raise HTTPException(
                status_code=400,
                detail=f"Invalid evidence for '{ev.file_path}': bad line range or empty source_code",
            )
    if req.job_id in SUBMISSION_STORE:
        raise HTTPException(status_code=400, detail=f"Job '{req.job_id}' has already been submitted")

    sub_data = {
        "submission_id": str(uuid.uuid4()),
        "job_id": req.job_id,
        "status": "submitted",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    SUBMISSION_STORE[req.job_id] = sub_data
    return SubmissionResponse(**sub_data)
