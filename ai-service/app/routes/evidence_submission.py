from fastapi import APIRouter, HTTPException, status
from app.models import (
    GenerationStatusResponse,
    DocumentationSubmissionRequest,
    GroundingEvidence
)

router = APIRouter(prefix="/api/v1/documents", tags=["Evidence & Submission"])

# Giả lập cơ sở dữ liệu lưu trữ Job & Submissions
JOBS_DB: dict = {
    "job-106-xyz": {
        "job_id": "job-106-xyz",
        "document_id": "doc-106",
        "status": "completed",
        "progress_percentage": 100.0,
        "files_processed": 5,
        "total_files": 5,
        "repository_url": "https://github.com/org/repo",
        "commit_hash": "a1b2c3d4e5f6"
    },
    "job-pending-123": {
        "job_id": "job-pending-123",
        "document_id": "doc-pending",
        "status": "processing",
        "progress_percentage": 45.0,
        "files_processed": 2,
        "total_files": 5,
        "repository_url": "https://github.com/org/repo",
        "commit_hash": "a1b2c3d4e5f6"
    }
}

SUBMISSIONS_DB: set = set()

@router.get("/{document_id}/status", response_model=GenerationStatusResponse)
async def get_generation_status(document_id: str):
    for job in JOBS_DB.values():
        if job["document_id"] == document_id:
            return GenerationStatusResponse(**job)
    raise HTTPException(status_code=404, detail=f"Job for document '{document_id}' not found")

@router.post("/submit", status_code=status.HTTP_200_OK)
async def submit_documentation(payload: DocumentationSubmissionRequest):
    # 1. Kiểm tra Job tồn tại
    if payload.job_id not in JOBS_DB:
        raise HTTPException(status_code=404, detail="Job ID không tồn tại")
    
    job = JOBS_DB[payload.job_id]

    # 2. Kiểm tra Job đã hoàn thành chưa
    if job["status"] != "completed" or job["progress_percentage"] < 100.0:
        raise HTTPException(status_code=400, detail="Job chưa hoàn thành sinh tài liệu")

    # 3. Kiểm tra submit trùng lặp
    if payload.job_id in SUBMISSIONS_DB:
        raise HTTPException(status_code=409, detail="Bản thảo này đã được gửi phê duyệt trước đó")

    # 4. Kiểm tra bằng chứng rỗng
    if not payload.evidences:
        raise HTTPException(status_code=422, detail="Danh sách bằng chứng mã nguồn không được rỗng")

    # 5. Xác minh từng bằng chứng thuộc về đúng Job, Repository và Commit Hash
    for ev in payload.evidences:
        if ev.job_id != payload.job_id:
            raise HTTPException(status_code=400, detail=f"Evidence file '{ev.file_path}' không thuộc Job '{payload.job_id}'")
        if ev.repository_url != job["repository_url"] or ev.commit_hash != job["commit_hash"]:
            raise HTTPException(status_code=400, detail=f"Evidence file '{ev.file_path}' không thuộc repository/commit của Job")

    SUBMISSIONS_DB.add(payload.job_id)
    return {
        "message": "Documentation submitted successfully for review",
        "job_id": payload.job_id,
        "document_id": payload.document_id,
        "workflow_status": "submitted"
    }
