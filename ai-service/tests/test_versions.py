"""Versioned documentation tests: LD-195, LD-128."""
import copy
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


# ---------- LD-128: update from a source change ----------

def cart_v2():
    f = copy.deepcopy(CART)
    f["functions"].append({"name": "apply_discount",
                           "parameters": [{"name": "code", "type": "str"}], "return_type": "float"})
    return f


def change(cid="c1", files=None):
    """LD-116 SourceChangeResponse, in the camelCase the Java service sends."""
    return {"id": cid, "trigger": "COMMIT", "commitSha": "abc123",
            "files": files or [{"path": "shop/cart.py", "change": "MODIFIED", "language": "python",
                                "entities": [{"kind": "function", "name": "apply_discount",
                                              "change": "ADDED", "startLine": 20, "endLine": 25}]}]}


def update(doc_id, source_change, files=(), **extra):
    return client.post(f"/documents/{doc_id}/updates",
                       json={"source_change": source_change, "files": list(files), **extra})


def test_modified_file_creates_proposal():
    doc = new_document()
    r = update(doc["id"], change(), [cart_v2()], actor="bot")
    assert r.status_code == 201, r.text
    p = r.json()["proposal"]
    assert p["number"] == 2 and p["status"] == "proposed" and p["origin"] == "source_change"
    assert p["base_version"] == 1
    assert p["source_changes"] == [{"id": "c1", "trigger": "COMMIT", "commit_sha": "abc123",
                                    "pull_request_number": None}]
    assert p["changes"] == [{"path": "shop/cart.py", "action": "updated", "previous_path": None,
                             "entities": ["function apply_discount (added)"]}]
    assert "apply_discount" in p["content"]
    # the unchanged file keeps exactly the same text
    v1 = client.get(f"/documents/{doc['id']}/versions/1").json()
    assert p["sections"][1] == v1["sections"][1]
    # the current version does not change until someone accepts
    d = client.get(f"/documents/{doc['id']}").json()
    assert d["current_version"] == 1 and d["pending_version"] == 2
    assert "apply_discount" not in client.get(f"/documents/{doc['id']}/content").text
    assert client.get(f"/documents/{doc['id']}/history").json()[-1]["action"] == "proposed"


def test_added_removed_and_renamed_files():
    doc = new_document()
    orders = {"path": "shop/orders.py", "language": "python", "status": "ok",
              "functions": [{"name": "place_order", "parameters": [], "return_type": "None"}]}
    files = [{"path": "shop/orders.py", "change": "ADDED"},
             {"path": "shop/users.py", "change": "REMOVED"},
             {"path": "shop/basket.py", "previousPath": "shop/cart.py", "change": "RENAMED"}]
    r = update(doc["id"], change("c2", files), [orders])
    assert r.status_code == 201, r.text
    p = r.json()["proposal"]
    actions = {c["path"]: (c["action"], c["previous_path"]) for c in p["changes"]}
    assert actions == {"shop/orders.py": ("added", None), "shop/users.py": ("removed", None),
                       "shop/basket.py": ("renamed", "shop/cart.py")}
    assert [s["path"] for s in p["sections"]] == ["shop/basket.py", "shop/orders.py"]
    basket = p["sections"][0]
    assert basket["status"] == "moved" and basket["markdown"].startswith("# shop/basket.py")
    assert any("renamed from shop/cart.py" in w for w in r.json()["warnings"])
    assert "UserService" not in p["content"] and "place_order" in p["content"]


def test_renamed_file_with_analysis_is_regenerated():
    doc = new_document()
    basket = {**cart_v2(), "path": "shop/basket.py"}
    files = [{"path": "shop/basket.py", "previous_path": "shop/cart.py", "change": "renamed"}]
    p = update(doc["id"], change("c3", files), [basket]).json()["proposal"]
    assert p["changes"][0]["action"] == "renamed"
    assert p["sections"][0]["path"] == "shop/basket.py" and p["sections"][0]["status"] == "offline"
    assert "apply_discount" in p["sections"][0]["markdown"]


def test_files_that_cannot_be_updated_keep_old_docs():
    doc = new_document()
    broken = {"path": "shop/users.py", "status": "invalid", "error": "SyntaxError line 3"}
    files = [{"path": "shop/cart.py", "change": "MODIFIED"},          # no analysis sent
             {"path": "shop/users.py", "change": "MODIFIED"},         # analysis failed
             {"path": "shop/data.bin", "change": "ADDED", "skippedReason": "not a source file"}]
    r = update(doc["id"], change("c4", files), [broken, {**CART, "path": "shop/other.py"}])
    assert r.status_code == 200
    body = r.json()
    assert body["proposal"] is None and "No documented file" in body["message"]
    w = " | ".join(body["warnings"])
    assert "shop/cart.py: no analysis provided" in w
    assert "shop/users.py: skipped (SyntaxError line 3); the previous documentation is kept" in w
    assert "shop/data.bin: not documented (not a source file)" in w
    assert "shop/other.py: analysis ignored" in w
    assert client.get(f"/documents/{doc['id']}").json()["versions_total"] == 1


def test_validation_errors():
    doc = new_document()
    assert update(doc["id"], {"id": "c", "files": []}).status_code == 422
    assert update(doc["id"], change(files=[{"path": "a.py", "change": "COPIED"}])).status_code == 422
    assert update(doc["id"], change(), [CART, CART]).status_code == 422
    assert update("nope", change(), [cart_v2()]).status_code == 404


def test_same_change_twice_and_second_change_extends_proposal():
    doc = new_document()
    first = update(doc["id"], change("c1"), [cart_v2()])
    again = update(doc["id"], change("c1"), [cart_v2()])
    assert again.status_code == 200 and again.json()["proposal"]["number"] == 2

    users2 = copy.deepcopy(USERS)
    users2["classes"][0]["methods"].append({"name": "delete_user", "parameters": []})
    r = update(doc["id"], change("c2", [{"path": "shop/users.py", "change": "MODIFIED"}]), [users2])
    assert r.status_code == 201
    p = r.json()["proposal"]
    assert p["number"] == 3 and [s["id"] for s in p["source_changes"]] == ["c1", "c2"]
    assert "apply_discount" in p["content"] and "delete_user" in p["content"]
    v2 = client.get(f"/documents/{doc['id']}/versions/2").json()
    assert first.json()["proposal"]["number"] == 2
    assert v2["status"] == "superseded" and v2["superseded_by"] == 3


def test_file_scope_document_stays_single_file():
    doc = new_document([CART], scope="file", target="shop/cart.py")
    p = update(doc["id"], change(), [cart_v2()]).json()["proposal"]
    assert p["content"].startswith("# shop/cart.py") and "\n---\n" not in p["content"]


def test_generation_error_keeps_previous_docs():
    from app.generator import DocGenerator

    class Broken(DocGenerator):
        def document_file(self, f, tpl, lang, retrieved=None):
            raise RuntimeError("boom")

    store = DocumentStore(None, generator=Broken())
    out = JobOutput(scope=Scope.repository, target="acme", template_id="default",
                    template_name="Standard technical docs", output_language="vi",
                    sections=[("shop/cart.py", "# shop/cart.py\n\nCũ.\n", "offline", None)])
    doc = store.create_from_job("j", out)
    from app.version_models import DocumentUpdateRequest
    req = DocumentUpdateRequest.model_validate({"source_change": change(), "files": [cart_v2()]})
    result, created = store.update(doc.id, req)
    assert not created and result.proposal is None
    assert "shop/cart.py: generation failed: boom" in result.warnings[0]


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
