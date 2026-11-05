"""LD-106: Evidence & Submission workflow.

- EvidenceCollector: tạo/ghi nhận grounding evidence (file, dòng, đoạn mã).
- SubmissionWorkflow: gửi tài liệu, đối chiếu evidence với job, chuyển trạng thái phê duyệt.
- Router /api/v1/submission: lớp mỏng gọi hai lớp trên.

Dữ liệu lưu trong RAM; đặt biến môi trường LD_SUBMISSION_STORE_PATH=/đường/dẫn/file.json
để lưu bền vững (tự nạp lại khi khởi động lại dịch vụ).
"""
import json
import os
import tempfile
import threading
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status

from app.models import (
    DocumentationSubmission,
    EvidenceRegisterRequest,
    GroundingEvidence,
    ReviewRequest,
    SubmissionRequest,
)

# Tách riêng router tránh xung đột với /health và contract cũ của Analyzer (Sửa L01)
router = APIRouter(prefix="/api/v1/submission", tags=["Evidence & Submission"])

# Stores (LD106-R3)
SUBMISSION_STORE: Dict[str, DocumentationSubmission] = {}
EVIDENCE_STORE: Dict[str, List[GroundingEvidence]] = {}

STORE_PATH_ENV = "LD_SUBMISSION_STORE_PATH"
_LOCK = threading.RLock()

# Luồng trạng thái hợp lệ: draft -> submitted -> approved | rejected -> (nộp lại) submitted
# "submitted" -> "submitted": cho phép gửi lại/cập nhật evidence khi chưa được duyệt (idempotent).
ALLOWED_TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"submitted", "approved", "rejected"},
    "rejected": {"submitted"},
    "approved": set(),
}


class WorkflowError(ValueError):
    """Lỗi nghiệp vụ; `status_code` để router đổi sang HTTP tương ứng."""

    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------- persistence
def _store_path() -> Optional[str]:
    return os.environ.get(STORE_PATH_ENV) or None


def save_stores() -> None:
    path = _store_path()
    if not path:
        return
    data = {
        "submissions": {k: v.model_dump(mode="json") for k, v in SUBMISSION_STORE.items()},
        "evidence": {k: [e.model_dump(mode="json") for e in v] for k, v in EVIDENCE_STORE.items()},
    }
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # ghi nguyên tử, tránh file hỏng khi dịch vụ chết giữa chừng
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def load_stores() -> None:
    path = _store_path()
    if not path or not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    SUBMISSION_STORE.clear()
    EVIDENCE_STORE.clear()
    for k, v in data.get("submissions", {}).items():
        SUBMISSION_STORE[k] = DocumentationSubmission(**v)
    for k, v in data.get("evidence", {}).items():
        EVIDENCE_STORE[k] = [GroundingEvidence(**e) for e in v]


load_stores()


# ------------------------------------------------------------------ evidence
class EvidenceCollector:
    @staticmethod
    def collect_evidence(file_path: str, start_line: int, end_line: int, source_code: str) -> GroundingEvidence:
        """Cắt đoạn mã [start_line, end_line] (đánh số từ 1, gồm cả hai đầu) làm bằng chứng."""
        if not file_path:
            raise WorkflowError("file_path không được rỗng")
        lines = (source_code or "").splitlines()
        if start_line < 1 or end_line < start_line:
            raise WorkflowError(f"Khoảng dòng không hợp lệ: {start_line}-{end_line}")
        if end_line > len(lines):
            raise WorkflowError(
                f"end_line={end_line} vượt quá số dòng của {file_path} ({len(lines)} dòng)"
            )
        return GroundingEvidence(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            code_snippet="\n".join(lines[start_line - 1:end_line]),
        )

    @staticmethod
    def register_evidence(job_id: str, evidences: List[GroundingEvidence]) -> List[GroundingEvidence]:
        """Ghi nhận evidence hợp lệ của job (nguồn đối chiếu khi gửi tài liệu)."""
        if not job_id:
            raise WorkflowError("job_id không được rỗng")
        with _LOCK:
            EVIDENCE_STORE.setdefault(job_id, []).extend(evidences)
            save_stores()
            return list(EVIDENCE_STORE[job_id])

    @staticmethod
    def get_evidence(job_id: str) -> List[GroundingEvidence]:
        if job_id not in EVIDENCE_STORE:
            raise WorkflowError(f"Không có evidence nào cho job {job_id}", status.HTTP_404_NOT_FOUND)
        return list(EVIDENCE_STORE[job_id])


# ------------------------------------------------------------------ workflow
class SubmissionWorkflow:
    @staticmethod
    def validate_evidences(job_id: Optional[str], evidences: List[GroundingEvidence]) -> None:
        """Đối chiếu evidence với những gì đã ghi nhận cho job.

        - Không có job_id: không có gì để đối chiếu (tài liệu nháp, không gắn job).
        - Có job_id nhưng job chưa được ghi nhận evidence: từ chối (trước đây bị bỏ qua im lặng).
        - Mỗi evidence phải nằm trọn trong một khoảng đã ghi nhận của cùng file.
        """
        if not job_id:
            return
        if job_id not in EVIDENCE_STORE:
            raise WorkflowError(
                f"Job {job_id} chưa có evidence được ghi nhận; không thể xác minh bằng chứng",
                status.HTTP_404_NOT_FOUND,
            )
        valid = EVIDENCE_STORE[job_id]
        for ev in evidences:
            matched = any(
                v.file_path == ev.file_path and v.start_line <= ev.start_line and v.end_line >= ev.end_line
                for v in valid
            )
            if not matched:
                raise WorkflowError(
                    f"Evidence {ev.file_path}:{ev.start_line}-{ev.end_line} không khớp với job {job_id}"
                )

    @staticmethod
    def _transition(sub: DocumentationSubmission, new_status: str) -> None:
        if new_status not in ALLOWED_TRANSITIONS.get(sub.status, set()):
            raise WorkflowError(
                f"Không thể chuyển trạng thái {sub.status} -> {new_status}",
                status.HTTP_409_CONFLICT,
            )
        sub.status = new_status

    @staticmethod
    def submit_documentation(
        doc_id: str,
        evidences: List[GroundingEvidence],
        job_id: Optional[str] = None,
        submitted_by: Optional[str] = None,
    ) -> DocumentationSubmission:
        if not doc_id:
            raise WorkflowError("doc_id không được rỗng")
        with _LOCK:
            SubmissionWorkflow.validate_evidences(job_id, evidences)

            existing = SUBMISSION_STORE.get(doc_id)
            if existing is not None:
                # Nộp lại chỉ hợp lệ khi chưa duyệt hoặc bị rejected; approved thì 409 (bảng chuyển trạng thái)
                SubmissionWorkflow._transition(existing, "submitted")
                existing.job_id = job_id
                existing.evidences = list(evidences)
                existing.submitted_by = submitted_by or existing.submitted_by
                existing.reviewed_by = None
                existing.review_note = None
                submission = existing
            else:
                submission = DocumentationSubmission(
                    doc_id=doc_id,
                    job_id=job_id,
                    status="submitted",
                    submitted_by=submitted_by or "Lâm Gia Huy",
                    evidences=list(evidences),
                )
                SUBMISSION_STORE[doc_id] = submission
            save_stores()
            return submission

    @staticmethod
    def get_submission(doc_id: str) -> DocumentationSubmission:
        if doc_id not in SUBMISSION_STORE:
            raise WorkflowError("Submission không tồn tại", status.HTTP_404_NOT_FOUND)
        return SUBMISSION_STORE[doc_id]

    @staticmethod
    def approve(doc_id: str, reviewer: str, note: Optional[str] = None) -> DocumentationSubmission:
        with _LOCK:
            sub = SubmissionWorkflow.get_submission(doc_id)
            SubmissionWorkflow._transition(sub, "approved")
            sub.reviewed_by, sub.review_note = reviewer, note
            save_stores()
            return sub

    @staticmethod
    def reject(doc_id: str, reviewer: str, note: Optional[str] = None) -> DocumentationSubmission:
        with _LOCK:
            sub = SubmissionWorkflow.get_submission(doc_id)
            SubmissionWorkflow._transition(sub, "rejected")
            sub.reviewed_by, sub.review_note = reviewer, note
            save_stores()
            return sub


# --------------------------------------------------------------------- routes
def _http(exc: WorkflowError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/evidence/{job_id}", response_model=List[GroundingEvidence], status_code=status.HTTP_201_CREATED)
async def register_evidence(job_id: str, req: EvidenceRegisterRequest):
    try:
        return EvidenceCollector.register_evidence(job_id, req.evidences)
    except WorkflowError as exc:
        raise _http(exc)


@router.get("/evidence/{job_id}", response_model=List[GroundingEvidence])
async def get_evidence(job_id: str):
    try:
        return EvidenceCollector.get_evidence(job_id)
    except WorkflowError as exc:
        raise _http(exc)


@router.post("/submit", response_model=DocumentationSubmission)
async def submit_documentation(req: SubmissionRequest):
    try:
        return SubmissionWorkflow.submit_documentation(
            req.doc_id, req.evidences, job_id=req.job_id, submitted_by=req.submitted_by
        )
    except WorkflowError as exc:
        raise _http(exc)


@router.post("/{doc_id}/approve", response_model=DocumentationSubmission)
async def approve_submission(doc_id: str, req: ReviewRequest):
    try:
        return SubmissionWorkflow.approve(doc_id, req.reviewer, req.note)
    except WorkflowError as exc:
        raise _http(exc)


@router.post("/{doc_id}/reject", response_model=DocumentationSubmission)
async def reject_submission(doc_id: str, req: ReviewRequest):
    try:
        return SubmissionWorkflow.reject(doc_id, req.reviewer, req.note)
    except WorkflowError as exc:
        raise _http(exc)


@router.get("/{doc_id}", response_model=DocumentationSubmission)
async def get_submission(doc_id: str):
    try:
        return SubmissionWorkflow.get_submission(doc_id)
    except WorkflowError as exc:
        raise _http(exc)
