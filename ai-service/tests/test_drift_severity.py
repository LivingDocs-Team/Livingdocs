"""LD-160 Test drift severity assessment (LD-156).

LD-157 severity rules, LD-158 severity classification (score bands, document / report level),
LD-159 display (Markdown report, API), and the evidence behind every assessment.
"""
import os

os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402

from app.drift import analyze  # noqa: E402
from app.drift_markdown import render  # noqa: E402
from app.jobs import JobOutput  # noqa: E402
from app.models import Scope  # noqa: E402
from app.drift_models import (DRIFT_KINDS, SEVERITY_ORDER, ChangedFile, DocMatch,  # noqa: E402
                              DriftAnalyzeRequest, DriftEvidence, DriftType, Severity)
from app.drift_severity import (BASE_RULE_OF_KIND, CAPS, RULES, SCORE_BANDS,  # noqa: E402
                                SEVERITY_LEVELS, assess, classify_score, rules_table, score_of)
from app.versions import DocumentStore  # noqa: E402
from drift_fixtures import AFTER, BEFORE, CART_SECTION, PATCH, PR, README  # noqa: E402

SIGNATURE_BASES = ("breaking_signature", "compatible_signature")


def saved_store():
    store = DocumentStore(None)
    out = JobOutput(scope=Scope.repository, target="acme/shop", template_id="default",
                    template_name="Standard technical docs", output_language="en",
                    sections=[("shop/cart.py", CART_SECTION, "offline", 0.5)], confidence=0.5)
    store.create_from_job("job-1", out, title="Shop docs", actor="tester")
    return store


def full_report(docs=(README,), files=None, saved=True):
    files = files or [ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER)]
    req = DriftAnalyzeRequest(repository="acme/shop", pull_request=PR, files=files, docs=list(docs),
                              document_ids=None if saved else [])
    return analyze(req, saved_store() if saved else DocumentStore(None))


def doc_ev(eid, line):
    return DriftEvidence(id=eid, kind="documentation", path="README.md", line_start=line, line_end=line)


# ====================== LD-157 rules ======================

def test_every_kind_has_a_base_rule_and_rules_are_well_formed():
    for type_, kinds in DRIFT_KINDS.items():
        for kind in kinds:
            bases = SIGNATURE_BASES if type_ == "signature" else BASE_RULE_OF_KIND[kind]
            assert bases and all(RULES[b].kind == "base" for b in bases), kind
    for r in RULES.values():
        assert r.label and r.description
        if r.kind == "base":
            assert r.level in Severity and r.delta == 0
        else:
            assert r.level is None and r.delta in (-1, 1)
    table = rules_table()
    assert len(table) == len(RULES) and {r["id"] for r in table} == set(RULES)


def test_assessment_lists_base_rule_adjustments_and_their_evidence():
    evidence = [DriftEvidence(id="X1", kind="code_diff", path="a.py"), doc_ev("D1", 3), doc_ev("D2", 9)]
    stale = DocMatch(term="discount", target="discount", line=9, excerpt="| `discount` |", kind="parameter")
    a = assess(DriftType.signature, "breaking_signature", [("doc_states_old_detail", [stale])], 0.9, evidence)
    assert (a.base_rule, a.base_level, a.level) == ("breaking_signature", Severity.medium, Severity.high)
    assert a.base_evidence == ["X1", "D1"]
    [step] = a.adjustments
    assert (step.rule, step.delta, step.evidence) == ("doc_states_old_detail", 1, ["D2"])
    assert a.summary == "High: breaking change (medium), documentation still states the old detail (+1)."
    assert SCORE_BANDS[Severity.high][0] <= a.score <= SCORE_BANDS[Severity.high][1]


def test_adjustment_without_documentation_points_at_the_code_diff():
    evidence = [DriftEvidence(id="X1", kind="code_diff", path="a.py"), doc_ev("D1", 3)]
    a = assess(DriftType.signature, "compatible_signature", [("public_endpoint", [])], 0.9, evidence)
    assert a.level == Severity.medium and a.adjustments[0].evidence == ["X1"]


def test_semantic_drift_is_capped_at_high_and_levels_never_go_below_low():
    adjust = [("contract_behaviour", []), ("doc_states_old_detail", []), ("large_change", []),
              ("large_change", [])]
    a = assess(DriftType.semantic, "behaviour_changed", adjust, 0.9, [])
    assert a.level == Severity.high and a.capped_at == Severity.high and "capped at high" in a.summary
    assert CAPS == {"semantic": Severity.high}
    low = assess(DriftType.referential, "line_reference_shifted", [("private_name", [])], 0.9, [])
    assert low.level == Severity.low


def test_uncertain_match_lowers_the_level():
    sure = assess(DriftType.semantic, "behaviour_changed", [("contract_behaviour", [])], 0.6,
                  [doc_ev("D1", 2)])
    weak = assess(DriftType.semantic, "behaviour_changed", [("contract_behaviour", [])], 0.45,
                  [doc_ev("D1", 2)])
    assert sure.level == Severity.medium
    assert weak.level == Severity.low and weak.adjustments[-1].rule == "uncertain_match"
    assert weak.adjustments[-1].evidence == ["D1"]


def test_uncertain_prose_mention_end_to_end():
    readme = {"path": "README.md", "content": "Call fetch_cart to load a cart.\n"}
    f = next(f for f in full_report(docs=[readme], saved=False).findings
             if f.entity == "fetch_cart" and f.document.path == "README.md")
    assert f.confidence < 0.5 and f.severity == Severity.low
    assert [s.rule for s in f.severity_assessment.adjustments] == ["contract_behaviour", "uncertain_match"]
    assert f.rules == ["behaviour change: low", "callers see different results: +1", "uncertain match: -1"]


# ====================== LD-158 classification ======================

@pytest.mark.parametrize("score, level", [(0, "low"), (24, "low"), (25, "medium"), (49, "medium"),
                                          (50, "high"), (74, "high"), (75, "critical"), (100, "critical")])
def test_score_bands(score, level):
    assert classify_score(score).value == level


def test_score_stays_in_band_and_ranks_by_confidence():
    for level in SEVERITY_ORDER:
        lo, hi = SCORE_BANDS[level]
        scores = [score_of(level, c) for c in (0.0, 0.3, 0.5, 0.8, 1.0)]
        assert all(lo <= s <= hi for s in scores) and scores == sorted(scores)
        assert classify_score(scores[0]) == level == classify_score(scores[-1])
    bands = [SCORE_BANDS[lv] for lv in SEVERITY_ORDER]
    assert bands[0][0] == 0 and bands[-1][1] == 100
    assert all(a[1] + 1 == b[0] for a, b in zip(bands, bands[1:]))   # contiguous, no gap
    assert set(SEVERITY_LEVELS) == {s.value for s in Severity}


def test_every_finding_is_assessed_consistently():
    r = full_report()
    assert r.findings
    for f in r.findings:
        a = f.severity_assessment
        assert a is not None and f.severity == a.level == classify_score(a.score)
        allowed = SIGNATURE_BASES if f.type.value == "signature" else BASE_RULE_OF_KIND[f.kind]
        assert a.base_rule in allowed
        ids = {e.id for e in f.evidence}
        assert set(a.base_evidence) <= ids
        assert all(set(s.evidence) <= ids for s in a.adjustments)
        assert f.rules[0] == f"{a.base_label}: {a.base_level.value}"
    scores = [f.severity_assessment.score for f in r.findings]
    assert scores == sorted(scores, reverse=True)                       # most severe first


def test_document_and_report_levels():
    r = full_report()
    for part in r.affected_documents:
        mine = [f for f in r.findings if (f.document.source, f.document.path) == (part.source, part.path)]
        assert part.findings == len(mine)
        assert part.severity == max((f.severity for f in mine), key=SEVERITY_ORDER.index)
    levels = [SEVERITY_ORDER.index(p.severity) for p in r.affected_documents]
    assert levels == sorted(levels, reverse=True)
    s = r.summary
    assert s.highest_severity == Severity.critical
    assert s.severity_score == max(f.severity_assessment.score for f in r.findings)
    assert s.recommendation == SEVERITY_LEVELS["critical"]["action"]


def test_no_drift_has_no_level():
    r = full_report(docs=[{"path": "README.md", "content": "# Nothing about carts\n"}], saved=False)
    assert r.findings == [] and r.summary.highest_severity is None
    assert r.summary.severity_score == 0 and r.summary.recommendation is None


# ====================== LD-159 display ======================

def test_markdown_groups_findings_by_severity_with_reasons_and_evidence():
    r = full_report()
    md = render(r)
    assert md.startswith("## Documentation drift — PR #42: LD-146 Cart: currency support")
    assert "**Overall severity:** 🔴 **Critical**" in md
    assert SEVERITY_LEVELS["critical"]["action"] in md
    headings = [line for line in md.splitlines() if line.startswith("### ")]
    assert [h.split()[2] for h in headings] == ["Critical", "High", "Medium", "Low"]
    assert md.count("#### F") == len(r.findings)
    assert "- **Why High** (score" in md and "starts at medium [X1" in md
    assert "documentation still states the old detail: +1 [D" in md
    assert "<details><summary>Evidence</summary>" in md and "```diff" in md


def test_markdown_filter_and_no_drift():
    r = full_report()
    md = render(r, Severity.critical)
    shown = sum(1 for f in r.findings if f.severity == Severity.critical)
    assert f"_Showing {shown} of {len(r.findings)} findings (critical and above)._" in md
    assert "### 🟠 High" not in md and md.count("#### F") == shown
    clean = render(full_report(docs=[{"path": "README.md", "content": "# Other\n"}], saved=False))
    assert "No documentation drift" in clean


def test_api_severity_rules_filter_and_markdown():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    rules = client.get("/drift/severity-rules").json()
    assert [lv["level"] for lv in rules["levels"]] == ["critical", "high", "medium", "low"]
    assert rules["levels"][0]["min_score"] == 75 and rules["caps"] == {"semantic": "high"}
    assert {r["id"] for r in rules["rules"]} == set(RULES)

    job = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                         "output_language": "en", "files": [BEFORE]}).json()
    doc = client.post("/documents", json={"job_id": job["id"]}).json()
    body = {"repository": "acme/shop", "pull_request": PR, "docs": [README], "document_ids": [doc["id"]],
            "files": [{"path": "shop/cart.py", "patch": PATCH, "before": BEFORE, "after": AFTER}]}
    report = client.post("/drift/analyze", json=body).json()
    f0 = report["findings"][0]
    assert f0["severity_assessment"]["level"] == f0["severity"]
    assert report["affected_documents"][0]["severity"] == "critical"

    high = client.get(f"/drift/reports/{report['id']}", params={"min_severity": "high"}).json()
    assert high["findings"] and all(f["severity"] in ("high", "critical") for f in high["findings"])
    assert len(high["findings"]) < len(report["findings"])
    assert high["summary"] == report["summary"]                  # the summary still counts everything
    assert client.get(f"/drift/reports/{report['id']}", params={"min_severity": "urgent"}).status_code == 422

    md = client.get(f"/drift/reports/{report['id']}/markdown", params={"min_severity": "high"})
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert md.text.startswith("## Documentation drift") and "### 🔵 Low" not in md.text
    assert client.get("/drift/reports/nope/markdown").status_code == 404



