import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app

client = TestClient(app)

SAMPLE = '''def ping():
    return "pong"


class Svc:
    def run(self):
        return 1
'''


def analyze(files):
    return client.post(
        "/api/v1/analyze-repo",
        json={"target": "demo", "scope": "full", "files": files},
    )


def test_analysis_returns_real_results_not_empty():
    r = analyze([{"path": "a.py", "content": SAMPLE}])
    assert r.status_code == 200
    body = r.json()
    assert body["files"] != []  # chặn lỗi files=[] quay lại
    f = body["files"][0]
    assert f["path"] == "a.py"
    assert f["status"] == "ok"
    assert f["language"] == "python"
    assert f["functions"] or f["classes"]  # có thực thể trích từ AST


def test_empty_files_list_rejected():
    assert analyze([]).status_code == 422


def test_empty_content_reported():
    f = analyze([{"path": "a.py", "content": "   "}]).json()["files"][0]
    assert f["status"] == "empty"


def test_invalid_python_reported():
    f = analyze([{"path": "bad.py", "content": "def broken(:\n"}]).json()["files"][0]
    assert f["status"] == "invalid"
    assert f["error"]


def test_unsupported_language_reported():
    f = analyze([{"path": "notes.txt", "content": "hello"}]).json()["files"][0]
    assert f["status"] == "unsupported"


def test_submission_routes_coexist_with_analyzer():
    paths = set(app.openapi()["paths"].keys())
    assert "/api/v1/analyze-repo" in paths
    assert "/health" in paths
    assert "/submit" in paths and "/jobs" in paths
