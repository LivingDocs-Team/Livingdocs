"""LD-150 Test drift detection (LD-145): HTTP API of the AI service.

POST /drift/changes (LD-146), POST /drift/analyze (LD-147/148/149), GET /drift/reports[/{id}].
"""
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline generator

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from drift_fixtures import AFTER, BEFORE, PATCH, PR, README  # noqa: E402

client = TestClient(app)


def saved_document():
    r = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                       "output_language": "en", "files": [BEFORE]})
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "completed"
    r = client.post("/documents", json={"job_id": job_id, "actor": "tester"})
    assert r.status_code == 201, r.text
    return r.json()


def body(**extra):
    data = {"repository": "acme/shop", "pull_request": PR,
            "files": [{"path": "shop/cart.py", "patch": PATCH, "before": BEFORE, "after": AFTER}]}
    data.update(extra)
    return data


def test_changes_endpoint_lists_entity_changes():
    r = client.post("/drift/changes", json=body())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tickets"] == ["LD-146", "LD-147"]
    assert data["additions"] == 5 and data["deletions"] == 4
    changes = {c["name"]: c["change"] for c in data["files"][0]["entity_changes"]}
    assert changes["get_cart_total"] == "signature_changed"
    assert changes["clear_cart"] == "removed"
    assert changes["GET /api/carts/{id}"] == "renamed"


def test_analyze_saved_document_and_repository_markdown():
    doc = saved_document()
    r = client.post("/drift/analyze", json=body(docs=[README], document_ids=[doc["id"]]))
    assert r.status_code == 201, r.text
    report = r.json()
    assert report["status"] == "drift_detected"
    assert report["summary"]["highest_severity"] == "critical"
    assert report["summary"]["affected_documents"] == 2
    assert {(a["source"], a["path"]) for a in report["affected_documents"]} == {
        ("document", "shop/cart.py"), ("repository", "README.md")}

    sig = next(f for f in report["findings"]
               if f["entity"] == "get_cart_total" and f["document"]["document_id"] == doc["id"])
    assert sig["type"] == "signature" and sig["severity"] == "high"
    assert sig["confidence_level"] == "high"
    assert {e["kind"] for e in sig["evidence"]} == {"code_diff", "documentation", "commit", "ticket"}
    assert sig["document"]["version"] == 1

    # the report is kept and listed
    got = client.get(f"/drift/reports/{report['id']}")
    assert got.status_code == 200 and got.json()["findings"] == report["findings"]
    rows = client.get("/drift/reports", params={"repository": "acme/shop", "pull_request": 42}).json()
    assert rows[0]["id"] == report["id"] and rows[0]["summary"]["findings"] == len(report["findings"])
    assert client.get("/drift/reports", params={"repository": "x/y"}).json() == []


def test_analyze_without_drift():
    r = client.post("/drift/analyze", json=body(
        document_ids=[],
        docs=[{"path": "README.md", "content": "# Shop\n\nNothing about carts here.\n"}]))
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "no_drift" and data["findings"] == []
    assert data["summary"]["by_severity"] == {"low": 0, "medium": 0, "high": 0, "critical": 0}


def test_unknown_document_is_a_warning_not_an_error():
    r = client.post("/drift/analyze", json=body(document_ids=["nope"]))
    assert r.status_code == 201
    assert "Document 'nope' not found; it was not checked." in r.json()["warnings"]


def test_errors():
    assert client.get("/drift/reports/nope").status_code == 404
    assert client.post("/drift/analyze", json=body(files=[])).status_code == 422
    dup = [{"path": "a.py"}, {"path": "a.py"}]
    assert client.post("/drift/analyze", json=body(files=dup)).status_code == 422
    assert client.post("/drift/analyze", json=body(pull_request={"number": 0})).status_code == 422
    bad_status = [{"path": "a.py", "status": "exploded"}]
    assert client.post("/drift/changes", json=body(files=bad_status)).status_code == 422
    assert client.get("/drift/reports", params={"pull_request": 0}).status_code == 422
