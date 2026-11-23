import itertools
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import main
from app.jobs import JobStore
from app.versions import DocumentStore


def test_internal_analytics_counts_real_outcomes_and_saved_document_history(monkeypatch, tmp_path):
    # The analytics window is built from the jobs' own updated_at values and must be strictly ordered. The system
    # clock ticks about every 0.5 ms on Windows, so two jobs that finish in the same tick would get equal
    # timestamps, make "from" equal "to" and be rejected with 400 (KeyError: 'aiJobs' in this test). A clock that
    # moves forward on every reading makes the order explicit instead of depending on the machine.
    ticks = itertools.count(1)
    start = datetime.now(timezone.utc)
    monkeypatch.setattr("app.jobs.now", lambda: start + timedelta(milliseconds=next(ticks)))
    jobs = JobStore()
    documents_file = tmp_path / "documents.json"
    monkeypatch.setattr(main, "jobs", jobs)
    monkeypatch.setattr(main, "documents", DocumentStore(str(documents_file)))
    monkeypatch.setenv("INTERNAL_API_SECRET", "analytics-test-secret")
    client = TestClient(main.app)
    # The generation worker also refers to its module-level store.
    monkeypatch.setattr("app.jobs.jobs", jobs)

    service_auth = {"Authorization": "Bearer analytics-test-secret"}   # every AI endpoint needs it once the secret is set
    sample = {"path": "example.py", "language": "python",
              "functions": [{"name": "hello", "signature": "def hello()"}]}
    completed = client.post("/generate", json={
        "scope": "file", "target": "example.py", "files": [sample],
    }, headers=service_auth).json()["id"]
    failed = client.post("/generate", json={
        "scope": "file", "target": "example.py",
        "files": [{**sample, "status": "invalid", "error": "Parser failed"}],
    }, headers=service_auth).json()["id"]
    assert jobs.get(completed).status.value == "completed"
    assert jobs.get(failed).status.value == "failed"
    assert client.post("/documents", json={"job_id": completed}, headers=service_auth).status_code == 201
    end = main.documents.list()[0].created_at + timedelta(seconds=1)
    endpoint = "/internal/system-analytics"
    headers = {"Authorization": "Bearer analytics-test-secret"}
    window = {"from": jobs.get(completed).updated_at.isoformat(), "to": end.isoformat()}
    assert client.get(endpoint, params=window).status_code == 401
    assert client.get(endpoint, params=window, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get(endpoint, params={**window, "to": window["from"]}, headers=headers).status_code == 400
    response = client.get(endpoint, params=window, headers=headers)
    assert response.status_code == 200
    activity = response.json()
    assert activity["documentsCreated"] == activity["documentVersionAuditEvents"] == 1
    assert activity["aiJobs"] == {
        "completed": 1, "failed": 1, "scope": "CURRENT_AI_PROCESS",
        "observedSince": jobs.observed_since.isoformat(),
    }

    exclusive = client.get(endpoint, params={**window, "to": jobs.get(failed).updated_at.isoformat()},
                           headers=headers).json()
    assert exclusive["aiJobs"]["completed"] == 1
    assert exclusive["aiJobs"]["failed"] == 0
    assert exclusive["documentsCreated"] == 0

    monkeypatch.setattr(main, "jobs", JobStore())
    monkeypatch.setattr(main, "documents", DocumentStore(str(documents_file)))
    after_restart = client.get(endpoint, params=window, headers=headers).json()
    assert after_restart["documentsCreated"] == after_restart["documentVersionAuditEvents"] == 1
    assert after_restart["aiJobs"]["completed"] == after_restart["aiJobs"]["failed"] == 0
    assert datetime.fromisoformat(after_restart["aiJobs"]["observedSince"]) > jobs.observed_since
