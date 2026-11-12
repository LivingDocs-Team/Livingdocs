"""LD-356 Implement AI confidence scoring: validate the scores of generated documentation (LD-340,
app/confidence.py) and of drift findings (LD-147, app/drift.py).

Acceptance criteria:
    scores are bounded              always 0-1, rounded half-up to 2 decimals, NaN / inf -> 0
    thresholds consistent           one HIGH / MEDIUM pair used by levels, drift severity and Markdown
    unknown evidence penalized      -0.10 per unknown id (max 0.30), for the generator and the AI review
    boundary tests pass             0, 0.495, 0.50, 0.745, 0.75, 1 and out-of-range values
    missing evidence                lowers the score: a finding / entity without its proof is never high
    reproducibility                 the same input gives the same scores, levels and order
"""
import json
import math
import os
import re
from types import SimpleNamespace

os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import confidence, drift, drift_severity  # noqa: E402
from app.confidence import (HIGH, LEVELS_TEXT, MEDIUM, average, bounded, citation_penalty,  # noqa: E402
                            level_of, score_entity)
from app.doc_schema import FunctionDoc  # noqa: E402
from app.drift import analyze, evidence_factor  # noqa: E402
from app.drift_models import (ChangedFile, DriftAnalyzeRequest, DriftEvidence,  # noqa: E402
                              DriftEvidenceKind, DriftType)
from app.drift_review import DriftReviewer  # noqa: E402
from app.evidence import build_catalog, entities  # noqa: E402
from app.generator import DocGenerator  # noqa: E402
from app.models import ConfidenceLevel, EntityReport, FileAnalysis  # noqa: E402
from app.renderer import _score_text  # noqa: E402
from app.templates import templates  # noqa: E402
from app.versions import DocumentStore  # noqa: E402
from drift_fixtures import AFTER, BEFORE, PATCH, PR, README  # noqa: E402
from test_drift_cases import CASES, run as run_case  # noqa: E402

ROUTES = FileAnalysis.model_validate({
    "path": "shop/routes.py", "language": "python",
    "functions": [{"name": "get_cart_total", "signature": "async def get_cart_total(cart_id: int) -> float",
                   "parameters": [{"name": "cart_id", "type": "int"}], "return_type": "float",
                   "docstring": "Return the cart total.",
                   "source": "async def get_cart_total(cart_id: int) -> float:\n    return 1.0",
                   "line_start": 5, "line_end": 7}]})


def entity_score(evidence, self_score=1.0, summary="Returns the total.", own=True, ai_mode=True):
    """Score get_cart_total (input quality 1.0, own evidence E1) for one AI answer."""
    catalog = build_catalog(ROUTES)
    ent = entities(ROUTES)[0]
    if not own:
        catalog.own.pop(ent.key)
    doc = FunctionDoc(name=ent.key, summary=summary, evidence=evidence, confidence=self_score)
    return score_entity(ent, doc, catalog, ai_mode)


# ---------- bounded scores ----------

@pytest.mark.parametrize("raw, expected", [
    (0, 0.0), (1, 1.0), (0.5, 0.5), (-0.2, 0.0), (1.7, 1.0), (7, 1.0),
    (0.745, 0.75), (0.7449999999999999, 0.75), (0.7449, 0.74), (0.495, 0.5), (0.4949, 0.49),
    (0.005, 0.01), (0.004, 0.0), (0.995, 1.0),
    (float("nan"), 0.0), (float("inf"), 0.0), (float("-inf"), 0.0), (None, 0.0), ("high", 0.0), ("0.8", 0.8),
])
def test_scores_are_bounded_and_rounded_half_up(raw, expected):
    assert bounded(raw) == expected
    assert 0.0 <= bounded(raw) <= 1.0


@pytest.mark.parametrize("score, level", [
    (0.0, "low"), (0.4949, "low"), (0.495, "medium"), (0.5, "medium"), (0.7449, "medium"),
    (0.745, "high"), (0.75, "high"), (1.0, "high"), (-1, "low"), (3, "high"), (float("nan"), "low"),
])
def test_level_boundaries_follow_the_score_that_is_shown(score, level):
    assert level_of(score).value == level
    assert level_of(None) is None


def test_thresholds_are_defined_once_and_used_everywhere():
    assert (HIGH, MEDIUM) == (0.75, 0.50)
    assert drift_severity.UNCERTAIN_CONFIDENCE == MEDIUM
    assert LEVELS_TEXT in confidence.METHOD and LEVELS_TEXT in drift.METHOD
    labels = {"levels": {"high": "high", "medium": "medium", "low": "low"}}
    for n in range(0, 1001):
        s = n / 1000
        lvl = level_of(s)
        # drift severity treats a finding as uncertain exactly when its confidence level is low
        assert (lvl == ConfidenceLevel.low) == (bounded(s) < drift_severity.UNCERTAIN_CONFIDENCE), s
        # the Markdown shows the same rounded score and the same level as the report
        assert _score_text(s, labels) == f"{bounded(s):.2f} ({lvl.value})", s


def test_uncertain_severity_rule_uses_the_rounded_confidence():
    def rules(c):
        a = drift_severity.assess(DriftType.referential, "entity_gone", [], c, [])
        return [s.rule for s in a.adjustments]
    assert "uncertain_match" in rules(0.4949)          # 0.49: low
    assert "uncertain_match" not in rules(0.495)       # 0.50: medium
    assert drift_severity.score_of(drift_severity.Severity.high, float("nan")) == \
        drift_severity.score_of(drift_severity.Severity.high, 0.0)


def test_models_reject_unbounded_scores():
    with pytest.raises(ValidationError):
        EntityReport(kind="function", name="f", confidence=1.5, level=ConfidenceLevel.high)
    with pytest.raises(ValidationError):
        EntityReport(kind="function", name="f", confidence=-0.1, level=ConfidenceLevel.low)


def test_average_skips_missing_scores_and_stays_bounded():
    assert average([]) is None and average([None, None]) is None
    assert average([0.5, None, 1.0]) == 0.75
    assert average([0.745]) == 0.75


# ---------- generated documentation (app/confidence.py) ----------

def test_formula_reaches_exactly_one_and_zero():
    assert math.isclose(confidence.W_INPUT + confidence.W_GROUND + confidence.W_DESCRIBED
                        + confidence.W_SELF, 1.0)
    assert entity_score(["E1"]).confidence == 1.0
    worst = entity_score(["Z1", "Z2", "Z3", "Z4"], self_score=0.0, summary="", own=False)
    assert worst.confidence == 0.0 and worst.level == ConfidenceLevel.low


@pytest.mark.parametrize("unknown, expected", [(0, 1.0), (1, 0.9), (2, 0.8), (3, 0.7), (6, 0.7)])
def test_each_unknown_id_is_penalised_up_to_the_cap(unknown, expected):
    r = entity_score(["E1"] + [f"Z{n}" for n in range(unknown)])
    assert r.confidence == expected and r.factors["invalid_citations"] == unknown
    assert citation_penalty(unknown) == round(1.0 - expected, 2)


def test_ids_are_matched_ignoring_case_and_duplicates_count_once():
    r = entity_score(["e1", " E1 ", "x9", "X9"])
    assert [e.id for e in r.evidence] == ["E1"]
    assert r.factors["invalid_citations"] == 1 and r.confidence == 0.9


def test_citing_only_unknown_ids_gives_no_grounding():
    r = entity_score(["Z1", "Z2"])
    # .30 input + 0 grounding + .20 described + .20 self - .20 penalty
    assert r.factors["grounding"] == 0.0 and r.confidence == 0.5 and r.level == ConfidenceLevel.medium


def test_missing_own_evidence_is_never_high():
    best = entity_score(["E1"], own=False)
    # E1 is no longer its own code: grounding 0.5 -> (.30 + .15 + .20 + .20) x .70 = 0.595
    assert best.factors["own_evidence"] == 0.0 and best.confidence == 0.6
    assert best.level == ConfidenceLevel.medium
    offline = entity_score([], own=False, ai_mode=False)
    assert offline.confidence == bounded(confidence.NO_AI_FACTOR * 0.7)


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), "nan", True, "very sure", None])
def test_unusable_self_assessment_counts_as_missing(raw):
    doc = FunctionDoc(name="get_cart_total", summary="x", evidence=["E1"], confidence=raw)
    assert doc.confidence is None
    assert entity_score(["E1"], self_score=raw).factors["self_assessed"] == confidence.DEFAULT_SELF


def test_generation_scores_are_reproducible():
    gen, tpl = DocGenerator(None), templates.get("default")
    a = gen.document_file(ROUTES, tpl, "en").report
    b = gen.document_file(ROUTES, tpl, "en").report
    assert a.model_dump() == b.model_dump()
    assert a.confidence == bounded(a.confidence) and a.level == level_of(a.confidence)


# ---------- drift findings (app/drift.py) ----------

def ev(kind, excerpt="line"):
    return DriftEvidence(id="X1" if kind == "code_diff" else "D1", kind=DriftEvidenceKind(kind),
                         path="a.py", excerpt=excerpt)


def test_missing_drift_evidence_lowers_confidence():
    hit = SimpleNamespace(matches=[SimpleNamespace(exact=True, in_code=True)], param_matches=[],
                          documents_file=True, target=SimpleNamespace(change=SimpleNamespace(source="analysis")))
    cl = SimpleNamespace(details=[], certainty=1.0)

    def score(evidence):
        return drift._confidence(hit, cl, evidence)

    assert score([ev("code_diff"), ev("documentation")]) == (1.0, {
        "match": 1.0, "method": 1.0, "location": 1.0, "certainty": 1.0, "evidence": 1.0})
    no_doc, factors = score([ev("code_diff"), ev("commit")])
    assert (no_doc, factors["evidence"], level_of(no_doc).value) == (0.7, 0.7, "medium")
    assert score([ev("documentation")])[0] == 0.7
    assert score([ev("code_diff", excerpt="  "), ev("documentation")])[0] == 0.7   # empty proof
    nothing = score([])[0]
    assert nothing == 0.49 and level_of(nothing) == ConfidenceLevel.low
    assert evidence_factor([]) == 0.49


def drift_report(reviewer=None, docs=(README,), ai_review=True):
    req = DriftAnalyzeRequest(repository="acme/shop", pull_request=PR, docs=list(docs), document_ids=[],
                              files=[ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER)],
                              ai_review=ai_review)
    return analyze(req, DocumentStore(None), reviewer=reviewer)


class CitingModel:
    """Confirms every finding, citing its first evidence id plus the given made-up ids."""

    def __init__(self, extra):
        self.extra = extra

    def complete(self, system, messages):
        reviews = []
        for block in re.split(r"\n(?=- F\d+ )", messages[0]["content"]):
            m = re.match(r"- (F\d+) ", block)
            if m:
                ids = re.findall(r"^  ([XDCT]\d+) ", block, re.M)
                reviews.append({"id": m.group(1), "verdict": "confirmed",
                                "explanation": f"Outdated [{ids[0]}].", "evidence": ids[:1] + self.extra})
        return json.dumps({"reviews": reviews})


def test_unknown_ids_in_the_ai_review_lower_confidence_not_severity():
    offline = drift_report(ai_review=False)
    clean = drift_report(DriftReviewer(CitingModel([])))
    bad = drift_report(DriftReviewer(CitingModel(["Z9", "Z8"])))
    assert [f.confidence for f in clean.findings] == [f.confidence for f in offline.findings]
    for o, f in zip(offline.findings, bad.findings):
        assert (f.id, f.severity, f.severity_assessment.score) == (o.id, o.severity, o.severity_assessment.score)
        assert f.ai_review.invalid_citations == ["Z9", "Z8"] and f.factors["invalid_citations"] == 2
        assert f.confidence == bounded(o.confidence - 0.2)
        assert f.confidence_level == level_of(f.confidence).value
    assert all(f.factors["invalid_citations"] == 0 for f in clean.findings)


def test_every_drift_score_is_bounded_and_consistent():
    for name in sorted(CASES):
        for mode in ("analysis", "patch"):
            for f in run_case(name, mode).findings:
                assert 0.0 <= f.confidence <= 1.0 and f.confidence == bounded(f.confidence), (name, f.id)
                assert f.confidence_level == level_of(f.confidence).value, (name, f.id)
                assert f.factors["evidence"] == evidence_factor(f.evidence), (name, f.id)


def test_drift_scores_are_reproducible():
    def key(r):
        return [(f.id, f.type.value, f.entity, f.document.path, f.confidence, f.confidence_level,
                 f.factors, f.severity.value, f.severity_assessment.score) for f in r.findings]
    other = {"path": "docs/cart.md", "content": "# Cart\n\nCall `get_total(cart)` to get the total.\n"}
    first = drift_report(docs=(README, other), ai_review=False)
    again = drift_report(docs=(README, other), ai_review=False)
    swapped = drift_report(docs=(other, README), ai_review=False)
    assert key(first) == key(again) == key(swapped)
    assert first.summary.model_dump() == swapped.summary.model_dump()
