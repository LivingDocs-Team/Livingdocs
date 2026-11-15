"""LD-357: review and apply documentation suggestions.

POST /suggestions/{id}/review, POST /suggestions/apply. Cases RV-xx of Docs/Linh/FR10.md.
"""
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline generator

from fastapi.testclient import TestClient  # noqa: E402

from app.versions import documents  # noqa: E402
from drift_fixtures import AFTER, BEFORE, PATCH, PR, README  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def saved_document():
    r = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                       "output_language": "vi", "files": [BEFORE]})
    r = client.post("/documents", json={"job_id": r.json()["id"], "actor": "tester"})
    return r.json()


def batch_for(doc_id, docs=(README,)):
    r = client.post("/suggestions/updates", json={
        "repository": "acme/shop", "pull_request": PR, "docs": list(docs), "document_ids": [doc_id],
        "files": [{"path": "shop/cart.py", "patch": PATCH, "before": BEFORE, "after": AFTER}]})
    assert r.status_code == 201, r.text
    return r.json()


def about(batch, text, path="shop/cart.py"):
    return next(s for s in batch["suggestions"] if text in s["original"] and s["target"]["path"] == path)


def review(sid, **body):
    return client.post(f"/suggestions/{sid}/review", json=body)


def apply(**body):
    r = client.post("/suggestions/apply", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def accept_all(batch):
    for s in batch["suggestions"]:
        if s["proposed"] is not None:
            assert review(s["id"], decision="accept", reviewer="lan").status_code == 200


def content(doc_id, version=None):
    v = version or client.get(f"/documents/{doc_id}").json()["current_version"]
    return client.get(f"/documents/{doc_id}/versions/{v}").json()["content"]


# ---------- RV-01 .. RV-02: review ----------

def test_rv01_accept_and_reject_are_recorded():
    doc = saved_document()
    b = batch_for(doc["id"])
    sig, gone = about(b, "### `get_cart_total`"), about(b, "### `clear_cart`")
    r = review(sig["id"], decision="accept", reviewer="lan", comment="ok")
    assert r.status_code == 200
    got = r.json()
    assert got["status"] == "accepted" and got["review"]["reviewer"] == "lan"
    assert got["review"]["comment"] == "ok" and got["review"]["edited"] is False
    assert review(gone["id"], decision="reject", comment="keep it").json()["status"] == "rejected"
    assert client.get(f"/suggestions/{gone['id']}").json()["review"]["decision"] == "reject"
    assert {s["id"] for s in client.get("/suggestions", params={"batch_id": b["id"], "status": "accepted"}).json()} \
        == {sig["id"]}
    assert review(sig["id"], decision="maybe").status_code == 422
    assert review("nope", decision="accept").status_code == 404


def test_rv02_reviewer_can_edit_and_review_items_need_text():
    doc = saved_document()
    b = batch_for(doc["id"])
    sig = about(b, "### `get_cart_total`")
    edited = sig["proposed"].replace("Total of a cart.", "Total of a cart in the given currency.")
    got = review(sig["id"], decision="accept", proposed=edited).json()
    assert got["proposed"] == edited and got["review"]["edited"] is True
    assert "+Total of a cart in the given currency." in got["diff"]
    todo = next(s for s in b["suggestions"] if s["operation"] == "review")
    assert review(todo["id"], decision="accept").status_code == 422
    got = review(todo["id"], decision="accept", proposed=todo["original"] + "\n\nNow inserts at the front.").json()
    assert got["status"] == "accepted" and got["operation"] == "replace"


# ---------- RV-03 .. RV-05: apply to a saved document ----------

def test_rv03_apply_creates_one_new_version_and_keeps_history():
    doc = saved_document()
    before = content(doc["id"], 1)
    b = batch_for(doc["id"])
    accept_all(b)
    res = apply(batch_id=b["id"], actor="lan")
    assert res["conflicts"] == [] and res["skipped"] == []
    [d] = res["documents"]
    assert d["document_id"] == doc["id"] and d["version"] == 2 and d["status"] == "accepted"
    on_doc = [s for s in b["suggestions"] if s["proposed"] is not None and s["target"]["source"] == "document"]
    assert d["sections"] == ["shop/cart.py"] and len(d["suggestions"]) == len(on_doc)
    assert [f["path"] for f in res["files"]] == ["README.md"]
    info = client.get(f"/documents/{doc['id']}").json()
    assert info["current_version"] == 2 and info["versions_total"] == 2
    text = content(doc["id"])
    assert "get_cart_total(cart_id, currency)" in text and "### `clear_cart`" not in text
    assert "### `count_cart_items`" in text and "### `apply_coupon`" in text
    assert "| `code` | str | - | - |\n\n## API Endpoints" in text   # blank line kept before next heading
    assert content(doc["id"], 1) == before                          # old version untouched
    v2 = client.get(f"/documents/{doc['id']}/versions/2").json()
    assert v2["origin"] == "edit" and v2["base_version"] == 1 and v2["created_by"] == "lan"
    assert v2["changes"] == [{"path": "shop/cart.py", "action": "edited", "previous_path": None, "entities": []}]
    sec = next(s for s in v2["sections"] if s["path"] == "shop/cart.py")["markdown"]
    assert sec in text                                               # sections still match the text
    assert "\n\n\n" not in sec                                        # deleted sections leave no gap
    events = client.get(f"/documents/{doc['id']}/history").json()
    assert events[-1]["action"] == "accepted" and events[-1]["version"] == 2 and events[-1]["actor"] == "lan"
    assert all(client.get(f"/suggestions/{i}").json()["status"] == "applied" and
               client.get(f"/suggestions/{i}").json()["applied_version"] == 2 for i in d["suggestions"])


def test_rv04_only_accepted_suggestions_are_applied():
    doc = saved_document()
    b = batch_for(doc["id"])
    sig, gone = about(b, "### `get_cart_total`"), about(b, "### `clear_cart`")
    review(sig["id"], decision="accept")
    review(gone["id"], decision="reject")
    res = apply(ids=[sig["id"], gone["id"], "nope"], actor="lan")
    assert [d["suggestions"] for d in res["documents"]] == [[sig["id"]]]
    reasons = {p["id"]: p["reason"] for p in res["skipped"]}
    assert reasons == {gone["id"]: "status is rejected, not accepted", "nope": "not found"}
    text = content(doc["id"])
    assert "get_cart_total(cart_id, currency)" in text and "### `clear_cart`" in text
    again = apply(ids=[sig["id"]])
    assert again["documents"] == [] and again["skipped"][0]["reason"] == "status is applied, not accepted"
    assert review(sig["id"], decision="reject").status_code == 409


def test_rv05_conflict_leaves_the_document_unchanged():
    doc = saved_document()
    first, second = batch_for(doc["id"]), batch_for(doc["id"])
    s1 = about(first, "### `get_cart_total`")
    review(s1["id"], decision="accept")
    apply(ids=[s1["id"]])                                     # version 2 changes that passage
    s2, other = about(second, "### `get_cart_total`"), about(second, "### `count_items`")
    review(s2["id"], decision="accept")
    review(other["id"], decision="accept")
    res = apply(ids=[s2["id"], other["id"]])
    assert res["documents"] == []
    assert res["conflicts"] == [{"id": s2["id"], "reason": "the passage is no longer in the documentation "
                                                         "(it changed after the suggestion was made)"}]
    assert res["skipped"][0]["id"] == other["id"] and "same document has a conflict" in res["skipped"][0]["reason"]
    assert client.get(f"/documents/{doc['id']}").json()["current_version"] == 2
    got = client.get(f"/suggestions/{s2['id']}").json()
    assert got["status"] == "conflict" and got["conflict"].startswith("the passage is no longer")
    assert client.get(f"/suggestions/{other['id']}").json()["status"] == "accepted"
    assert apply(ids=[other["id"]])["documents"][0]["version"] == 3   # still applies on its own


# ---------- RV-06 .. RV-08 ----------

def test_rv06_owned_document_gets_a_proposal_for_review():
    doc = saved_document()
    d = documents.get(doc["id"])
    d.owner_user_id = "7"                                     # document under the review workflow
    b = batch_for(doc["id"], docs=[])
    s = about(b, "### `get_cart_total`")
    review(s["id"], decision="accept")
    [res] = apply(ids=[s["id"]], actor="lan")["documents"]
    assert res["status"] == "proposed" and res["version"] == 2
    assert d.current_version == 1 and d.pending_version == 2
    t = about(b, "### `count_items`")
    review(t["id"], decision="accept")
    [res] = apply(ids=[t["id"]], actor="lan")["documents"]    # built on the pending proposal
    assert res["version"] == 3 and d.pending_version == 3
    v2, v3 = documents.version(d.id, 2), documents.version(d.id, 3)
    assert v2.status.value == "superseded" and v2.superseded_by == 3
    assert "get_cart_total(cart_id, currency)" in v3.content and "count_cart_items" in v3.content


def test_rv07_repository_markdown_returns_new_text_and_diff():
    doc = saved_document()
    b = batch_for(doc["id"])
    s = about(b, "# Shop", "README.md")
    review(s["id"], decision="accept")
    [f] = apply(ids=[s["id"]])["files"]
    assert f["path"] == "README.md" and f["batch_id"] == b["id"] and f["suggestions"] == [s["id"]]
    assert f["content"] == "# Shop\n\nRead a total with `GET /api/carts/{id}`.\nWe add items to a cart.\n"
    assert "-Implementation: [cart](shop/cart.py), see `clear_cart()`." in f["diff"]


def test_rv08_apply_needs_ids_or_batch():
    assert client.post("/suggestions/apply", json={}).status_code == 422
    assert client.post("/suggestions/apply", json={"batch_id": "nope"}).status_code == 404
