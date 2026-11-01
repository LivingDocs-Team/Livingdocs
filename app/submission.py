import uuid
from datetime import datetime
from typing import Dict, List, Optional
from app.evidence_models import GroundingEvidence, GenerationStatus, DocumentationSubmission
from app.models import FileAnalysis

# Bộ lưu trữ dữ liệu (In-Memory Persistence Store cho demo & backend integration)
STATUS_STORE: Dict[str, GenerationStatus] = {}
SUBMISSION_STORE: Dict[str, DocumentationSubmission] = {}
EVIDENCE_STORE: Dict[str, List[GroundingEvidence]] = {}


class EvidenceCollector:
    """Trích xuất GroundingEvidence từ kết quả phân tích mã nguồn thực tế (FileAnalysis)."""
    
    @staticmethod
    def extract_from_analysis(document_id: str, analysis_files: List[FileAnalysis], commit_hash: str) -> List[GroundingEvidence]:
        evidences = []
        for file in analysis_files:
            # Trích xuất từ các hàm tìm thấy trong file
            for func in file.functions:
                evidence = GroundingEvidence(
                    evidence_id=f"evi-{uuid.uuid4().hex[:8]}",
                    file_path=file.file_path,
                    start_line=func.start_line,
                    end_line=func.end_line,
                    code_snippet=f"def {func.name}(...):",
                    commit_hash=commit_hash
                )
                evidences.append(evidence)
        
        # Lưu vào Store
        EVIDENCE_STORE[document_id] = evidences
        return evidences

    @staticmethod
    def get_evidences(document_id: str) -> List[GroundingEvidence]:
        return EVIDENCE_STORE.get(document_id, [])


class StatusTracker:
    """Theo dõi tiến độ job thực tế và lưu trữ trạng thái."""
    
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
    def get_status(document_id: str) -> GenerationStatus:
        if document_id not in STATUS_STORE:
            # Trạng thái mặc định nếu chưa khởi tạo job
            return GenerationStatus(
                document_id=document_id,
                status="processing",
                progress_percentage=0,
                current_step="Initializing"
            )
        return STATUS_STORE[document_id]


class SubmissionWorkflow:
    """Xử lý nộp tài liệu phê duyệt với quy tắc lưu trữ và kiểm tra điều kiện nghiêm ngặt."""

    @staticmethod
    def submit_documentation(document_id: str, submitted_by: str) -> DocumentationSubmission:
        # 1. Kiểm tra trạng thái job sinh tài liệu
        status = StatusTracker.get_status(document_id)
        if status.status != "completed" or status.progress_percentage < 100:
            raise ValueError("Cannot submit document while generation is in progress or incomplete")

        # 2. Kiểm tra tài liệu đã nộp trước đó chưa (Persistence Check)
        if document_id in SUBMISSION_STORE:
            raise ValueError("Document is locked and already submitted")

        # 3. Kiểm tra bằng chứng mã nguồn (Evidence Check)
        evidences = EvidenceCollector.get_evidences(document_id)
        if not evidences:
            raise ValueError("Missing grounding evidence for required sections")

        # 4. Tạo bản ghi Submission & Lưu trữ bền vững
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
        """Truy xuất bản ghi nộp bài đã lưu trữ."""
        return SUBMISSION_STORE.get(document_id)
