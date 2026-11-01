import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models import FileAnalysis, Function
from app.submission import EvidenceCollector, StatusTracker, STATUS_STORE, SUBMISSION_STORE, EVIDENCE_STORE

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_stores():
    STATUS_STORE.clear()
    SUBMISSION_STORE.clear()
    EVIDENCE_STORE.clear()

def test_evidence_extraction_with_real_source():
    """Test 1: Kiểm tra trích xuất đúng field path, lineno, end_lineno và source thật."""
    doc_id = "doc-106-real"
    mock_files = [
        FileAnalysis(
            path="app/submission.py",             # Dùng path chuẩn contract
            functions=[
                Function(
                    name="submit_documentation",
                    lineno=45,                   # Dùng lineno chuẩn contract
                    end_lineno=65,               # Dùng end_lineno chuẩn contract
                    source="def submit_documentation(document_id, submitted_by):\n    pass" # Source thật
                )
            ]
        )
    ]
    
    evidences = EvidenceCollector.extract_from_analysis(doc_id, mock_files, commit_hash="git-hash-12345")
    
    assert len(evidences) == 1
    assert evidences[0].file_path == "app/submission.py"
    assert evidences[0].start_line == 45
    assert evidences[0].end_line == 65
    assert "def submit_documentation" in evidences[0].code_snippet

def test_api_status_404_when_job_not_found():
    """Test 2: Kiểm tra API status trả về 404 khi job chưa tồn tại."""
    response = client.get("/api/v1/documents/non-existent-job/status")
    assert response.status_code == 404

def test_full_api_workflow_e2e():
    """Test 3: Kiểm tra toàn bộ luồng qua API HTTP thật."""
    doc_id = "doc-e2e-api"
    
    # 1. Tạo Evidence từ AST gốc
    mock_files = [
        FileAnalysis(
            path="app/main.py",
            functions=[Function(name="main", lineno=1, end_lineno=10, source="def main(): return True")]
        )
    ]
    EvidenceCollector.extract_from_analysis(doc_id, mock_files, commit_hash="commit-001")
    
    # 2. Cập nhật Status hoàn thành
    StatusTracker.update_status(doc_id, progress=100, status_str="completed", step="Done")
    
    # 3. Query Status qua API
    res_status = client.get(f"/api/v1/documents/{doc_id}/status")
    assert res_status.status_code == 200
    assert res_status.json()["progress_percentage"] == 100
    
    # 4. Submit qua API
    res_submit = client.post(f"/api/v1/documents/{doc_id}/submit?submitted_by=lamgiahuy")
    assert res_submit.status_code == 200
    assert res_submit.json()["status"] == "submitted"
    
    # 5. Query Submission record qua API
    res_get_sub = client.get(f"/api/v1/documents/{doc_id}/submission")
    assert res_get_sub.status_code == 200
    assert res_get_sub.json()["submitted_by"] == "lamgiahuy"
