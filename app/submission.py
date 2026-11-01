import uuid
from datetime import datetime
from typing import Dict, List, Optional
from app.evidence_models import GroundingEvidence, GenerationStatus, DocumentationSubmission
from app.models import FileAnalysis

# Kho lưu trữ dữ liệu (Simulation Persistence Layer)
STATUS_STORE: Dict[str, GenerationStatus] = {}
SUBMISSION_STORE: Dict[str, DocumentationSubmission] = {}
EVIDENCE_STORE: Dict[str, List[GroundingEvidence]] = {}


class EvidenceCollector:
    """Trích xuất GroundingEvidence từ kết quả phân tích mã nguồn THỰC TẾ (FileAnalysis)."""
    
    @staticmethod
    def extract_from_analysis(document_id: str, analysis_files: List[FileAnalysis], commit_hash: str) -> List[GroundingEvidence]:
        evidences = []
        for file in analysis_files:
            for func in file.functions:
                # 🔴 Sửa lỗi 2: Lấy func.source thực tế, nếu không có mới đọc nội dung giới hạn
                real_code = func.source if func.source else f"# Source line {func.lineno} to {func.end_lineno} in {file.path}"
                
                evidence = GroundingEvidence(
                    evidence_id=f"evi-{uuid.uuid4().hex[:8]}",
                    file_path=file.path,              # 🔴 Dùng file.path của contract gốc
                    start_line=func.lineno,          # 🔴 Dùng func.lineno của contract gốc
                    end_line=func.end_lineno,        # 🔴 Dùng func.end_lineno của contract gốc
                    code_snippet=real_code,           # 🔴 Mã nguồn thực tế
                    commit_hash=commit_hash
                )
                evidences.append(evidence)
        
        EVIDENCE_STORE[document_id] = evidences
        return evidences

    @staticmethod
    def get_evidences(document_id: str) -> List[GroundingEvidence]:
        return EVIDENCE_STORE.get(document_id, [])


class StatusTracker:
    """Theo dõi tiến độ job thực tế."""
    
    @staticmethod
    def update_status(document_id: str, progress: int, status_str: str = "processing", step: str = "") -> GenerationStatus:
        status_obj = GenerationStatus(
            document_id=document_id,
            status=status_str,
            progress_percentage=progress,
            current_step=step,
            updated_at=datetime.utcnow()
        )
        STATUS_STORE[document_id] = status_obj
        return status_obj

    @staticmethod
    def get_status(document_id: str) -> Optional[GenerationStatus]:
        # 🔴 Sửa lỗi 3: Không tự trả về processing nếu job không tồn tại
        if document_id not in STATUS_STORE:
            return None
        return STATUS_STORE[document_id]


class SubmissionWorkflow:
    """Xử lý nộp tài liệu phê duyệt với quy tắc kiểm tra nghiêm ngặt."""

    @staticmethod
    def submit_documentation(document_id: str, submitted_by: str) -> DocumentationSubmission:
        status = StatusTracker.get_status(document_id)
        if not status:
            raise KeyError("Document generation job not found")
        if status.status != "completed" or status.progress_percentage < 100:
            raise ValueError("Cannot submit document while generation is in progress or incomplete")

        if document_id in SUBMISSION_STORE:
            raise ValueError("Document is locked and already submitted")

        evidences = EvidenceCollector.get_evidences(document_id)
        if not evidences:
            raise ValueError("Missing grounding evidence for required sections")

        submission = DocumentationSubmission(
            submission_id=f"sub-{uuid.uuid4().hex[:8]}",
            document_id=document_id,
            submitted_by=submitted_by,
            status="submitted",
            submitted_at=datetime.utcnow(),
            evidence_ids=[e.evidence_id for e in evidences]
        )
        SUBMISSION_STORE[document_id] = submission
        return submission

    @staticmethod
    def get_submission(document_id: str) -> Optional[DocumentationSubmission]:
        return SUBMISSION_STORE.get(document_id)
