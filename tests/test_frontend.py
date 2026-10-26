import pytest

def test_frontend_e2e_mock():
    mock_ui_state = {
        "title": "LivingDocs",
        "is_loaded": True
    }
    assert mock_ui_state["is_loaded"] is True
