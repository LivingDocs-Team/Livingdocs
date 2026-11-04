import pytest
from ai-service.app.confidence import calculate_confidence
from ai-service.app.models import EvidenceItem

def test_confidence_calculation():
    items = [
        EvidenceItem(source="s1", relevance=0.8, snippet="t1"),
        EvidenceItem(source="s2", relevance=1.0, snippet="t2")
    ]
    score = calculate_confidence(items)
    assert score == 0.9
