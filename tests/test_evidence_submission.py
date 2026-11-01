import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models import FileAnalysis, Function
from app.submission import EvidenceCollector, StatusTracker, STORAGE_FILE

client = TestClient(app)

@pytest.fixture(autouse=True)
def cleanup_storage():
    if os.path.exists(STORAGE_FILE):
        os.remove(STORAGE_FILE)
    yield
    if os.path.exists(STORAGE_FILE):
        os.remove(STORAGE_FILE)

def test_evidence_extraction_rejects_empty_source():
    """Trích xuất evidence: nếu thiếu source thì không tạo evidence giả."""
    doc_id = "doc-no-source"
    mock_files = [
        FileAnalysis(
            path="app/submission.py",
            functions=[Function(name="empty_func", lineno=10, end_lineno=12, source="")]
        )
    ]
    evidences = EvidenceCollector.extract_from_analysis(doc_id, mock_files, commit_hash="hash-001")
    assert len(evidences) == 0

def test_api_job_not_found_returns_404():
    """Kiểm tra Job không tồn tại trả về HTTP 404."""
    res = client.get("/api/v1/documents/unknown-job-id/status")
    assert res.status_code == 404

def test_api_submit_incomplete_job_returns_400():
    """Kiểm tra Submit khi Job chưa hoàn thành trả về HTTP 400."""
    doc_id = "doc-in-progress"
    StatusTracker.update_status(doc_id, progress=50, status_str="processing")
    
    res = client.post(f"/api/v1/documents/{doc_id}/submit?submitted_by=danglhh")
    assert res.status_code == 400

def test_api_submit_missing_evidence_returns_422():
    """Kiểm tra Submit khi thiếu Evidence trả về HTTP 422."""
    doc_id = "doc-no-evi"
    StatusTracker.update_status(doc_id, progress=100, status_str="completed")
    
    res = client.post(f"/api/v1/documents/{doc_id}/submit?submitted_by=danglhh")
    assert res.status_code == 422

def test_persistence_across_restarts():
    """Kiểm tra tính bền vững (Persistence) của dữ liệu sau khi khởi động lại app."""
    doc_id = "doc-persist"
    mock_files = [
        FileAnalysis(
            path="app/main.py",
            functions=[Function(name="main", lineno=1, end_lineno=5, source="def main(): pass")]
        )
    ]
    EvidenceCollector.extract_from_analysis(doc_id, mock_files, commit_hash="commit-123")
    StatusTracker.update_status(doc_id, progress=100, status_str="completed")
    
    res_sub = client.post(f"/api/v1/documents/{doc_id}/submit?submitted_by=danglhh")
    assert res_sub.status_code == 200

    # Giả lập restart service bằng TestClient mới
    new_client = TestClient(app)
    res_get = new_client.get(f"/api/v1/documents/{doc_id}/submission")
    assert res_get.status_code == 200
    assert res_get.json()["submitted_by"] == "danglhh"
