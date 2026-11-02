import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.submission import STATUS_STORE, SUBMISSION_STORE, EVIDENCE_STORE

client = TestClient(app)

PY_SOURCE = '''import os


def hello(name):
    return f"hi {name}"


class Greeter:
    def run(self):
        return hello("x")
'''


@pytest.fixture(autouse=True)
def reset(monkeypatch, tmp_path):
    STATUS_STORE.clear()
    SUBMISSION_STORE.clear()
    EVIDENCE_STORE.clear()
    monkeypatch.setenv("REPOS_BASE_DIR", str(tmp_path))
    yield


def _make_repo(tmp_path, name="repo", files=None):
    root = tmp_path / name
    root.mkdir()
    for fname, content in (files or {}).items():
        (root / fname).write_text(content, encoding="utf-8")
    return root


def test_full_workflow_uses_real_source(tmp_path):
    _make_repo(tmp_path, files={"a.py": PY_SOURCE})
    r = client.post("/jobs", json={"job_id": "j1", "repo_path": "repo", "commit_hash": "abc123"})
    assert r.status_code == 202

    assert client.get("/status/j1").json()["status"] == "completed"

    r = client.get("/evidence/j1")
    assert r.status_code == 200
    items = r.json()
    names = {i["source_code"].splitlines()[0].strip() for i in items}
    assert "def hello(name):" in names
    assert "class Greeter:" in names

    lines = PY_SOURCE.splitlines()
    for it in items:  # evidence phải khớp đúng nội dung file thật
        assert it["source_code"] == "\n".join(lines[it["start_line"] - 1:it["end_line"]])
        assert it["commit_hash"] == "abc123"
        assert it["file_path"] == "a.py"

    sub = {"job_id": "j1", "repository": "CNPM/LivingDocs", "commit_hash": "abc123", "evidence_list": items}
    assert client.post("/submit", json=sub).status_code == 200
    assert client.post("/submit", json=sub).status_code == 400


def test_repo_without_code_returns_404_not_fake_text(tmp_path):
    _make_repo(tmp_path, files={"README.md": "# hi"})
    client.post("/jobs", json={"job_id": "j2", "repo_path": "repo", "commit_hash": "abc"})
    assert client.get("/evidence/j2").status_code == 404


def test_path_traversal_rejected():
    r = client.post("/jobs", json={"job_id": "j3", "repo_path": "../..", "commit_hash": "abc"})
    assert r.status_code == 400


def test_unknown_repo_path_404():
    r = client.post("/jobs", json={"job_id": "j4", "repo_path": "nope", "commit_hash": "abc"})
    assert r.status_code == 404


def test_duplicate_job_id_rejected(tmp_path):
    _make_repo(tmp_path, files={"a.py": PY_SOURCE})
    body = {"job_id": "j5", "repo_path": "repo", "commit_hash": "abc"}
    assert client.post("/jobs", json=body).status_code == 202
    assert client.post("/jobs", json=body).status_code == 400


def test_submit_invalid_line_range_rejected():
    STATUS_STORE["j6"] = {"status": "completed", "progress": 100}
    bad = {"file_path": "a.py", "start_line": 10, "end_line": 2, "commit_hash": "c", "source_code": "x"}
    r = client.post("/submit", json={"job_id": "j6", "repository": "r", "commit_hash": "c", "evidence_list": [bad]})
    assert r.status_code == 400


def test_submit_job_not_completed_rejected():
    STATUS_STORE["j7"] = {"status": "processing", "progress": 10}
    ok = {"file_path": "a.py", "start_line": 1, "end_line": 2, "commit_hash": "c", "source_code": "x"}
    r = client.post("/submit", json={"job_id": "j7", "repository": "r", "commit_hash": "c", "evidence_list": [ok]})
    assert r.status_code == 400
