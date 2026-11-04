"""Markdown report generator."""
from ai-service.app.models import ExplanationResponse

def render_markdown_report(response: ExplanationResponse) -> str:
    md = [
        "# Code Analysis AI Explanation",
        f"**Confidence:** {response.confidence * 100}%",
        "",
        "## Summary",
        response.explanation,
        "",
        "## Supporting Evidence"
    ]
    for ev in response.evidence:
        md.append(f"- [{ev.source}] {ev.snippet} (Relevance: {ev.relevance})")
    return "\n".join(md)
