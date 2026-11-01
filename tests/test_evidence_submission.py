import pytest
from fastapi.testclient import TestClient

# Import linh hoạt đường dẫn app
try:
    from app.main import app
    from app.submission import STATUS_STORE, SUBMISSION_STORE, EVIDENCE_STORE
except ImportError:
    from ai_service.app.main import app
    from ai_service.app.submission import STATUS_STORE, SUBMISSION_STORE, EVIDENCE_STORE

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_in_memory_stores():
    """Reset sạch dữ liệu trong RAM trước mỗi test case"""
    STATUS_STORE.clear()
    SUBMISSION_STORE.clear()
    EVIDENCE_STORE.clear()
    yield

# --- Test API Status ---
def test_get_status_job_not_found():
    """Query Job không tồn tại -> 404 Not Found"""
    response = client.get("/status/non-existent-job-xyz")
    assert response.status_code == 404

def test_get_status_processing():
    """Query Job đang chạy -> 200 OK"""
    STATUS_STORE["job-1"] = {"status": "processing", "progress": 40}
    response = client.get("/status/job-1")
    assert response.status_code == 200
    assert response.json()["status"] == "processing"

# --- Test API Evidence ---
def test_get_evidence_job_not_found():
    """Query Evidence của Job không tồn tại -> 404 Not Found"""
    response = client.get("/evidence/non-existent-job")
    assert response.status_code == 404

def test_get_evidence_job_not_completed():
    """Query Evidence khi Job chưa hoàn thành -> 400 Bad Request"""
    STATUS_STORE["job-running"] = {"status": "processing", "progress": 50}
    response = client.get("/evidence/job-running")
    assert response.status_code == 400

def test_get_evidence_success_with_real_source():
    """Query Evidence thành công từ source code thật"""
    STATUS_STORE["job-ok"] = {"status": "completed", "progress": 100}
    EVIDENCE_STORE["job-ok"] = [
        {
            "file_path": "app/main.py",
            "start_line": 1,
            "end_line": 20,
            "commit_hash": "6a0ba68",
            "source_code": "def health_check(): return {'status': 'ok'}"
        }
    ]
    response = client.get("/evidence/job-ok")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "source_code" in data[0]

def test_get_evidence_missing_source_returns_404():
    """Nếu không trích xuất được source code thật -> Không tự chế text, trả 404"""
    STATUS_STORE["job-empty"] = {"status": "completed", "progress": 100}
    EVIDENCE_STORE["job-empty"] = []
    response = client.get("/evidence/job-empty")
    assert response.status_code == 404

# --- Test API Submit ---
def test_submit_success():
    """Submit hợp lệ -> 200 OK"""
    STATUS_STORE["job-sub"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-sub",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "6a0ba68",
        "evidence_list": [
            {
                "file_path": "app/main.py",
                "start_line": 1,
                "end_line": 10,
                "commit_hash": "6a0ba68",
                "source_code": "code"
            }
        ]
    }
    response = client.post("/submit", json=payload)
    assert response.status_code == 200

def test_submit_without_evidence_fails():
    """Submit thiếu evidence -> 400 Bad Request"""
    STATUS_STORE["job-no-ev"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-no-ev",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "6a0ba68",
        "evidence_list": []
    }
    response = client.post("/submit", json=payload)
    assert response.status_code == 400

def test_submit_duplicate_fails():
    """Submit trùng lặp -> 400 Bad Request"""
    STATUS_STORE["job-dup"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-dup",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "6a0ba68",
        "evidence_list": [
            {
                "file_path": "app/main.py",
                "start_line": 1,
                "end_line": 10,
                "commit_hash": "6a0ba68",
                "source_code": "code"
            }
        ]
    }
    client.post("/submit", json=payload)
    res2 = client.post("/submit", json=payload)
    assert res2.status_code == 400
