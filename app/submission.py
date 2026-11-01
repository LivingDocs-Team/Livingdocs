import uuid
from datetime import datetime
from typing import Dict, List, Optional
from app.evidence_models import GroundingEvidence, GenerationStatus, DocumentationSubmission
from app.models import FileAnalysis

STATUS_STORE: Dict[str, GenerationStatus] = {}
SUBMISSION_STORE: Dict[str, DocumentationSubmission] = {}
EVIDENCE_STORE: Dict[str, List[GroundingEvidence]] = {}

class EvidenceCollector:
    """Trích xuất Evidence từ mã nguồn THỰC TẾ (Không tạo nội dung giả)."""
    
    @staticmethod
    def extract_from_analysis(document_id: str, analysis_files: List[FileAnalysis], commit_hash: str) -> List[GroundingEvidence]:
        evidences = []
        for file in analysis_files:
            for func in file.functions:
                # 🔴 Nếu thiếu source thực tế thì BỎ QUA, KHÔNG TỰ TẠO CHUỖI FAKE
                if not func.source or not func.source.strip():
                    continue
                
                evidence = GroundingEvidence(
                    evidence_id=f"evi-{uuid.uuid4().hex[:8]}",
                    file_path=file.path,             # Khớp với model contract gốc
                    start_line=func.lineno,         # Khớp với model contract gốc
                    end_line=func.end_lineno,       # Khớp với model contract gốc
                    code_snippet=func.source,        # Mã nguồn THỰC TẾ
                    commit_hash=commit_hash
                )
                evidences.append(evidence)
        
        EVIDENCE_STORE[document_id] = evidences
        return evidences

    @staticmethod
    def get_evidences(document_id: str) -> List[GroundingEvidence]:
        return EVIDENCE_STORE.get(document_id, [])


class StatusTracker:
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
        # 🔴 Trả về None nếu job không tồn tại (để API bắn lỗi 404)
        return STATUS_STORE.get(document_id)


class SubmissionWorkflow:
    @staticmethod
    def submit_documentation(document_id: str, submitted_by: str) -> DocumentationSubmission:
        status = StatusTracker.get_status(document_id)
        if not status:
            raise KeyError("Generation job not found")
        if status.status != "completed" or status.progress_percentage < 100:
            raise ValueError("Cannot submit document while generation is in progress or incomplete")

        if document_id in SUBMISSION_STORE:
            raise ValueError("Document is locked and already submitted")

        evidences = EvidenceCollector.get_evidences(document_id)
        if not evidences:
            raise ValueError("Missing required source grounding evidence")

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
