from typing import List, Optional
from app.models import GroundingEvidence, GenerationStatus, DocumentationSubmission

class EvidenceCollector:
    @staticmethod
    def collect_evidence(file_path: str, start_line: int, end_line: int, code: str) -> GroundingEvidence:
        """LD-107: Thu thập bằng chứng mã nguồn gốc"""
        lines = code.splitlines()
        snippet = "\n".join(lines[max(0, start_line-1):min(len(lines), end_line)])
        return GroundingEvidence(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            code_snippet=snippet
        )

class EvidenceDisplayService:
    @staticmethod
    def format_evidence_for_display(evidence: GroundingEvidence) -> dict:
        """LD-108: Hiển thị bằng chứng đối chiếu mã nguồn lên giao diện UI"""
        return {
            "display_title": f"Nguồn gốc: {evidence.file_path} (Dòng {evidence.start_line}-{evidence.end_line})",
            "code_preview": evidence.code_snippet,
            "is_highlighted": True
        }

class StatusTracker:
    @staticmethod
    def get_generation_status(doc_id: str, is_done: bool = True) -> GenerationStatus:
        """LD-109: Cập nhật và hiển thị trạng thái sinh tài liệu thời gian thực"""
        if is_done:
            return GenerationStatus(doc_id=doc_id, status="completed", progress_percentage=100, message="Sinh tài liệu thành công")
        return GenerationStatus(doc_id=doc_id, status="processing", progress_percentage=50, message="Đang xử lý thu thập bằng chứng")

class SubmissionWorkflow:
    @staticmethod
    def submit_documentation(doc_id: str, evidences: List[GroundingEvidence]) -> DocumentationSubmission:
        """LD-110: Thực hiện quy trình gửi phê duyệt tài liệu"""
        return DocumentationSubmission(
            doc_id=doc_id,
            status="submitted",
            evidences=evidences
        )
