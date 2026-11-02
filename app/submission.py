from typing import List
from app.models import GroundingEvidence, DocumentationSubmission

class EvidenceCollector:
    @staticmethod
    def collect_evidence(file_path: str, start_line: int, end_line: int, code: str) -> GroundingEvidence:
        """LD-107: Trích xuất bằng chứng đối chiếu mã nguồn"""
        lines = code.splitlines()
        snippet = "\n".join(lines[max(0, start_line-1):min(len(lines), end_line)])
        return GroundingEvidence(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            code_snippet=snippet
        )

class SubmissionWorkflow:
    @staticmethod
    def submit_documentation(doc_id: str, evidences: List[GroundingEvidence]) -> DocumentationSubmission:
        """LD-110: Tạo quy trình gửi phê duyệt tài liệu"""
        return DocumentationSubmission(
            doc_id=doc_id,
            status="submitted",
            evidences=evidences
        )
