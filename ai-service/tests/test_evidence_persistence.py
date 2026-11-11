"""LD-402 Fix evidence & submission persistence (ai-service part).

Confirmed bugs, reproduced before the fix:
    1. an owner edit after "changes requested" created a version with no evidence: the staff
       reviewer got 404 from /review-evidence and the manager 404 from /evidence for the
       resubmitted version
    2. a rollback copied only evidence_report: /review-evidence of the restored version was 404
    3. files saved before the fix keep those versions without evidence after a restart

Also checked: documents and evidence survive a real restart with DOCUMENTS_FILE configured
(two separate processes on the same file).
"""
import json
import os
import pathlib
import subprocess
import sys
import textwrap

os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.jobs import JobOutput  # noqa: E402
from app.models import (ConfidenceLevel, FileReport, FileResultStatus, JobReport,  # noqa: E402
                        Scope, SourceSnapshot)
from app.version_models import VersionOrigin  # noqa: E402
from app.versions import DocumentStore, repair_evidence  # noqa: E402
from main import app  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECRET = "ld402-internal-secret"
HEADERS = {"Authorization": f"Bearer {SECRET}", "X-User-Id": "73"}
OWNER = {**HEADERS, "X-Document-Owner-Id": "73"}
client = TestClient(app)

REPORT = JobReport(job_id="job-402", template_id="default", confidence=0.8, level=ConfidenceLevel.high,
                   files=[FileReport(path="a.py", status=FileResultStatus.generated, confidence=0.8,
                                     level=ConfidenceLevel.high)])
SNAPSHOT = SourceSnapshot(repository_id="7f9b6c2e-3c1a-4d55-9a4f-111111111111",
                          repository_full_name="acme/shop", branch="main", commit_sha="d" * 40,
                          fetched_at="2026-11-11T10:00:00Z")


def store_with_document(path=None):
    store = DocumentStore(str(path) if path else None)
    out = JobOutput(scope=Scope.file, target="a.py", template_id="default", template_name=None,
                    output_language="en",
                    sections=[("a.py", "# A\n", "generated", 0.8)], confidence=0.8,
                    source_snapshot=SNAPSHOT, evidence_report=REPORT)
    doc = store.create_from_job("job-402", out, actor="73", owner_user_id="73", report=REPORT)
    return store, doc.id


def evidence_of(v):
    return (v.evidence_report.job_id if v.evidence_report else None,
            v.review_report.job_id if v.review_report else None,
            v.source_snapshot.commit_sha if v.source_snapshot else None)


FULL = ("job-402", "job-402", "d" * 40)


# ---------- bug 1: edit after changes requested ----------

def test_owner_edit_keeps_the_evidence_of_its_base():
    store, d = store_with_document()
    v2 = store.edit_owned(d, "73", 1, "# A edited\n", "changes requested")
    v3 = store.edit_owned(d, "73", 2, "# A edited again\n")          # replaces pending v2
    for v in (v2, v3):
        assert evidence_of(v) == FULL and v.evidence_from_version == 1
    assert store.version(d, 1).evidence_from_version is None          # the original is its own
    # deep copies: changing one version never changes another
    v3.evidence_report.confidence = 0.1
    assert store.version(d, 1).evidence_report.confidence == 0.8


def test_resubmitted_version_can_be_reviewed_through_the_api(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    store, d = store_with_document()
    monkeypatch.setattr("main.documents", store)
    r = client.put(f"/internal/documents/{d}/content", headers=HEADERS,
                   json={"expected_version": 1, "content": "# A edited\n", "note": "fixed"})
    assert r.status_code == 200 and r.json()["evidence_from_version"] == 1
    staff = client.get(f"/internal/documents/{d}/review-evidence?version=2", headers=HEADERS)
    manager = client.get(f"/internal/documents/{d}/evidence?version=2", headers=HEADERS)
    assert staff.status_code == 200 and staff.json()["source_snapshot"]["commit_sha"] == "d" * 40
    assert manager.status_code == 200 and manager.json()["job_id"] == "job-402"
    versions = client.get(f"/internal/documents/{d}", headers=HEADERS)
    assert versions.status_code == 200


# ---------- bug 2: rollback ----------

def test_rollback_keeps_all_evidence_of_the_restored_version(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    store, d = store_with_document()
    store.resolve_workflow_version(d, "73", 1, "APPROVED", "84")
    store.edit_owned(d, "73", 1, "# A v2\n")
    store.resolve_workflow_version(d, "73", 2, "APPROVED", "84")
    monkeypatch.setattr("main.documents", store)
    r = client.post(f"/internal/documents/{d}/rollback", headers=OWNER,
                    json={"source_version": 2, "note": "back to v2"})
    assert r.status_code == 201
    v3 = store.version(d, 3)
    assert v3.origin == VersionOrigin.rollback and evidence_of(v3) == FULL
    assert v3.evidence_from_version == 1                    # v2 itself carried v1's evidence
    assert client.get(f"/internal/documents/{d}/review-evidence?version=3", headers=HEADERS).status_code == 200
    assert client.get(f"/internal/documents/{d}/evidence?version=3", headers=HEADERS).status_code == 200


# ---------- restart ----------

def test_evidence_of_every_version_survives_a_restart(tmp_path):
    path = tmp_path / "documents.json"
    store, d = store_with_document(path)
    store.edit_owned(d, "73", 1, "# A edited\n")
    again = DocumentStore(str(path))                        # "restart" on the same file
    for n in (1, 2):
        assert evidence_of(again.version(d, n)) == FULL
    assert again.version(d, 2).evidence_from_version == 1


def test_versions_saved_before_the_fix_are_repaired_when_loaded(tmp_path):
    path = tmp_path / "documents.json"
    store, d = store_with_document(path)
    store.edit_owned(d, "73", 1, "# A edited\n")
    store.resolve_workflow_version(d, "73", 2, "APPROVED", "84")
    store.rollback_owned(d, "73", 2, "84")                   # v3: rollback to the approved v2
    raw = json.loads(path.read_text(encoding="utf-8"))
    for v in raw["versions"][d][1:]:                         # what the old code wrote
        v.update(evidence_report=None, review_report=None, source_snapshot=None)
        v.pop("evidence_from_version", None)
    path.write_text(json.dumps(raw), encoding="utf-8")

    restored = DocumentStore(str(path))
    for n in (2, 3):
        v = restored.version(d, n)
        assert evidence_of(v) == FULL and v.evidence_from_version == 1, n


def test_repair_follows_the_version_history():
    store, d = store_with_document()
    store.edit_owned(d, "73", 1, "# v2\n")
    store.edit_owned(d, "73", 2, "# v3\n")                   # v2 superseded by v3
    versions = store._versions[d]
    for v in versions[1:]:
        v.evidence_report = v.review_report = v.source_snapshot = None
        v.evidence_from_version = None
    assert repair_evidence(versions) == 2
    assert [v.evidence_from_version for v in versions] == [None, 1, 1]
    assert repair_evidence(versions) == 0                    # nothing left to repair


RESTART_SCRIPT = textwrap.dedent('''
    import json, sys
    from fastapi.testclient import TestClient
    from main import app
    c = TestClient(app)
    H = {"Authorization": "Bearer %s", "X-User-Id": "73"}
    if sys.argv[1] == "write":
        job = c.post("/generate", json={"scope": "file", "target": "a.py", "files": [{
            "path": "a.py", "language": "python", "status": "ok",
            "functions": [{"name": "f", "parameters": [], "source": "def f():\\n    return 1"}]}]}).json()
        doc = c.post("/internal/documents/from-job", headers=H, json={"job_id": job["id"]}).json()
        c.put("/internal/documents/%%s/content" %% doc["id"], headers=H,
              json={"expected_version": 1, "content": "# edited"})
        print(doc["id"])
    else:
        d = sys.argv[2]
        out = {"doc": c.get("/internal/documents/" + d, headers=H).status_code}
        for n in (1, 2):
            out["evidence_v%%d" %% n] = c.get("/internal/documents/%%s/evidence?version=%%d" %% (d, n), headers=H).status_code
            out["review_v%%d" %% n] = c.get("/internal/documents/%%s/review-evidence?version=%%d" %% (d, n), headers=H).status_code
        print(json.dumps(out))
''' % SECRET)


def test_documents_and_evidence_survive_a_real_restart(tmp_path):
    """Two separate processes configured with the same DOCUMENTS_FILE (the compose setup)."""
    env = {**os.environ, "DOCUMENTS_FILE": str(tmp_path / "documents.json"),
           "TEMPLATES_FILE": str(tmp_path / "templates.json"), "INTERNAL_API_SECRET": SECRET,
           "ANTHROPIC_API_KEY": "",
           "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")])}

    def run(*args):
        r = subprocess.run([sys.executable, "-c", RESTART_SCRIPT, *args], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip().splitlines()[-1]

    doc_id = run("write")
    after = json.loads(run("read", doc_id))
    assert after == {"doc": 200, "evidence_v1": 200, "review_v1": 200, "evidence_v2": 200, "review_v2": 200}
