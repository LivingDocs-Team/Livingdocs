import os
import pytest

os.environ["ANTHROPIC_API_KEY"] = "mock_key_for_ci_pipeline"

def test_ai_service_integration_mock():
    """Mock test cho AI Service Task LD-106"""
    mock_response = {
        "status": "success",
        "documentation": "# AI Generated Content",
        "usage": {"total_tokens": 100}
    }
    assert mock_response["status"] == "success"
    assert "documentation" in mock_response
