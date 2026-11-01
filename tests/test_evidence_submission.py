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

def test_evidence_extraction_requires_real_source():
    """Kiểm tra: Thiếu source thực tế thì không tự tạo evidence giả lập."""
    doc_id = "doc-real-source"
    
    files_with_source = [
        FileAnalysis(
            path="app/submission.py",
            functions=[
                Function(name="func1", lineno=10, end_lineno=20, source="def func1(): return True"),
                Function(name="func2_no_source", lineno=21, end_lineno=30, source=None) # Không có source
            ]
        )
    ]
    
    evidences = EvidenceCollector.extract_from_analysis(doc_id, files_with_source, commit_hash="commit-123")
    
    # Chỉ có 1 evidence hợp lệ (func1), func2 bị bỏ qua vì thiếu source thật
    assert len(evidences) == 1
    assert evidences[0].file_path == "app/submission.py"
    assert evidences[0].start_line == 10
    assert evidences[0].end_line == 20
    assert evidences[0].code_snippet == "def func1(): return True"

def test_status_api_404_when_not_exists():
    """Kiểm tra: Truy vấn job chưa tồn tại trả về lỗi HTTP 404."""
    res = client.get("/api/v1/documents/non-existent/status")
    assert res.status_code == 404

def test_full_api_submission_workflow():
    """Kiểm tra: Toàn bộ luồng từ khởi tạo status -> trích xuất evidence -> nộp bài qua HTTP API."""
    doc_id = "doc-e2e-valid"
    
    # 1. Trích xuất evidence thực tế
    files = [FileAnalysis(path="main.py", functions=[Function(name="main", lineno=1, end_lineno=5, source="def main(): pass")])]
    EvidenceCollector.extract_from_analysis(doc_id, files, commit_hash="hash-999")
    
    # 2. Cập nhật tiến độ 100%
    StatusTracker.update_status(doc_id, progress=100, status_str="completed", step="Done")
    
    # 3. Nộp bài qua HTTP API
    response = client.post(f"/api/v1/documents/{doc_id}/submit?submitted_by=lamgiahuy")
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    
    # 4. Nộp trùng -> Trả lỗi HTTP 400
    dup_res = client.post(f"/api/v1/documents/{doc_id}/submit?submitted_by=lamgiahuy")
    assert dup_res.status_code == 400
