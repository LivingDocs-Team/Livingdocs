"""LD-150: drift detection (LD-145) on real analyzer output (LD-328), through the public HTTP API.

Flow, as the pipeline runs it:
    analyzer output -> POST /generate -> POST /documents (version 1)
    Pull Request (analyzer output of the file at base and head) -> POST /drift/analyze
    -> findings with evidence -> GET /drift/reports[/{id}]

The Pull Request changes `shop/cart_service.py`:
    CartService.add_item   parameter `quantity` renamed to `qty`     -> Signature
    CartService.total      renamed to `grand_total`                  -> Referential
    CartService            docstring: prices in USD, without VAT     -> Semantic
The generator runs offline; no network is used.
"""
import copy

import pytest
from fastapi.testclient import TestClient

from conftest import DRIFT_FILE as CART
from conftest import DRIFT_PR as PR
from conftest import cart_head_version as head_version
from main import app

client = TestClient(app)


@pytest.fixture
def saved_document(analysis):
    job = client.post("/generate", json=analysis).json()
    assert client.get(f"/jobs/{job['id']}").json()["status"] == "completed"
    r = client.post("/documents", json={"job_id": job["id"], "actor": "ci"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def pr_body(analysis, shop_readme, saved_document):
    before = next(f for f in analysis["files"] if f["path"] == CART)
    return {"repository": "acme/shop", "pull_request": PR,
            "files": [{"path": CART, "before": before, "after": head_version(before)}],
            "docs": [shop_readme], "document_ids": [saved_document["id"]]}


def by_entity(report):
    return {(f["entity"], f["document"]["source"]): f for f in report["findings"]}


def test_changes_are_read_from_analyzer_output(pr_body):
    r = client.post("/drift/changes", json=pr_body)
    assert r.status_code == 200, r.text
    f = r.json()["files"][0]
    assert f["method"] == "analysis" and f["warnings"] == []
    changes = {c["name"]: c for c in f["entity_changes"]}
    assert set(changes) == {"CartService.add_item", "CartService.grand_total", "CartService"}
    assert changes["CartService.add_item"]["change"] == "signature_changed"
    assert changes["CartService.add_item"]["removed_parameters"] == ["quantity"]
    assert changes["CartService.grand_total"]["old_name"] == "CartService.total"
    assert changes["CartService"]["change"] == "behavior_changed"
    assert r.json()["tickets"] == ["LD-146", "LD-147"]


def test_drift_found_in_generated_document_and_readme(pr_body, saved_document):
    r = client.post("/drift/analyze", json=pr_body)
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["status"] == "drift_detected" and rep["warnings"] == []
    assert rep["summary"]["by_type"] == {"referential": 1, "signature": 1, "semantic": 2}
    assert rep["summary"]["highest_severity"] == "high"
    assert {(a["source"], a["path"]) for a in rep["affected_documents"]} == {
        ("document", CART), ("repository", "README.md")}

    f = by_entity(rep)
    sig = f[("CartService.add_item", "document")]
    assert sig["type"] == "signature" and sig["severity"] == "high"   # the doc still names `quantity`
    assert sig["kind"] == "parameter_renamed" and sig["breaking"] is True   # LD-153: same position, type
    assert sig["confidence_level"] == "high" and sig["after"].startswith("add_item(")
    assert sig["document"]["document_id"] == saved_document["id"] and sig["document"]["version"] == 1

    ren = f[("CartService.grand_total", "document")]
    assert ren["type"] == "referential" and ren["severity"] == "high"
    assert ren["kind"] == "entity_renamed"
    assert (ren["before"], ren["after"]) == ("CartService.total", "CartService.grand_total")

    sem = f[("CartService", "repository")]
    assert sem["type"] == "semantic" and sem["document"]["path"] == "README.md"
    assert sem["kind"] == "docstring_changed"
    # LD-154: the generated section copied the old docstring; it is quoted as evidence
    own = f[("CartService", "document")]
    quoted = [m for m in own["document"]["matches"] if m["kind"] == "docstring"]
    assert quoted and quoted[0]["term"] == "Prices are in VND and include VAT."
    assert own["severity"] == "high" and own["confidence"] > sem["confidence"]
    assert sem["confidence"] < f[("CartService", "document")]["confidence"]   # not its own section


def test_every_finding_has_checkable_evidence(pr_body):
    rep = client.post("/drift/analyze", json=pr_body).json()
    content = client.get(f"/documents/{pr_body['document_ids'][0]}/content").text.splitlines()
    for f in rep["findings"]:
        kinds = [e["kind"] for e in f["evidence"]]
        assert kinds[0] == "code_diff" and {"documentation", "commit", "ticket"} <= set(kinds)
        for e in f["evidence"]:
            if e["kind"] == "documentation" and e["document_id"]:
                # the line points into the saved section; its text is in the saved document
                assert e["excerpt"] in (line.strip() for line in content)
        commit = next(e for e in f["evidence"] if e["kind"] == "commit")
        assert commit["commit_sha"] == "abc1234" and commit["url"] == PR["url"]

    service = by_entity(rep)[("CartService", "document")]
    code = service["evidence"][0]["excerpt"]
    assert "Prices are in VND and include VAT." in code and "Prices are in USD, without VAT." in code


def test_unchanged_pull_request_has_no_drift(analysis, shop_readme, saved_document):
    before = next(f for f in analysis["files"] if f["path"] == CART)
    body = {"repository": "acme/shop", "pull_request": PR,
            "files": [{"path": CART, "before": before, "after": copy.deepcopy(before)}],
            "docs": [shop_readme], "document_ids": [saved_document["id"]]}
    rep = client.post("/drift/analyze", json=body).json()
    assert rep["status"] == "no_drift" and rep["findings"] == [] and rep["affected_documents"] == []


def test_report_is_kept_and_listed(pr_body):
    rep = client.post("/drift/analyze", json=pr_body).json()
    assert client.get(f"/drift/reports/{rep['id']}").json()["findings"] == rep["findings"]
    rows = client.get("/drift/reports", params={"repository": "acme/shop", "pull_request": 7}).json()
    assert rows[0]["id"] == rep["id"] and rows[0]["head_sha"] == "abc1234"
