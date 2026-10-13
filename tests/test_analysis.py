from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_unsupported_and_empty_file():
    res = client.post("/api/v1/analyze-repo", json={
        "scope": "file",
        "target": "test",
        "file_paths": ["non_existent_file.txt"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["files"][0]["status"] in ["unsupported", "invalid"]
