"""Evidence collector for AI analysis."""
from typing import List
from ai-service.app.models import EvidenceItem

class EvidenceCollector:
    def collect(self, issue_rule: str) -> List[EvidenceItem]:
        return [
            EvidenceItem(
                source="PEP8 / Best Practices",
                relevance=0.9,
                snippet=f"Rule {issue_rule} violates clean code standards."
            )
        ]
