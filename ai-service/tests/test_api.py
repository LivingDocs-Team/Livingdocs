import logging
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # tests use the offline generator

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

client = TestClient(app)

SAMPLE_FILE = {
    "path": "src/users/service.py",
    "language": "python",
    "module": "users",
    "classes": [{
        "name": "UserService",
        "docstring": "Manages users.",
        "methods": [{
            "name": "get_user",
            "parameters": [{"name": "user_id", "type": "int"}],
            "return_type": "User",
        }],
    }],
    "functions": [{"name": "hash_password", "parameters": [{"name": "raw", "type": "str"}],
                   "return_type": "str"}],
    "endpoints": [{"http_method": "get", "path": "/users/{id}", "handler": "get_user",
                   "parameters": [{"name": "id", "type": "int"}], "response": "User JSON"}],
}


def test_generate_file_docs():
    r = client.post("/generate", json={"scope": "file", "target": "src/users/service.py",
                                       "files": [SAMPLE_FILE]})
    assert r.status_code == 202
    job_id = r.json()["id"]

    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "completed", job
    assert job["progress"] == 1.0

    md = client.get(f"/jobs/{job_id}/result").text
    for expected in ["UserService", "get_user", "user_id", "hash_password",
                     "GET /users/{id}", "**Giá trị trả về:** `User`"]:
        assert expected in md


def test_failed_job_logs_state_without_source_details(caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error.jobs"):
        response = client.post("/generate", json={
            "scope": "file", "target": SAMPLE_FILE["path"],
            "files": [{**SAMPLE_FILE, "status": "invalid", "error": "Parser failed"}],
        })
    assert response.status_code == 202
    job_id = response.json()["id"]
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error"] == "No documentation could be generated for any file"
    assert [record.getMessage() for record in caplog.records
            if record.name == "uvicorn.error.jobs"] == [
        f"Documentation job {job_id}: pending",
        f"Documentation job {job_id}: running",
        f"Documentation job {job_id}: failed",
    ]


def test_repository_scope_has_overview():
    second = {**SAMPLE_FILE, "path": "src/auth.py"}
    r = client.post("/generate", json={"scope": "repository", "target": "Livingdocs",
                                       "files": [SAMPLE_FILE, second]})
    md = client.get(f"/jobs/{r.json()['id']}/result").text
    assert md.startswith("# Livingdocs")
    assert "src/auth.py" in md


def test_custom_template_controls_sections():
    tpl = client.post("/templates", json={"name": "Endpoints only", "instructions": "x",
                                          "sections": ["API Endpoints"]}).json()
    r = client.post("/generate", json={"scope": "file", "target": "f", "template_id": tpl["id"],
                                       "files": [SAMPLE_FILE]})
    md = client.get(f"/jobs/{r.json()['id']}/result").text
    assert "## API Endpoints" in md and "## Classes" not in md


def test_built_in_template_is_protected_and_unknown_template_rejected():
    assert client.delete("/templates/default").status_code == 403
    r = client.post("/generate", json={"scope": "file", "target": "f", "template_id": "nope",
                                       "files": [SAMPLE_FILE]})
    assert r.status_code == 404

