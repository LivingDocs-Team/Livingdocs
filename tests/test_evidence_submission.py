"""LD-402 Fix evidence & submission persistence (PR #108, code-analyzer /api/v1).

Confirmed bugs of PR #108, reproduced before the fix:
    1. evidences and submissions lived in two module dictionaries: after a restart, submitting
       a submission gave 404 and reusing an evidence gave 400
    2. nothing could be read back (no GET endpoint)
    3. EvidenceResponse was declared twice; the second class dropped created_at and metadata
    4. the analyzer image runs as an unprivileged user and had no writable data folder / volume
"""
import json
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.models import EvidenceCreate, SubmissionCreate
from app.submissions import SubmissionError, SubmissionStore

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = {"task_id": "LD-402", "evidence_type": "test_result", "file_path": "artifacts/report.json",
            "description": "E2E output", "metadata": {"run": 42}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = SubmissionStore(str(tmp_path / "submissions.json"))
    monkeypatch.setattr(main, "submissions", store)
    return TestClient(main.app), store


# ---------- API ----------

def test_evidence_response_keeps_created_at_and_metadata(client):
    c, _ = client
    ev = c.post("/api/v1/evidences", json=EVIDENCE)
    assert ev.status_code == 201
    body = ev.json()
    assert body["id"].startswith("ev-") and body["created_at"] and body["metadata"] == {"run": 42}
    assert c.get(f"/api/v1/evidences/{body['id']}").json() == body
    assert c.get("/api/v1/evidences/ev-missing").status_code == 404


def test_submission_workflow_can_be_read_back(client):
    c, _ = client
    ev = c.post("/api/v1/evidences", json=EVIDENCE).json()
    sub = c.post("/api/v1/submissions", json={"task_id": "LD-402", "title": "Evidence", "notes": "done",
                                              "evidence_ids": [ev["id"], ev["id"]]}).json()
    assert sub["status"] == "DRAFT" and sub["notes"] == "done" and [e["id"] for e in sub["evidences"]] == [ev["id"]]
    done = c.post(f"/api/v1/submissions/{sub['id']}/submit")
    assert done.status_code == 200 and done.json()["status"] == "SUBMITTED" and done.json()["submitted_at"]
    again = c.post(f"/api/v1/submissions/{sub['id']}/submit")           # retry: same result
    assert again.status_code == 200 and again.json()["submitted_at"] == done.json()["submitted_at"]
    assert c.get(f"/api/v1/submissions/{sub['id']}").json() == done.json()
    assert [s["id"] for s in c.get("/api/v1/submissions", params={"task_id": "LD-402"}).json()] == [sub["id"]]
    assert c.get("/api/v1/submissions", params={"task_id": "LD-999"}).json() == []


def test_submission_errors(client):
    c, _ = client
    missing = c.post("/api/v1/submissions", json={"task_id": "t", "title": "t", "evidence_ids": ["ev-nope"]})
    assert missing.status_code == 400 and "ev-nope" in missing.json()["detail"]
    empty = c.post("/api/v1/submissions", json={"task_id": "t", "title": "t", "evidence_ids": []}).json()
    assert c.post(f"/api/v1/submissions/{empty['id']}/submit").status_code == 400
    assert c.post("/api/v1/submissions/sub-nope/submit").status_code == 404
    assert c.get("/api/v1/submissions/sub-nope").status_code == 404


# ---------- persistence ----------

def test_store_survives_a_restart(tmp_path):
    path = tmp_path / "submissions.json"
    store = SubmissionStore(str(path))
    ev = store.add_evidence(EvidenceCreate(**EVIDENCE))
    sub = store.add_submission(SubmissionCreate(task_id="LD-402", title="t", evidence_ids=[ev.id]))
    store.submit(sub.id)

    again = SubmissionStore(str(path))                      # "restart" on the same file
    assert again.evidence(ev.id) == ev
    assert again.submission(sub.id) == store.submission(sub.id)
    assert again.submission(sub.id).status.value == "SUBMITTED"
    reuse = again.add_submission(SubmissionCreate(task_id="LD-402", title="again", evidence_ids=[ev.id]))
    assert reuse.evidences == [ev]
    assert not path.with_suffix(".tmp").exists()            # atomic write left nothing behind


def test_corrupt_file_is_moved_aside(tmp_path):
    path = tmp_path / "submissions.json"
    path.write_text("{not json", encoding="utf-8")
    store = SubmissionStore(str(path))
    assert store.submissions() == [] and not path.exists()
    assert len(list(tmp_path.glob("submissions.corrupt-*.json"))) == 1


def test_in_memory_mode_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = SubmissionStore(None)
    store.add_evidence(EvidenceCreate(**EVIDENCE))
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(SubmissionError) as e:
        store.submit("sub-x")
    assert e.value.status == 404


RESTART_SCRIPT = textwrap.dedent('''
    import json, sys
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    if sys.argv[1] == "write":
        ev = c.post("/api/v1/evidences", json={"task_id": "LD-402", "evidence_type": "log",
                                              "file_path": "ci.log"}).json()
        sub = c.post("/api/v1/submissions", json={"task_id": "LD-402", "title": "t",
                                                  "evidence_ids": [ev["id"]]}).json()
        c.post("/api/v1/submissions/%s/submit" % sub["id"])
        print(json.dumps([ev["id"], sub["id"]]))
    else:
        ev, sub = sys.argv[2], sys.argv[3]
        out = {"evidence": c.get("/api/v1/evidences/" + ev).status_code,
               "submission": c.get("/api/v1/submissions/" + sub).json().get("status"),
               "submit_again": c.post("/api/v1/submissions/%s/submit" % sub).status_code,
               "reuse_evidence": c.post("/api/v1/submissions", json={"task_id": "LD-402", "title": "t2",
                                                                    "evidence_ids": [ev]}).status_code}
        print(json.dumps(out))
''')


def test_evidence_and_submission_survive_a_real_restart(tmp_path):
    """Two separate processes configured with the same SUBMISSIONS_FILE (the compose setup)."""
    env = {**os.environ, "SUBMISSIONS_FILE": str(tmp_path / "submissions.json"),
           "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")])}

    def run(*args):
        r = subprocess.run([sys.executable, "-c", RESTART_SCRIPT, *args], cwd=tmp_path, env=env,
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])

    ev, sub = run("write")
    assert run("read", ev, sub) == {"evidence": 200, "submission": "SUBMITTED", "submit_again": 200,
                                    "reuse_evidence": 201}


def test_container_is_configured_to_keep_the_file():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    analyzer = compose.split("  code-analyzer:", 1)[1].split("\n  github-integration:", 1)[0]
    assert "SUBMISSIONS_FILE: /app/data/submissions.json" in analyzer
    assert "- analyzer-data:/app/data" in analyzer and "\n  analyzer-data:" in compose
    docker = (ROOT / "code-analyzer" / "Dockerfile").read_text(encoding="utf-8")
    assert "chown analyzer /app/data" in docker
    assert docker.index("chown analyzer /app/data") < docker.index("USER analyzer")
