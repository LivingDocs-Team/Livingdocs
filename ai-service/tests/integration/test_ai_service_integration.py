import os
import pytest

os.environ["ANTHROPIC_API_KEY"] = "mock_key_for_ci_pipeline"

def test_ai_service_integration_base():
    """Integration test base cho AI Service"""
    assert os.environ.get("ANTHROPIC_API_KEY") == "mock_key_for_ci_pipeline"
