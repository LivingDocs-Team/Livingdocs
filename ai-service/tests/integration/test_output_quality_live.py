import pytest
from ai-service.app.renderer import render_markdown_report
from ai-service.app.models import ExplanationResponse, EvidenceItem

def test_live_quality_report():
    data = ExplanationResponse(
        explanation="Detected bare except block.",
        confidence=0.85,
        evidence=[EvidenceItem(source="Docs", relevance=0.85, snippet="Catching all exceptions is risky.")]
    )
    report = render_markdown_report(data)
    assert "# Code Analysis AI Explanation" in report
    assert "85.0%" in report
