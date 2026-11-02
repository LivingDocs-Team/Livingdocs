import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    """Kiểm tra healthcheck khôi phục đúng (L01)"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_submit_success():
    """Submit hợp lệ bằng dữ liệu thật thành công"""
    payload = {
        "job_id": "job-106-xyz",
        "document_id": "doc-106",
        "author": "Developer",
        "evidences": [
            {
                "file_path": "app/models.py",
                "start_line": 10,
                "end_line": 20,
                "code_snippet": "class GroundingEvidence(BaseModel):",
                "job_id": "job-106-xyz",
                "repository_url": "https://github.com/org/repo",
                "commit_hash": "a1b2c3d4e5f6"
            }
        ]
    }
    response = client.post("/api/v1/documents/submit", json=payload)
    assert response.status_code == 200
    assert response.json()["workflow_status"] == "submitted"

def test_submit_duplicate_fails():
    """Chống submit trùng lặp (409 Conflict)"""
    payload = {
        "job_id": "job-106-xyz",
        "document_id": "doc-106",
        "author": "Developer",
        "evidences": [{
            "file_path": "app/models.py",
            "start_line": 10,
            "end_line": 20,
            "code_snippet": "class GroundingEvidence(BaseModel):",
            "job_id": "job-106-xyz",
            "repository_url": "https://github.com/org/repo",
            "commit_hash": "a1b2c3d4e5f6"
        }]
    }
    response = client.post("/api/v1/documents/submit", json=payload)
    assert response.status_code == 409

def test_submit_uncompleted_job_fails():
    """Từ chối submit khi job chưa hoàn thành (400 Bad Request)"""
    payload = {
        "job_id": "job-pending-123",
        "document_id": "doc-pending",
        "author": "Developer",
        "evidences": [{
            "file_path": "app/models.py",
            "start_line": 1,
            "end_line": 5,
            "code_snippet": "test",
            "job_id": "job-pending-123",
            "repository_url": "https://github.com/org/repo",
            "commit_hash": "a1b2c3d4e5f6"
        }]
    }
    response = client.post("/api/v1/documents/submit", json=payload)
    assert response.status_code == 400

def test_submit_fake_evidence_commit_fails():
    """Từ chối khi evidence chứa commit/repo giả không thuộc job (400 Bad Request)"""
    payload = {
        "job_id": "job-106-xyz",
        "document_id": "doc-106",
        "author": "Developer",
        "evidences": [{
            "file_path": "app/models.py",
            "start_line": 1,
            "end_line": 5,
            "code_snippet": "test",
            "job_id": "job-106-xyz",
            "repository_url": "https://github.com/org/fake-repo",
            "commit_hash": "000000"
        }]
    }
    response = client.post("/api/v1/documents/submit", json=payload)
    assert response.status_code == 400
