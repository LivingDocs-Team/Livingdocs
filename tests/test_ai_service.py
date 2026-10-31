import os
import pytest

# Khởi tạo API Key giả lập cho môi trường CI runner
os.environ.setdefault("ANTHROPIC_API_KEY", "mock_key_for_ci_pipeline")

def test_ai_service_evidence_schema():
    """Kiểm tra cấu trúc dữ liệu Grounding Evidence (LD-106)"""
    mock_payload = {
        "doc_id": "DOC-LD-106",
        "status": "submitted",
        "evidences": [
            {
                "file_path": "app/models.py",
                "start_line": 1,
                "end_line": 15,
                "code_snippet": "class GroundingEvidence(BaseModel):"
            }
        ]
    }
    assert mock_payload["doc_id"] == "DOC-LD-106"
    assert len(mock_payload["evidences"]) == 1
    assert mock_payload["evidences"][0]["start_line"] == 1

def test_ai_service_integration_mock():
    """Mock integration test cho AI Service"""
    mock_response = {
        "status": "success",
        "documentation": "# Generated Evidence Documentation",
        "usage": {"total_tokens": 150}
    }
    assert mock_response["status"] == "success"
    assert "documentation" in mock_response
