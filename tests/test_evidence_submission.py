import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.submission import STATUS_STORE, SUBMISSION_STORE, EVIDENCE_STORE

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_stores():
    STATUS_STORE.clear()
    SUBMISSION_STORE.clear()
    EVIDENCE_STORE.clear()
    yield


def test_routes_are_registered():
    # Dùng OpenAPI schema vì app.routes không còn ổn định giữa các bản FastAPI
    paths = set(app.openapi()["paths"].keys())
    assert "/submit" in paths
    assert "/status/{job_id}" in paths
    assert "/evidence/{job_id}" in paths
    assert "/jobs" in paths


def test_get_status_not_found():
    """Job không tồn tại trả về 404"""
    response = client.get("/status/non-existent-job-xyz")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_evidence_job_not_found():
    """Evidence của Job không tồn tại trả về 404"""
    response = client.get("/evidence/non-existent-job")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_evidence_job_not_completed():
    """Query evidence khi job chưa hoàn thành trả về 400"""
    STATUS_STORE["job-running"] = {"status": "processing", "progress": 50}
    response = client.get("/evidence/job-running")
    assert response.status_code == 400


def test_get_evidence_missing_source():
    """Không trích xuất được source code thật thì trả 404"""
    STATUS_STORE["job-empty"] = {"status": "completed", "progress": 100}
    EVIDENCE_STORE["job-empty"] = []
    response = client.get("/evidence/job-empty")
    assert response.status_code == 404
    assert "No source code evidence" in response.json()["detail"]


def test_submit_without_evidence_fails():
    """Submit thiếu evidence trả về 400"""
    STATUS_STORE["job-no-ev"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-no-ev",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "a09ebe9",
        "evidence_list": [],
    }
    response = client.post("/submit", json=payload)
    assert response.status_code == 400


def test_submit_duplicate_fails():
    """Submit trùng lặp trả về 400"""
    STATUS_STORE["job-dup"] = {"status": "completed", "progress": 100}
    payload = {
        "job_id": "job-dup",
        "repository": "CNPM/LivingDocs",
        "commit_hash": "a09ebe9",
        "evidence_list": [
            {
                "file_path": "app/main.py",
                "start_line": 1,
                "end_line": 10,
                "commit_hash": "a09ebe9",
                "source_code": "code",
            }
        ],
    }
    res1 = client.post("/submit", json=payload)
    assert res1.status_code == 200
    res2 = client.post("/submit", json=payload)
    assert res2.status_code == 400
