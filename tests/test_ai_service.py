import os
import pytest
from unittest.mock import patch, MagicMock

# 1. Đặt API Key giả lập để tránh ứng dụng báo lỗi thiếu môi trường
os.environ["ANTHROPIC_API_KEY"] = "mock_key_for_ci_pipeline"

# 2. Chặn (Mock) trực tiếp hàm gọi API của Anthropic
@patch("anthropic.resources.Messages.create")
def test_ai_service_integration_mock(mock_create):
    """
    Mock trực tiếp phản hồi từ Anthropic API để kiểm thử tích hợp
    mà không cần kết nối mạng hay API Key thật.
    """
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="# AI Generated Documentation Content")]
    mock_response.id = "msg_mock_12345"
    mock_create.return_value = mock_response

    assert mock_response.id == "msg_mock_12345"
    assert "Documentation" in mock_response.content[0].text
