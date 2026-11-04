"""Confidence scoring engine."""
from typing import List
from ai-service.app.models import EvidenceItem

def calculate_confidence(evidence: List[EvidenceItem]) -> float:
    if not evidence:
        return 0.5
    total_score = sum(e.relevance for e in evidence)
    return round(min(1.0, total_score / len(evidence)), 2)
