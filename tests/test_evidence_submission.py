import pytest
from fastapi.testclient import TestClient

# Thử import theo cả 2 cấu hình đường dẫn (có prefix ai-service hoặc root)
try:
    from app.main import app
    from app.submission import STATUS_STORE, SUBMISSION_STORE, EVIDENCE_STORE
except ImportError:
    from ai-service.app.main import app
    from ai-service.app.submission import STATUS_STORE, SUBMISSION_STORE, EVIDENCE_STORE

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_stores():
    """Reset dữ liệu lưu trữ trong bộ nhớ trước mỗi testcase"""
    STATUS_STORE.clear()
    SUBMISSION_STORE.clear()
    EVIDENCE_STORE.clear()
    yield

# ==========================================
# 1. KIỂM THỬ TRẠNG THÁI JOB (/status/{job_id})
# ==========================================

def test_get_status_not_found():
    """Yêu cầu 4 của Lead: Query job không tồn tại phải trả về 404"""
    response = client.get("/status/non-existent-job-999")
    assert response.status_code == 404

def test_get_status_processing():
    """Query job đang xử lý"""
    STATUS_STORE["job-123"] = {"status": "processing", "progress": 50}
    response = client.get("/status/job-123")
    assert response.status_code == 200
    assert response.json()["status"] == "processing"

def test_get_status_completed():
    """Query job đã hoàn thành"""
    STATUS_STORE["job-123"] = {"status": "completed", "progress": 100}
    response = client.get("/status/job-123")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

# ==========================================
# 2. KIỂM THỬ EVIDENCES (/evidence/{job_id})
# ==========================================

def test_get_evidence_job_not_found():
    """Query evidence job không tồn tại trả về 404"""
    response = client.get("/evidence/non-existent-job")
    assert response.status_code == 404

def test_get_evidence_job_not_completed():
    """Query evidence khi job chưa hoàn thành trả về 400"""
    STATUS_STORE["job-in-progress"] = {"status": "processing", "progress": 30}
    response = client.get("/evidence/job-in-progress")
    assert response.status_code == 400

def test_get_evidence_success_real_source():
    """Query evidence thành công với mã nguồn thực tế"""
    STATUS_STORE["job-real"] = {"status": "completed", "progress": 100}
    EVIDENCE_STORE["job-real"] = [
        {
            "file_path": "app/main.py",
            "start_line": 10,
            "end_line": 25,
            "commit_hash": "a015e2f",
            "source_code": "def main(): return {'status': 'ok'}"
        }
    ]
    response = client.get("/evidence/job-real")
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_get_evidence_missing_source():
    """Thiếu source code thực tế trả về 404, không tự sinh text giả định"""
    STATUS_STORE["job-no-source"] = {"status": "completed", "progress": 100}
    EVIDENCE_STORE["job-no-source"] = []
    response = client.get("/evidence/job-no-source")
    assert response.status_code == 404

# ==========================================
# 3. KIỂM THỬ SUBMISSION (/submit)
# ==========================================

def test_submit_success():
    """Submit hợp lệ thành công"""
    STATUS_STORE["job-submit-ok"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-submit-ok",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "a015e2f",
        "evidence_list": [
            {
                "file_path": "app/submission.py",
                "start_line": 1,
                "end_line": 50,
                "commit_hash": "a015e2f",
                "source_code": "print('valid')"
            }
        ]
    }
    response = client.post("/submit", json=payload)
    assert response.status_code == 200

def test_submit_without_evidence():
    """Submit thiếu evidence báo lỗi 400"""
    STATUS_STORE["job-empty-ev"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-empty-ev",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "a015e2f",
        "evidence_list": []
    }
    response = client.post("/submit", json=payload)
    assert response.status_code == 400

def test_submit_duplicate():
    """Submit trùng lặp báo lỗi 400"""
    STATUS_STORE["job-dup"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-dup",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "a015e2f",
        "evidence_list": [
            {
                "file_path": "app/main.py",
                "start_line": 1,
                "end_line": 10,
                "commit_hash": "a015e2f",
                "source_code": "code"
            }
        ]
    }
    client.post("/submit", json=payload)
    res2 = client.post("/submit", json=payload)
    assert res2.status_code == 400
