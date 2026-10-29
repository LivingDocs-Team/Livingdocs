from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_analyze_repo_api_success():
    """LD-372: Gọi API POST /api/v1/analyze-repo thành công (200 OK)"""
    payload = {
        "target": "livingdocs_test",
        "scope": "repository",
        "files": [
            {
                "path": "app/calculator.py",
                "content": "def add(a: int, b: int) -> int:\n    return a + b",
                "language": "python"
            }
        ]
    }
    response = client.post("/api/v1/analyze-repo", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["target"] == "livingdocs_test"
    assert data["files"][0]["status"] == "ok"

def test_analyze_repo_api_validation_error():
    """LD-372: Kiểm tra validation 422 khi danh sách files rỗng"""
    payload = {"target": "empty", "scope": "repository", "files": []}
    response = client.post("/api/v1/analyze-repo", json=payload)
    assert response.status_code == 422

def test_analyze_repo_api_unsupported_language():
    """LD-372: Kiểm tra xử lý ngôn ngữ chưa hỗ trợ"""
    payload = {
        "target": "test",
        "scope": "file",
        "files": [{"path": "main.rb", "content": "puts 'hello'", "language": "ruby"}]
    }
    response = client.post("/api/v1/analyze-repo", json=payload)
    assert response.status_code == 200
    assert response.json()["files"][0]["status"] == "unsupported"


def test_health_endpoint():
    """LD-397: /health is used by the Docker Compose healthcheck"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "code-analyzer"}
