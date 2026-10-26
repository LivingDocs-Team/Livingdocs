from typing import List, Optional
from app.models import GroundingEvidence, GenerationStatus, DocumentationSubmission

class EvidenceCollector:
    @staticmethod
    def collect_evidence(file_path: str, start_line: int, end_line: int, code: str) -> GroundingEvidence:
        """LD-107: Trích xuất thu thập bằng chứng mã nguồn gốc"""
        lines = code.splitlines()
        snippet = "\n".join(lines[max(0, start_line-1):min(len(lines), end_line)])
        return GroundingEvidence(
            file_path=file_path,
            start_line=
