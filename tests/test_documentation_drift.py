import pytest
import sys
import os

sys.path.append(os.path.abspath("ai-service"))
sys.path.append(os.path.abspath("code-analyzer"))

from app.extractor import analyze_code_diff
from app.confidence import calculate_confidence_score
from app.evidence import build_drift_evidences

def test_analyze_code_diff_ld146():
    sample_code = """
def sample_api_call(param1: str, param2: int):
    '''Sample docstring.'''
    pass
"""
    result = analyze_code_diff("sample.py", sample_code)
    assert result["status"] == "SUCCESS"
    assert len(result["functions"]) == 1
    assert result["functions"][0]["name"] == "sample_api_call"

def test_confidence_score_ld149():
    code_details = {"name": "sample_api_call", "args": ["param1", "param2_new"]}
    doc_snippet = "Function sample_api_call accepts param1 only."
    score = calculate_confidence_score(code_details, doc_snippet)
    assert score > 0.6

def test_drift_evidence_ld149():
    affected_docs = [{
        "element_name": "sample_api_call",
        "doc_path": "Docs/API.md",
        "snippet": "sample_api_call(param1)",
        "element_details": {"name": "sample_api_call", "args": ["param1", "param2_new"]}
    }]
    evidences = build_drift_evidences(affected_docs)
    assert len(evidences) == 1
    assert evidences[0].drift_detected is True
