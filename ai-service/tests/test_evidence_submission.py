import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

SAMPLE_FILE = {
    "path": "app/models.py",
    "language": "python",
    "classes": [
        {
            "name": "GroundingEvidence",
            "docstring": "Evidence model.",
            "line_start": 10,
            "line_end": 15,
            "methods": []
        }
    ]
}

def test_ld111_full_evidence_and_submission_suite():
    # 1. Khởi tạo sinh tài liệu
    res = client.post("/generate", json={
        "scope": "file",
        "target": "app/models.py",
        "files": [SAMPLE_FILE]
    })
    assert res.status_code == 202
    job_id = res.json()["id"]

    # 2. Test LD-109: Display Generation Status
    status_res = client.get(f"/api/v1/documents/{job_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "completed"
    assert status_res.json()["progress_percentage"] == 100.0

    # 3. Test LD-107 & LD-108: Collect & Display Evidence
    ev_res = client.get(f"/api/v1/documents/{job_id}/evidence")
    assert ev_res.status_code == 200
    ev_list = ev_res.json()
    assert len(ev_list) > 0
    assert ev_list[0]["file_path"] == "app/models.py"

    # 4. Test LD-110: Submit Documentation Workflow
    sub_res = client.post(f"/api/v1/documents/{job_id}/submit?submitted_by=lamgiahuy")
    assert sub_res.status_code == 200
    assert sub_res.json()["status"] == "submitted"

    # 5. Test LD-110: Duplicate Submission Check (Conflict)
    re_sub = client.post(f"/api/v1/documents/{job_id}/submit")
    assert re_sub.status_code == 409
