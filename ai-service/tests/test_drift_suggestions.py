"""LD-354: drift resolution suggestions (POST /drift/reports/{id}/suggestions).

Cases DR-xx of Docs/Linh/FR10.md. A drift report is made for the drift fixture (shop/cart.py
before / after a Pull Request) against a saved document and the README, then turned into
suggestions.
"""
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline generator

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from drift_fixtures import AFTER, BEFORE, PATCH, PR, README  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)
README2 = {"path": "README.md", "content": README["content"] + "See shop/cart.py:30-40 for the Cart class.\n"}
FILES = [{"path": "shop/cart.py", "patch": PATCH, "before": BEFORE, "after": AFTER}]


def saved_document():
    r = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                       "output_language": "vi", "files": [BEFORE]})
    r = client.post("/documents", json={"job_id": r.json()["id"], "actor": "tester"})
    return r.json()


def report(doc_ids, docs=(README2,), files=FILES):
    r = client.post("/drift/analyze", json={"repository": "acme/shop", "pull_request": PR, "files": files,
                                            "docs": list(docs), "document_ids": doc_ids})
    assert r.status_code == 201, r.text
    return r.json()


def suggestions(report_id, **body):
    r = client.post(f"/drift/reports/{report_id}/suggestions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def setup():
    doc = saved_document()
    rep = report([doc["id"]])
    return doc, rep, suggestions(rep["id"], docs=[README2])


def kinds(rep):
    return {f["id"]: f["kind"] for f in rep["findings"]}


def for_finding(batch, rep, kind, path="shop/cart.py"):
    ids = {i for i, k in kinds(rep).items() if k == kind}
    return [s for s in batch["suggestions"] if ids & set(s["finding_ids"]) and s["target"]["path"] == path]


# ---------- DR-01 .. DR-02 ----------

def test_dr01_batch_from_report_covers_every_finding(setup):
    doc, rep, batch = setup
    assert batch["source"] == "drift" and batch["report_id"] == rep["id"]
    assert batch["pull_request"]["number"] == 42 and batch["warnings"] == []
    covered = {i for s in batch["suggestions"] for i in s["finding_ids"]}
    assert covered == {f["id"] for f in rep["findings"]}
    assert all(s["source"] == "drift" and s["status"] == "pending" for s in batch["suggestions"])
    listed = client.get("/suggestions", params={"batch_id": batch["id"]}).json()
    assert len(listed) == len(batch["suggestions"])
    assert client.post("/drift/reports/nope/suggestions", json={}).status_code == 404


def test_dr02_one_suggestion_per_passage_with_its_findings(setup):
    doc, rep, batch = setup
    keys = [(s["target"]["document_id"], s["target"]["path"], s["target"]["line_start"]) for s in batch["suggestions"]]
    assert len(keys) == len(set(keys))
    gone = for_finding(batch, rep, "endpoint_removed")[0]
    assert gone["operation"] == "delete" and gone["original"].startswith("### `DELETE /carts/{id}`")
    assert {kinds(rep)[i] for i in gone["finding_ids"]} == {"endpoint_removed", "entity_removed"}
    renamed = for_finding(batch, rep, "entity_renamed")[0]
    assert "### `count_cart_items`" in renamed["proposed"] and renamed["confidence"] == 0.9
    sig = for_finding(batch, rep, "parameter_removed")
    table = next(s for s in sig if "### `get_cart_total`" in s["original"])
    assert "| `discount`" not in table["proposed"] and "| `currency` | str |" in table["proposed"]
    assert table["evidence"] and table["evidence"][0].startswith("X")
    assert all(s["target"]["document_id"] == doc["id"] and s["target"]["version"] == 1
               for s in batch["suggestions"] if s["target"]["source"] == "document")


# ---------- DR-03: stale line references ----------

def test_dr03_line_references_get_their_new_range(setup):
    _, rep, batch = setup
    texts = {s["target"]["line_start"]: s for s in batch["suggestions"] if s["target"]["path"] == "shop/cart.py"}
    sig = next(s for s in texts.values() if "### `get_cart_total`" in s["original"])
    assert "`shop/cart.py:10-15`" in sig["proposed"]          # entity's new range (body changed)
    assert "`shop/cart.py:10-14` now points to `shop/cart.py:10-15`" in sig["reasons"]
    count = next(s for s in texts.values() if "### `count_items`" in s["original"])
    assert "`shop/cart.py:24-26`" in count["proposed"]        # moved by lines added above it
    unknown = [r for s in batch["suggestions"] for r in s["reasons"] if "30-40" in r]
    assert unknown and all("check the reference" in r for r in unknown)


# ---------- DR-04 .. DR-06 ----------

def test_dr04_repository_markdown_must_be_sent_again(setup):
    _, rep, _ = setup
    batch = suggestions(rep["id"])                            # README not sent
    assert any("README.md: the Markdown file is not in the request" in w for w in batch["warnings"])
    assert all(s["target"]["source"] == "document" for s in batch["suggestions"])
    assert any(w.startswith("No suggestion for finding(s)") for w in batch["warnings"])
    with_readme = suggestions(rep["id"], docs=[README2])
    s = next(s for s in with_readme["suggestions"] if s["target"]["path"] == "README.md")
    assert "`GET /api/carts/{id}`" in s["proposed"] and "clear_cart" not in s["proposed"]
    assert "See shop/cart.py:30-40" in s["proposed"]            # unknown new place: left alone


def test_dr05_undocumented_entity_gets_a_section(setup):
    _, rep, batch = setup
    s = for_finding(batch, rep, "undocumented_entity")[0]
    assert s["operation"] == "insert" and "\n### `apply_coupon`\n" in s["proposed"]


def test_dr06_behaviour_change_is_left_for_review_with_the_reports_advice(setup):
    _, rep, batch = setup
    s = for_finding(batch, rep, "implementation_changed")[0]
    assert s["operation"] == "review" and s["proposed"] is None
    finding = next(f for f in rep["findings"] if f["kind"] == "implementation_changed")
    assert finding["suggestion"] in s["reasons"]


# ---------- DR-07 .. DR-08 ----------

def test_dr07_moved_file_path_is_replaced():
    readme = {"path": "README.md", "content": "# Shop\n\nCart code: `shop/cart.py`.\n"}
    rep = report([], docs=[readme], files=[{"path": "shop/basket.py", "previous_path": "shop/cart.py",
                                            "status": "renamed", "before": BEFORE,
                                            "after": {**BEFORE, "path": "shop/basket.py"}}])
    assert "file_moved" in kinds(rep).values()
    s = suggestions(rep["id"], docs=[readme])["suggestions"][0]
    assert s["proposed"] == "# Shop\n\nCart code: `shop/basket.py`."


def test_dr08_report_without_findings():
    rep = report([], docs=[{"path": "docs/x.md", "content": "# X\n\nNothing here.\n"}])
    batch = suggestions(rep["id"])
    assert batch["suggestions"] == [] and "nothing to resolve" in batch["warnings"][0]
