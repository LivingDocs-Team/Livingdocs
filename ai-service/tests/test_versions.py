"""Versioned documentation tests: LD-195."""
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline generator

from fastapi.testclient import TestClient  # noqa: E402

from app.jobs import JobOutput  # noqa: E402
from app.models import Scope  # noqa: E402
from app.versions import DocumentStore
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
