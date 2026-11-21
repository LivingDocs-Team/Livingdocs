"""LD-166 / LD-172: accept, edit or dismiss the AI suggestion of a drift finding (LD-161), and
keep drift analyses with their resolution history across restarts (LD-167)."""
import json
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


def test_imports_legacy_and_current_reports_once_across_restart(tmp_path):
    legacy_path = tmp_path / "drift_reports.json"
    current_path = tmp_path / "drift-reports.json"
    legacy = DriftReportStore(path=str(legacy_path))
    old = legacy.add(reviewed())
    fid, suggested = suggestion_of(old)
    legacy.resolve(old.id, fid, ResolutionUpdate(status="resolved", actor="42", accepted_update=suggested))
    legacy_bytes = legacy_path.read_bytes()
    current = DriftReportStore(path=str(tmp_path / "current.json"))
    new = current.add(reviewed())
    (tmp_path / "current.json").rename(current_path)

    upgraded = DriftReportStore(limit=1, path=str(current_path))
    assert [row.id for row in upgraded.list()] == [new.id, old.id]
    upgraded.resolve(old.id, fid, ResolutionUpdate(status="open", actor="42"))
    restarted = DriftReportStore(limit=1, path=str(current_path))
    finding = next(f for f in restarted.get(old.id).findings if f.id == fid)
    assert [event.status for event in finding.resolution.history] == ["resolved", "open"]
    assert legacy_path.read_bytes() == legacy_bytes


def test_failed_import_keeps_legacy_file_and_can_retry(tmp_path, monkeypatch):
    legacy_path = tmp_path / "drift_reports.json"
    current_path = tmp_path / "drift-reports.json"
    old = DriftReportStore(path=str(legacy_path)).add(reviewed())
    legacy_bytes = legacy_path.read_bytes()

    def unavailable(*args):
        raise OSError("simulated replacement failure")

    with monkeypatch.context() as patch:
        patch.setattr("app.drift.os.replace", unavailable)
        with pytest.raises(OSError, match="replacement failure"):
            DriftReportStore(path=str(current_path))
    assert legacy_path.read_bytes() == legacy_bytes
    assert not current_path.exists()
    assert DriftReportStore(path=str(current_path)).get(old.id) == old


def test_import_above_retention_limit_survives_next_write_and_restart(tmp_path):
    legacy_path = tmp_path / "drift_reports.json"
    current_path = tmp_path / "drift-reports.json"
    report = reviewed()
    rows = [report.model_copy(update={"id": f"legacy-{number}"}).model_dump(mode="json")
            for number in range(501)]
    legacy_path.write_text(json.dumps([*rows, rows[0]]), encoding="utf-8")
    store = DriftReportStore(path=str(current_path))
    finding_id, _ = suggestion_of(store.get("legacy-0"))
    store.resolve("legacy-0", finding_id, ResolutionUpdate(status="acknowledged", actor="42"))
    store.add(report)
    restored = DriftReportStore(path=str(current_path))
    assert len(restored.list()) == 502
    assert restored.get("legacy-0").review.acknowledged == 1
    assert restored.get(report.id) == report


@pytest.mark.parametrize("name", ["drift_reports.json", "drift-reports.json"])
def test_partial_import_file_is_preserved_for_recovery(tmp_path, name):
    legacy = tmp_path / "drift_reports.json"
    current = tmp_path / "drift-reports.json"
    report = reviewed().model_dump(mode="json")
    payload = json.dumps({"reports": [report]})
    legacy.write_text(payload, encoding="utf-8")
    current.write_text(payload, encoding="utf-8")
    (tmp_path / name).write_text(payload[:-2], encoding="utf-8")
    before = [path.read_bytes() for path in (legacy, current)]
    with pytest.raises(json.JSONDecodeError):
        DriftReportStore(path=str(current))
    assert [path.read_bytes() for path in (legacy, current)] == before


def test_conflicting_import_ids_leave_both_files_unchanged(tmp_path):
    legacy = tmp_path / "drift_reports.json"
    current = tmp_path / "drift-reports.json"
    report = reviewed().model_dump(mode="json")
    legacy.write_text(json.dumps([report]), encoding="utf-8")
    current.write_text(json.dumps({"reports": [report | {"repository": "different/repo"}]}), encoding="utf-8")
    before = [path.read_bytes() for path in (legacy, current)]
    with pytest.raises(ValueError, match="Conflicting persisted drift report"):
        DriftReportStore(path=str(current))
    assert [path.read_bytes() for path in (legacy, current)] == before


def test_failed_flush_rolls_back_existing_store_without_touching_legacy(tmp_path, monkeypatch):
    legacy = tmp_path / "drift_reports.json"
    current = tmp_path / "drift-reports.json"
    old = DriftReportStore(path=str(legacy)).add(reviewed())
    store = DriftReportStore(path=str(current))
    before = [path.read_bytes() for path in (legacy, current)]
    new = reviewed()

    def unavailable(_fd):
        raise OSError("simulated flush failure")

    with monkeypatch.context() as patch:
        patch.setattr("app.drift.os.fsync", unavailable)
        with pytest.raises(OSError, match="flush failure"):
            store.add(new)
    assert store.get(new.id) is None
    assert [path.read_bytes() for path in (legacy, current)] == before
    assert DriftReportStore(path=str(current)).get(old.id) == old
    assert not list(tmp_path.glob("*.tmp"))


def test_replays_manager_decision_after_failed_report_write_and_restart(tmp_path, monkeypatch):
    path = tmp_path / "reports.json"
    store = DriftReportStore(path=str(path))
    report = store.add(reviewed())
    fid, suggested = suggestion_of(report)
    finding = next(item for item in report.findings if item.id == fid)
    finding.document.document_id = "doc"
    submit = ResolutionUpdate(status="acknowledged", decision="accept", actor="developer")
    store.resolve(report.id, fid, submit, draft=lambda *_: 2)

    def unavailable(*args):
        raise OSError("simulated replacement failure")

    with monkeypatch.context() as patch:
        patch.setattr("app.drift.os.replace", unavailable)
        with pytest.raises(OSError, match="replacement failure"):
            store.apply_workflow_decision(report.id, fid, "doc", 2, "REJECTED", "manager", "Revise")
    store = DriftReportStore(path=str(path))
    for _ in range(2):
        store.apply_workflow_decision(report.id, fid, "doc", 2, "REJECTED", "manager", "Revise")
    with pytest.raises(ResolutionError) as error:
        store.resolve(report.id, fid, submit, draft=lambda *_: 99)
    assert error.value.status == 409

    retry = ResolutionUpdate(status="acknowledged", decision="edit", proposed=suggested + " revised", retry_of=2)
    first = store.resolve(report.id, fid, retry, draft=lambda *_: 3)
    assert store.resolve(report.id, fid, retry, draft=lambda *_: 3) == first
    store.apply_workflow_decision(report.id, fid, "doc", 2, "REJECTED", "manager", "Revise")
    for _ in range(2):
        store.apply_workflow_decision(report.id, fid, "doc", 3, "APPROVED", "manager", None)
    store = DriftReportStore(path=str(path))
    resolution = next(item.resolution for item in store.get(report.id).findings if item.id == fid)

    def no_new_draft(*args):
        pytest.fail("An approved submission retry must not create another draft")

    assert store.resolve(report.id, fid, retry, draft=no_new_draft).resolution == resolution
    assert resolution.status == "resolved"
    assert resolution.accepted_update == retry.proposed
    assert [(event.draft_version, event.workflow_decision) for event in resolution.history] == [
        (2, None), (2, "REJECTED"), (3, None), (3, "APPROVED"),
    ]


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
