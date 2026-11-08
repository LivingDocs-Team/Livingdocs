"""Versioned documentation tests: LD-195."""
import os
import pytest

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline generator

from fastapi.testclient import TestClient  # noqa: E402

from app.jobs import JobOutput  # noqa: E402
from app.models import Scope  # noqa: E402
from app.versions import DocumentStore, VersionError
from main import app  # noqa: E402

client = TestClient(app)

CART = {
    "path": "shop/cart.py", "language": "python", "status": "ok",
    "functions": [{"name": "get_cart_total", "parameters": [{"name": "cart_id", "type": "int"}],
                   "return_type": "float", "lineno": 10, "end_lineno": 13}],
}
USERS = {
    "path": "shop/users.py", "language": "python", "status": "ok",
    "classes": [{"name": "UserService", "docstring": "Manages users.",
                 "methods": [{"name": "get_user", "parameters": [{"name": "user_id", "type": "int"}],
                              "return_type": "User"}]}],
}


# ---------- LD-195: documents and version history ----------

def new_document(files=None, scope="repository", target="acme/shop"):
    files = files or [CART, USERS]
    r = client.post("/generate", json={"scope": scope, "target": target, "files": files})
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "completed"
    r = client.post("/documents", json={"job_id": job_id, "actor": "linh"})
    assert r.status_code == 201, r.text
    return r.json()


def test_save_job_as_version_1():
    doc = new_document()
    assert doc["current_version"] == 1 and doc["pending_version"] is None
    assert doc["target"] == "acme/shop" and doc["versions_total"] == 1

    v1 = client.get(f"/documents/{doc['id']}/versions/1").json()
    assert v1["status"] == "accepted" and v1["origin"] == "generated"
    assert [s["path"] for s in v1["sections"]] == ["shop/cart.py", "shop/users.py"]
    md = client.get(f"/documents/{doc['id']}/content").text
    assert md == v1["content"] and "get_cart_total" in md and "UserService" in md

    history = client.get(f"/documents/{doc['id']}/history").json()
    assert [(e["action"], e["version"], e["actor"]) for e in history] == [("created", 1, "linh")]
    assert doc["id"] in [d["id"] for d in client.get("/documents").json()]


def test_create_document_errors():
    assert client.post("/documents", json={"job_id": "nope"}).status_code == 404
    r = client.post("/generate", json={"scope": "file", "target": "x.py",
                                       "files": [{"path": "x.py", "status": "invalid", "error": "bad"}]})
    failed = r.json()["id"]
    assert client.get(f"/jobs/{failed}").json()["status"] == "failed"
    r = client.post("/documents", json={"job_id": failed})
    assert r.status_code == 409 and "failed" in r.json()["detail"]
    assert client.get("/documents/nope").status_code == 404
    doc = new_document()
    assert client.get(f"/documents/{doc['id']}/versions/9").status_code == 404
    assert client.get(f"/documents/{doc['id']}/content?version=9").status_code == 404


# ---------- persistence ----------

def test_documents_survive_restart(tmp_path):
    path = tmp_path / "documents.json"
    store = DocumentStore(str(path))
    out = JobOutput(scope=Scope.repository, target="acme", template_id="default",
                    template_name="Standard technical docs", output_language="en",
                    sections=[("a.py", "# a.py\n\nA.\n", "offline", 0.5)],
                    skipped=[("b.py", "bad")], confidence=0.5)
    doc = store.create_from_job("job1", out, actor="linh")

    again = DocumentStore(str(path))
    d = again.get(doc.id)
    assert d.current_version == 1 and d.target == "acme"
    v = again.version(doc.id)
    assert "# a.py" in v.content and [s.path for s in v.skipped] == ["b.py"]
    assert [e.action.value for e in again.history(doc.id)] == ["created"]

    path.write_text("{not json", encoding="utf-8")
    assert DocumentStore(str(path)).list() == []
    assert list(tmp_path.glob("documents.corrupt-*.json"))


def test_workflow_owner_is_persisted_and_legacy_actor_is_not_an_owner(tmp_path):
    path = tmp_path / "documents.json"
    store = DocumentStore(str(path))
    out = JobOutput(scope=Scope.repository, target="acme", template_id="default",
                    template_name="Standard technical docs", output_language="en",
                    sections=[("a.py", "# a.py\n", "offline", 0.5)])
    legacy = store.create_from_job("legacy-job", out, actor="untrusted-actor")
    owned = store.create_from_job("owned-job", out, actor="73", owner_user_id="73")

    restored = DocumentStore(str(path))
    assert restored.get(legacy.id).owner_user_id is None
    assert restored.get_owned(owned.id, "73").owner_user_id == "73"
    assert restored.version(owned.id, 1).created_by == "73"
    with pytest.raises(VersionError) as error:
        restored.get_owned(legacy.id, "73")
    assert error.value.status == 404
    with pytest.raises(VersionError) as error:
        restored.get_owned(owned.id, "74")
    assert error.value.status == 404


def test_owner_edit_adds_a_new_proposal_version_and_rejects_duplicate_pending_edit():
    store = DocumentStore()
    out = JobOutput(scope=Scope.file, target="a.py", template_id="default",
                    template_name="Standard technical docs", output_language="en",
                    sections=[("a.py", "# a.py\n", "offline", 0.5)])
    doc = store.create_from_job("job1", out, actor="73", owner_user_id="73")

    proposal = store.edit_owned(doc.id, "73", 1, "# Revised document", "Updated after staff feedback")

    assert proposal.number == 2
    assert proposal.status.value == "proposed"
    assert proposal.created_by == "73"
    assert store.get(doc.id).pending_version == 2
    assert store.history(doc.id)[-1].action.value == "proposed"
    with pytest.raises(VersionError) as error:
        store.edit_owned(doc.id, "73", 1, "# Another edit")
    assert error.value.status == 409


def test_internal_document_routes_require_the_service_credential(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")
    response = client.get("/internal/documents/missing", headers={
        "Authorization": "Bearer wrong-secret",
    })
    assert response.status_code == 401


def test_internal_document_creation_uses_trusted_owner_not_request_fields(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")
    job_response = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                                   "files": [CART, USERS]})
    assert job_response.status_code == 202
    job_id = job_response.json()["id"]

    response = client.post("/internal/documents/from-job", headers={
        "Authorization": "Bearer workflow-internal-secret", "X-User-Id": "73",
    }, json={"job_id": job_id, "actor": "999", "owner_user_id": "999", "user_id": "999"})

    assert response.status_code == 201, response.text
    assert response.json()["owner_user_id"] == "73"
    assert response.json()["id"]
    assert response.json()["current_version"] == 0
    assert response.json()["pending_version"] == 1
    assert client.get(f"/documents/{response.json()['id']}").status_code == 404
    assert response.json()["id"] not in [doc["id"] for doc in client.get("/documents").json()]


def test_internal_document_edit_checks_owner_and_adds_version(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")
    job_response = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                                   "files": [CART, USERS]})
    job_id = job_response.json()["id"]
    created = client.post("/internal/documents/from-job", headers={
        "Authorization": "Bearer workflow-internal-secret", "X-User-Id": "73",
    }, json={"job_id": job_id}).json()
    path = f"/internal/documents/{created['id']}/content"

    denied = client.put(path, headers={
        "Authorization": "Bearer workflow-internal-secret", "X-User-Id": "74",
    }, json={"content": "Not the owner"})
    assert denied.status_code == 404

    edited = client.put(path, headers={
        "Authorization": "Bearer workflow-internal-secret", "X-User-Id": "73",
    }, json={"content": "# Updated by owner", "expected_version": 1})
    assert edited.status_code == 200, edited.text
    assert edited.json()["number"] == 2
    assert edited.json()["status"] == "proposed"
    assert client.get(f"/internal/documents/{created['id']}", headers={
        "Authorization": "Bearer workflow-internal-secret",
        "X-User-Id": "73",
    }).json()["owner_user_id"] == "73"

    forged_owner_edit = client.put(path, headers={
        "Authorization": "Bearer workflow-internal-secret", "X-User-Id": "73",
    }, json={"content": "# Still the same owner", "expected_version": 2,
            "owner_user_id": "74", "actor": "999"})
    assert forged_owner_edit.status_code == 200, forged_owner_edit.text
    assert client.get(f"/internal/documents/{created['id']}", headers={
        "Authorization": "Bearer workflow-internal-secret",
        "X-User-Id": "73",
    }).json()["owner_user_id"] == "73"


def test_document_versions_support_repeated_changes_and_final_decision():
    store = DocumentStore()
    out = JobOutput(scope=Scope.file, target="a.py", template_id="default",
                    template_name="Standard technical docs", output_language="en",
                    sections=[("a.py", "# a.py\n", "offline", 0.5)])
    doc = store.create_from_job("job1", out, actor="73", owner_user_id="73")
    first = store.edit_owned(doc.id, "73", 1, "# First proposal")
    second = store.edit_owned(doc.id, "73", first.number, "# Revised proposal")
    assert first.status.value == "superseded"
    assert second.status.value == "proposed"

    store.resolve_workflow_version(doc.id, "73", second.number, "APPROVED", "84", "Looks good")
    persisted = store.get(doc.id)
    assert persisted.current_version == second.number
    assert persisted.pending_version is None
    assert store.version(doc.id).status.value == "accepted"
    assert store.history(doc.id)[-1].actor == "84"
