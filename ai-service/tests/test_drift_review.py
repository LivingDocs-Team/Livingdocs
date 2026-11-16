"""LD-346 AI-based documentation drift analysis: AI review, explanations and resolution.

The AI is a fake model driven by the prompt (no network). It never changes the rule-based type or
severity; its verdicts must be grounded in the finding's own evidence ids.
"""
import json
import os
import re

os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402

from app import drift_review  # noqa: E402
from app.drift import DriftReportStore, analyze  # noqa: E402
from app.drift_markdown import render  # noqa: E402
from app.drift_models import (AIVerdict, ChangedFile, DriftAnalyzeRequest,  # noqa: E402
                              ResolutionStatus, ResolutionUpdate, ReviewStatus)
from app.drift_review import (DriftReviewer, ResolutionError, build_prompt,  # noqa: E402
                              get_reviewer, parse_reviews, resolve)
from app.versions import DocumentStore  # noqa: E402
from drift_fixtures import AFTER, BEFORE, PATCH, PR, README  # noqa: E402


class FakeModel:
    """Answers from the prompt: one review per finding id; can fail or answer badly first."""

    def __init__(self, answer=None, fail_first=0, garbage_first=0):
        self.answer = answer or (lambda fid, ids: {"id": fid, "verdict": "confirmed",
                                                   "explanation": f"Outdated passage [{ids[-1]}].",
                                                   "evidence": ids[:1], "suggested_update": f"fix {fid}"})
        self.fail_first, self.garbage_first = fail_first, garbage_first
        self.calls, self.prompts = 0, []

    def complete(self, system, messages):
        self.calls += 1
        self.prompts.append(messages)
        if self.calls <= self.fail_first:
            raise TimeoutError("simulated API timeout")
        if self.calls <= self.fail_first + self.garbage_first:
            return "Sorry, here is my review in prose."
        prompt = messages[0]["content"]
        reviews = []
        for block in re.split(r"\n(?=- F\d+ )", prompt):
            m = re.match(r"- (F\d+) ", block)
            if m:
                ids = re.findall(r"^  ([XDCT]\d+) ", block, re.M)
                reviews.append(self.answer(m.group(1), ids))
        return "```json\n" + json.dumps({"reviews": reviews}) + "\n```"


def report_with(reviewer=None, ai_review=True, docs=(README,)):
    req = DriftAnalyzeRequest(repository="acme/shop", pull_request=PR, docs=list(docs), document_ids=[],
                              files=[ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER)],
                              ai_review=ai_review)
    return analyze(req, DocumentStore(None), reviewer=reviewer)


# ---------- AI review ----------

def test_ai_confirms_with_grounded_explanations_and_does_not_change_severity():
    offline = report_with(DriftReviewer(None))
    model = FakeModel()
    r = report_with(DriftReviewer(model, model="fake"))
    assert model.calls == 1 and "Findings:" in model.prompts[0][0]["content"]
    assert [(f.id, f.type, f.kind, f.severity) for f in r.findings] == \
        [(f.id, f.type, f.kind, f.severity) for f in offline.findings]
    for f in r.findings:
        a = f.ai_review
        assert (a.mode, a.verdict, a.model) == ("ai", AIVerdict.confirmed, "fake")
        assert set(a.evidence) <= {e.id for e in f.evidence} and a.evidence
        assert a.suggested_update == f"fix {f.id}"
    assert (r.review.ai_mode, r.review.ai_confirmed) == ("ai", len(r.findings))
    assert r.review.status == ReviewStatus.pending and r.review.open == len(r.findings)


def test_unknown_citations_are_dropped_and_ungrounded_answers_are_not_trusted():
    def answer(fid, ids):
        if fid == "F1":
            return {"id": fid, "verdict": "confirmed", "explanation": "Old path [D1] and [Z9].",
                    "evidence": ["Z9"], "suggested_update": "new text"}
        return {"id": fid, "verdict": "disputed", "explanation": "Looks fine.", "evidence": [],
                "suggested_update": "x"}
    r = report_with(DriftReviewer(FakeModel(answer)))
    f1, f2 = r.findings[0], r.findings[1]
    assert f1.ai_review.verdict == AIVerdict.confirmed and f1.ai_review.evidence == ["D1"]
    assert f1.ai_review.explanation == "Old path [D1] and."
    assert "F1: AI cited unknown evidence Z9; ignored." in r.warnings
    assert f2.ai_review.verdict == AIVerdict.uncertain            # no citation: not trusted
    assert f2.ai_review.suggested_update != "x"


def test_disputed_findings_keep_their_severity_and_get_no_suggestion():
    r = report_with(DriftReviewer(FakeModel(lambda fid, ids: {
        "id": fid, "verdict": "disputed", "explanation": f"[{ids[0]}] already matches.",
        "evidence": ids[:1], "suggested_update": "ignored"})))
    assert all(f.ai_review.verdict == AIVerdict.disputed and f.ai_review.suggested_update is None
               for f in r.findings)
    assert r.review.ai_disputed == len(r.findings) and r.summary.highest_severity.value == "critical"


def test_invalid_answer_is_repaired_and_failures_fall_back_to_offline():
    model = FakeModel(garbage_first=1)
    r = report_with(DriftReviewer(model, max_attempts=2))
    assert model.calls == 2 and "not valid" in model.prompts[1][-1]["content"]
    assert all(f.ai_review.mode == "ai" for f in r.findings)

    down = FakeModel(fail_first=5)
    r = report_with(DriftReviewer(down, max_attempts=2))
    assert down.calls == 2
    assert all(f.ai_review.mode == "offline" and f.ai_review.explanation for f in r.findings)
    assert "AI review unavailable; explanations were built from the rules and evidence." in r.warnings


def test_offline_explanation_cites_evidence_and_suggests_replacement():
    r = report_with(ai_review=False)
    moved = next(f for f in r.findings if f.kind == "endpoint_moved")
    a = moved.ai_review
    assert (a.mode, a.verdict) == ("offline", AIVerdict.not_reviewed)
    assert "[X1]" in a.explanation and "[D1]" in a.explanation and "critical" in a.explanation
    assert a.evidence == ["X1", "D1"]
    assert r.review.ai_mode == "offline"


def test_only_the_most_severe_findings_are_sent(monkeypatch):
    monkeypatch.setattr(drift_review, "MAX_REVIEWED", 1)
    model = FakeModel()
    r = report_with(DriftReviewer(model))
    assert model.prompts[0][0]["content"].count("\n- F") == 1
    assert r.findings[0].ai_review.mode == "ai" and r.findings[1].ai_review.mode == "offline"
    assert "Only the 1 most severe findings were reviewed by the AI." in r.warnings


def test_parse_reviews_rejects_unreadable_answers():
    r = report_with(ai_review=False)
    for bad in ("not json", "[]", '{"reviews": [{"id": "F99"}]}'):
        with pytest.raises(drift_review.InvalidReview):
            parse_reviews(bad, r.findings)
    prompt = build_prompt(r, r.findings[:1])
    assert "F1 [referential / endpoint" in prompt and "  X1 code diff shop/cart.py" in prompt


def test_reviewer_mode_follows_the_api_key(monkeypatch):
    assert get_reviewer().mode == "offline"

    class Client:
        model = "claude-test"

        def complete(self, system, messages):
            return "{}"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(drift_review, "AnthropicClient", Client)
    reviewer = get_reviewer()
    assert (reviewer.mode, reviewer.model) == ("ai", "claude-test")


# ---------- resolution ----------

def test_resolution_workflow_and_history():
    r = report_with(ai_review=False)
    f1, f2 = r.findings[0].id, r.findings[1].id
    resolve(r, f1, ResolutionUpdate(status="acknowledged", actor="an"))
    assert r.review.status == ReviewStatus.in_progress and r.review.acknowledged == 1
    resolve(r, f1, ResolutionUpdate(status="acknowledged", actor="an"))    # same: no new entry
    resolve(r, f1, ResolutionUpdate(status="resolved", actor="an", note="Fixed in #43"))
    finding = r.findings[0]
    assert [h.status for h in finding.resolution.history] == [ResolutionStatus.acknowledged,
                                                              ResolutionStatus.resolved]
    assert (finding.resolution.actor, finding.resolution.note) == ("an", "Fixed in #43")
    with pytest.raises(ResolutionError) as e:
        resolve(r, f2, ResolutionUpdate(status="dismissed", note="  "))
    assert e.value.status == 422
    with pytest.raises(ResolutionError) as e:
        resolve(r, "F999", ResolutionUpdate(status="resolved"))
    assert e.value.status == 404
    for f in r.findings[1:]:
        resolve(r, f.id, ResolutionUpdate(status="dismissed", note="Archived v1 page."))
    assert r.review.status == ReviewStatus.completed
    assert (r.review.open, r.review.resolved, r.review.dismissed) == (0, 1, len(r.findings) - 1)
    resolve(r, f1, ResolutionUpdate(status="open", actor="an"))
    assert r.review.status == ReviewStatus.in_progress


def test_store_resolve_and_list():
    store = DriftReportStore()
    r = store.add(report_with(ai_review=False))
    assert store.resolve("nope", "F1", ResolutionUpdate(status="resolved")) is None
    store.resolve(r.id, "F1", ResolutionUpdate(status="resolved"))
    [row] = store.list()
    assert row.review.resolved == 1 and row.review.status == ReviewStatus.in_progress


def test_markdown_shows_ai_review_and_resolution():
    r = report_with(DriftReviewer(FakeModel()))
    resolve(r, "F1", ResolutionUpdate(status="resolved", actor="an", note="Fixed in #43"))
    md = render(r)
    assert "**Review:** in progress" in md and "AI: " in md
    assert "- **AI review:** ✅ confirmed — Outdated passage" in md
    assert "- **Suggested update:**" in md and "fix F1" in md
    assert "- **Resolution:** resolved by an — Fixed in #43" in md


def test_api_resolution_endpoint_and_ai_flag():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    body = {"repository": "acme/shop", "pull_request": PR, "docs": [README], "document_ids": [],
            "ai_review": False,
            "files": [{"path": "shop/cart.py", "patch": PATCH, "before": BEFORE, "after": AFTER}]}
    report = client.post("/drift/analyze", json=body).json()
    f1 = report["findings"][0]
    assert f1["ai_review"]["mode"] == "offline" and f1["resolution"]["status"] == "open"
    assert report["review"]["status"] == "pending"

    url = f"/drift/reports/{report['id']}/findings/F1/resolution"
    r = client.put(url, json={"status": "resolved", "actor": "7", "note": "README updated"})
    assert r.status_code == 200 and r.json()["resolution"]["status"] == "resolved"
    assert client.put(url, json={"status": "dismissed"}).status_code == 422
    assert client.put(url, json={"status": "done"}).status_code == 422
    assert client.put(f"/drift/reports/{report['id']}/findings/F99/resolution",
                      json={"status": "resolved"}).status_code == 404
    assert client.put("/drift/reports/nope/findings/F1/resolution", json={"status": "resolved"}).status_code == 404
    again = client.get(f"/drift/reports/{report['id']}").json()
    assert again["findings"][0]["resolution"]["history"][0]["note"] == "README updated"
    assert again["review"]["resolved"] == 1
    row = client.get("/drift/reports", params={"repository": "acme/shop"}).json()[0]
    assert row["review"]["status"] == "in_progress"
