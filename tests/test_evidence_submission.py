import pytest
from fastapi.testclient import TestClient

# Import ứng dụng chính FastAPI đã kết nối các router LD-106
from app.main import app
from app.submission import STATUS_STORE, SUBMISSION_STORE, EVIDENCE_STORE

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
    """Yêu cầu 4 của Lead: Truy vấn Job không tồn tại phải trả về 404 Not Found"""
    response = client.get("/status/non-existent-job-999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_get_status_processing():
    """Truy vấn Job đang trong quá trình xử lý"""
    STATUS_STORE["job-123"] = {"status": "processing", "progress": 50}
    response = client.get("/status/job-123")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processing"
    assert data["progress"] == 50

def test_get_status_completed():
    """Truy vấn Job đã hoàn thành"""
    STATUS_STORE["job-123"] = {"status": "completed", "progress": 100}
    response = client.get("/status/job-123")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

# ==========================================
# 2. KIỂM THỬ EVIDENCES (/evidence/{job_id})
# ==========================================

def test_get_evidence_job_not_found():
    """Truy vấn Evidence của Job không tồn tại phải trả về 404"""
    response = client.get("/evidence/non-existent-job")
    assert response.status_code == 404

def test_get_evidence_job_not_completed():
    """Yêu cầu 4 của Lead: Truy vấn Evidence khi Job chưa hoàn thành (chờ processing)"""
    STATUS_STORE["job-in-progress"] = {"status": "processing", "progress": 30}
    response = client.get("/evidence/job-in-progress")
    assert response.status_code == 400
    assert "not completed" in response.json()["detail"].lower()

def test_get_evidence_success_real_source():
    """Yêu cầu 2 của Lead: Trích xuất Evidence thành công từ mã nguồn thật"""
    STATUS_STORE["job-real"] = {"status": "completed", "progress": 100}
    EVIDENCE_STORE["job-real"] = [
        {
            "file_path": "app/main.py",
            "start_line": 10,
            "end_line": 25,
            "commit_hash": "a015e2f",
            "source_code": "def main():\n    return {'status': 'ok'}"
        }
    ]
    response = client.get("/evidence/job-real")
    assert response.status_code == 200
    evidences = response.json()
    assert len(evidences) == 1
    assert evidences[0]["file_path"] == "app/main.py"
    assert "def main():" in evidences[0]["source_code"]

def test_get_evidence_missing_source():
    """Yêu cầu 2 của Lead: Không có source_code thì báo thiếu evidence, không sinh text giả định"""
    STATUS_STORE["job-no-source"] = {"status": "completed", "progress": 100}
    # Để trống danh sách evidence khi nguồn không trích xuất được AST source
    EVIDENCE_STORE["job-no-source"] = []
    
    response = client.get("/evidence/job-no-source")
    assert response.status_code == 404
    assert "no evidence" in response.json()["detail"].lower()

# ==========================================
# 3. KIỂM THỬ SUBMISSION (/submit)
# ==========================================

def test_submit_success():
    """Submit thành công khi thông tin hợp lệ"""
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
                "source_code": "print('valid source')"
            }
        ]
    }
    response = client.post("/submit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "submitted"
    assert "submission_id" in data

def test_submit_without_evidence():
    """Yêu cầu 4 của Lead: Submit thiếu Evidence phải báo lỗi 400 Bad Request"""
    STATUS_STORE["job-empty-ev"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-empty-ev",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "a015e2f",
        "evidence_list": []  # Thiếu evidence
    }
    response = client.post("/submit", json=payload)
    assert response.status_code == 400
    assert "evidence" in response.json()["detail"].lower()

def test_submit_duplicate():
    """Yêu cầu 4 của Lead: Submit trùng lặp cho cùng 1 job_id phải bị từ chối 400"""
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
    # Lần 1: Thành công
    res1 = client.post("/submit", json=payload)
    assert res1.status_code == 200
    
    # Lần 2: Submit trùng
    res2 = client.post("/submit", json=payload)
    assert res2.status_code == 400
    assert "already submitted" in res2.json()["detail"].lower()
