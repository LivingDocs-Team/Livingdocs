import sys
import os
import pytest
from fastapi.testclient import TestClient

# Đảm bảo PYTHONPATH nhận diện được cả ai-service và root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../ai-service")))

try:
    from app.main import app
    from app.submission import STATUS_STORE, SUBMISSION_STORE, EVIDENCE_STORE
except ImportError:
    from main import app
    from submission import STATUS_STORE, SUBMISSION_STORE, EVIDENCE_STORE

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_stores():
    """Reset dữ liệu bộ nhớ trước mỗi testcase"""
    STATUS_STORE.clear()
    SUBMISSION_STORE.clear()
    EVIDENCE_STORE.clear()
    yield

# ==========================================
# 1. KIỂM THỬ TRẠNG THÁI JOB (/status/{job_id})
# ==========================================

def test_get_status_not_found():
    """Yêu cầu 4 của Lead: Query job không tồn tại phải trả 404"""
    response = client.get("/status/non-existent-job-xyz")
    assert response.status_code == 404

def test_get_status_processing():
    """Query job đang xử lý"""
    STATUS_STORE["job-1"] = {"status": "processing", "progress": 50}
    response = client.get("/status/job-1")
    assert response.status_code == 200
    assert response.json()["status"] == "processing"

# ==========================================
# 2. KIỂM THỬ EVIDENCES (/evidence/{job_id})
# ==========================================

def test_get_evidence_job_not_found():
    """Query evidence của job không tồn tại trả về 404"""
    response = client.get("/evidence/non-existent-job")
    assert response.status_code == 404

def test_get_evidence_job_not_completed():
    """Query evidence khi job chưa xong trả về 400"""
    STATUS_STORE["job-running"] = {"status": "processing", "progress": 50}
    response = client.get("/evidence/job-running")
    assert response.status_code == 400

def test_get_evidence_success_real_source():
    """Query evidence với source code thật"""
    STATUS_STORE["job-ok"] = {"status": "completed", "progress": 100}
    EVIDENCE_STORE["job-ok"] = [
        {
            "file_path": "app/main.py",
            "start_line": 1,
            "end_line": 20,
            "commit_hash": "e44381",
            "source_code": "def health_check(): return {'status': 'ok'}"
        }
    ]
    response = client.get("/evidence/job-ok")
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_get_evidence_missing_source():
    """Yêu cầu 2 của Lead: Thiếu source code thực tế trả về 404, không tự chế text"""
    STATUS_STORE["job-empty"] = {"status": "completed", "progress": 100}
    EVIDENCE_STORE["job-empty"] = []
    response = client.get("/evidence/job-empty")
    assert response.status_code == 404

# ==========================================
# 3. KIỂM THỬ SUBMISSION (/submit)
# ==========================================

def test_submit_success():
    """Submit hợp lệ thành công"""
    STATUS_STORE["job-sub"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-sub",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "e44381",
        "evidence_list": [
            {
                "file_path": "app/main.py",
                "start_line": 1,
                "end_line": 10,
                "commit_hash": "e44381",
                "source_code": "code"
            }
        ]
    }
    response = client.post("/submit", json=payload)
    assert response.status_code == 200

def test_submit_without_evidence():
    """Yêu cầu 4 của Lead: Submit thiếu evidence trả về 400"""
    STATUS_STORE["job-no-ev"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-no-ev",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "e44381",
        "evidence_list": []
    }
    response = client.post("/submit", json=payload)
    assert response.status_code == 400

def test_submit_duplicate():
    """Yêu cầu 4 của Lead: Submit trùng lặp trả về 400"""
    STATUS_STORE["job-dup"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-dup",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "e44381",
        "evidence_list": [
            {
                "file_path": "app/main.py",
                "start_line": 1,
                "end_line": 10,
                "commit_hash": "e44381",
                "source_code": "code"
            }
        ]
    }
    client.post("/submit", json=payload)
    res2 = client.post("/submit", json=payload)
    assert res2.status_code == 400
