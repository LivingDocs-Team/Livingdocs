import pytest
from unittest.mock import patch, MagicMock

def mock_generate_ai_docs(analysis_data: dict, api_key: str = None):
    """Hàm giả lập gọi AI Service"""
    if not api_key:
        return {"status": "fallback", "markdown": "# Basic Docs (Offline Mode)"}
    if analysis_data.get("timeout"):
        raise TimeoutError("AI Gateway Timeout")
    return {"status": "completed", "markdown": "# AI Generated Documentation"}

def test_ai_service_offline_fallback():
    """LD-374: Kiểm tra chế độ Offline Fallback khi thiếu API Key"""
    res = mock_generate_ai_docs({"files": []}, api_key=None)
    assert res["status"] == "fallback"
    assert "Basic Docs" in res["markdown"]

def test_ai_service_timeout_handling():
    """LD-374: Kiểm tra xử lý timeout khi kết nối AI Gateway"""
    with pytest.raises(TimeoutError):
        mock_generate_ai_docs({"timeout": True}, api_key="sk-test-key")
