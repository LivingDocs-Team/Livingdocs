"""LD-166 / LD-172: accept, edit or dismiss the AI suggestion of a drift finding (LD-161), and
keep drift analyses with their resolution history across restarts (LD-167)."""
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline reviewer

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.drift import DriftReportStore  # noqa: E402
from app.drift_models import ResolutionUpdate  # noqa: E402
from app.drift_review import DriftReviewer, ResolutionError, resolve  # noqa: E402
from drift_fixtures import AFTER, BEFORE, PATCH, PR, README  # noqa: E402
from test_drift_review import FakeModel, report_with  # noqa: E402


def reviewed():
    """Report whose findings carry an AI suggestion (fake model: `fix <id>`)."""
    return report_with(DriftReviewer(FakeModel()))


def suggestion_of(report):
    finding = next(f for f in report.findings if f.ai_review and f.ai_review.suggested_update)
    return finding.id, finding.ai_review.suggested_update


def test_accepting_the_ai_suggestion_records_it_in_the_resolution_and_history():
    r = reviewed()
    fid, suggested = suggestion_of(r)

    f = resolve(r, fid, ResolutionUpdate(status="resolved", actor="42", accepted_update=suggested))

    assert f.resolution.status == "resolved" and f.resolution.accepted_update == suggested
    assert f.resolution.history[-1].accepted_update == suggested
    assert r.review.resolved == 1


def test_an_edited_suggestion_is_stored_as_written_and_reopening_clears_it():
    r = reviewed()
    fid, suggested = suggestion_of(r)
    edited = suggested + "\n\nSee also the currency section."

    resolve(r, fid, ResolutionUpdate(status="resolved", accepted_update=f"  {edited}  "))
    f = resolve(r, fid, ResolutionUpdate(status="open", actor="42"))

    assert f.resolution.status == "open" and f.resolution.accepted_update is None
    assert [e.status for e in f.resolution.history] == ["resolved", "open"]
    assert f.resolution.history[0].accepted_update == edited     # history keeps what was accepted


def test_accepted_update_only_with_resolved_and_same_update_adds_no_history():
    r = reviewed()
    fid, suggested = suggestion_of(r)
    for status in ("acknowledged", "open"):
        with pytest.raises(ResolutionError) as e:
            resolve(r, fid, ResolutionUpdate(status=status, accepted_update="text"))
        assert e.value.status == 422
    with pytest.raises(ResolutionError):
        resolve(r, fid, ResolutionUpdate(status="dismissed", note="Not drift", accepted_update="x"))

    resolve(r, fid, ResolutionUpdate(status="resolved", accepted_update=suggested))
    f = resolve(r, fid, ResolutionUpdate(status="resolved", accepted_update=suggested))
    assert len(f.resolution.history) == 1


def test_reports_and_resolution_history_survive_a_restart(tmp_path):
    path = tmp_path / "drift_reports.json"
    store = DriftReportStore(path=str(path))
    first = store.add(reviewed())
    second = store.add(reviewed())
    fid, suggested = suggestion_of(first)
    store.resolve(first.id, fid, ResolutionUpdate(status="resolved", actor="42", accepted_update=suggested))

    reloaded = DriftReportStore(path=str(path))

    assert [row.id for row in reloaded.list()] == [second.id, first.id]   # newest first, as before
    f = next(x for x in reloaded.get(first.id).findings if x.id == fid)
    assert f.resolution.accepted_update == suggested
    assert [(e.status, e.actor) for e in f.resolution.history] == [("resolved", "42")]
    assert reloaded.list()[1].review.resolved == 1


def test_only_the_newest_reports_are_loaded_and_a_corrupt_file_is_moved_aside(tmp_path):
    path = tmp_path / "drift_reports.json"
    store = DriftReportStore(path=str(path))
    ids = [store.add(reviewed()).id for _ in range(3)]
    assert [row.id for row in DriftReportStore(limit=2, path=str(path)).list()] == ids[:0:-1]

    path.write_text("{not json", encoding="utf-8")
    assert DriftReportStore(path=str(path)).list() == []
    assert not path.exists() and list(tmp_path.glob("drift_reports.corrupt-*.json"))


def test_api_accepts_an_edited_suggestion_and_rejects_it_without_resolving():
    from main import app

    client = TestClient(app)
    body = {"repository": "acme/shop", "pull_request": PR, "docs": [README], "document_ids": [],
            "ai_review": False,
            "files": [{"path": "shop/cart.py", "patch": PATCH, "before": BEFORE, "after": AFTER}]}
    report = client.post("/drift/analyze", json=body).json()
    finding = report["findings"][0]
    url = f"/drift/reports/{report['id']}/findings/{finding['id']}/resolution"

    bad = client.put(url, json={"status": "acknowledged", "accepted_update": "x"})
    ok = client.put(url, json={"status": "resolved", "actor": "42", "accepted_update": "Edited text."})

    assert bad.status_code == 422
    assert ok.status_code == 200, ok.text
    assert ok.json()["resolution"]["accepted_update"] == "Edited text."
    assert ok.json()["resolution"]["history"][-1]["accepted_update"] == "Edited text."
