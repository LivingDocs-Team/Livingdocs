import pytest
from app.extractor import analyze_code_diff
from app.retrieval import match_affected_docs
from app.evidence import generate_drift_evidence

def test_code_change_analysis():
    sample_code = """
def update_user_profile(user_id: str, email: str, age: int):
    '''Update user information.'''
    pass
"""
    result = analyze_code_diff("test.py", sample_code)
    assert result["status"] == "SUCCESS"
    assert len(result["functions"]) == 1
    assert result["functions"][0]["name"] == "update_user_profile"
    assert "age" in result["functions"][0]["args"]

def test_drift_evidence_generation():
    changed_code_info = {
        "functions": [
            {"name": "update_user_profile", "args": ["user_id", "email", "age"]}
        ]
    }
    affected_docs = [
        {
            "function_name": "update_user_profile",
            "doc_path": "Docs/API.md",
            "matched_snippet": "update_user_profile(user_id, email) - Updates user info."
        }
    ]
    
    evidences = generate_drift_evidence(changed_code_info, affected_docs)
    assert len(evidences) == 1
    assert evidences[0]["drift_detected"] is True
    assert evidences[0]["confidence_score"] > 0.6
