import os
import pytest
from unittest.mock import patch, MagicMock

def mock_call_ai_service(prompt: str):
    """Giả lập gọi AI Service khi chạy CI/CD"""
    api_key = os.getenv("ANTHROPIC_API_KEY", "mock_key_for_ci")
    if not api_key:
        return {"status": "error", "message": "Missing API Key"}
    return {
        "status": "success",
        "generated_doc": "# AI Generated Documentation\n\nThis is a mock doc for CI pipeline.",
        "usage": {"input_tokens": 10, "output_tokens": 20}
    }

def test_ai_service_integration_success():
    """CI Test: Kiểm thử tích hợp AI Service thành công"""
    response = mock_call_ai_service("Explain this code")
    assert response["status"] == "success"
    assert "Generated Documentation" in response["generated_doc"]

@patch("os.getenv")
def test_ai_service_missing_key(mock_getenv):
    """CI Test: Kiểm thử trường hợp thiếu API Key"""
    mock_getenv.return_value = ""
    response = mock_call_ai_service("Explain this code")
    assert response["status"] == "error"
