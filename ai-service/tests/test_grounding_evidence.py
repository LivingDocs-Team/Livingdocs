"""LD-355: tests for AI grounding evidence (FR-AI-04).

Cases GE-xx of Docs/Linh/LD-355-Grounding-Evidence.md. The AI is a fake client that
returns fixed JSON, so we control exactly which evidence ids it cites.
"""
import json
import os

os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402

from app.confidence import INVALID_CITATION_PENALTY, score_entity  # noqa: E402
from app.doc_schema import FunctionDoc, citation_ids, parse_file_doc  # noqa: E402
from app.evidence import build_catalog, entities, location  # noqa: E402
from app.generator import DocGenerator  # noqa: E402
from app.jobs import jobs, run_job  # noqa: E402
from app.models import ContextDocument, FileAnalysis, GenerateRequest  # noqa: E402
from app.retrieval import build_index, retrieve  # noqa: E402

ROUTES = {
    "path": "shop/routes.py", "language": "python",
    "functions": [{"name": "get_cart_total", "parameters": [{"name": "cart_id", "type": "int"}],
                   "return_type": "float", "docstring": "Return the cart total.",
                   "source": "def get_cart_total(cart_id: int) -> float:\n    return CartService().total(cart_id)",
                   "line_start": 5, "line_end": 7}],
    "endpoints": [{"http_method": "GET", "path": "/carts/{cart_id}/total", "handler": "get_cart_total",
                   "response": "float"}],                       # no line numbers from the analyzer
}
SERVICE = {
    "path": "shop/cart_service.py", "language": "python",
    "classes": [{"name": "CartService", "docstring": "Cart rules.", "line_start": 3, "line_end": 20,
                 "methods": [{"name": "total", "parameters": [{"name": "cart_id", "type": "int"}],
                              "return_type": "float", "source": "def total(self, cart_id): ...",
                              "line_start": 10, "line_end": 14}]}],
}
README = ContextDocument(path="README.md", content="# Shop\n\n## Cart\n\nThe cart total is computed by CartService.\n")


def fa(d) -> FileAnalysis:
    return FileAnalysis.model_validate(d)


def req(files, context=()):
    return GenerateRequest.model_validate({"scope": "repository", "target": "shop", "files": files,
                                           "context": [c.model_dump() for c in context]})


class Fixed:
    def __init__(self, *answers):
        self.answers = [a if isinstance(a, str) else json.dumps(a) for a in answers]
        self.calls = 0

    def complete(self, system, messages):
        self.calls += 1
        return self.answers.pop(0)


def run(files, *answers, context=()):
    c = Fixed(*answers)
    r = req(files, context)
    job = jobs.create(r)
    run_job(job.id, r, generator=DocGenerator(c, max_attempts=len(answers), backoff_seconds=0))
    return jobs.get(job.id), jobs.get_report(job.id), c


def entity(report, path, name):
    fr = next(f for f in report.files if f.path == path)
    return next(e for e in fr.entities if e.name == name)


# ---------- GE-01 .. GE-05: citation ids from the AI ----------

@pytest.mark.parametrize("raw, ids", [
    (["E1", "C2"], ["E1", "C2"]),
    ("E1, C2", ["E1", "C2"]),                        # one string instead of a list
    (["[E1]", "e2:", " D1 "], ["E1", "E2", "D1"]),   # brackets, case, punctuation
    (["E01", "E1"], ["E1"]),                         # leading zeros, duplicates
    (["E1 (own code)", "see C3 and D2"], ["E1", "C3", "D2"]),
    (None, []), ([], []), ([None, "", "  "], []),
    (["source code"], ["source code"]),              # not an id: kept, reported as invalid
    (["CartService", "E2E"], ["CartService", "E2E"]),  # words that only look like ids
])
def test_ge01_citation_ids_are_normalized(raw, ids):
    assert citation_ids(raw) == ids


def test_ge02_overview_evidence_as_string_does_not_cost_a_retry():
    doc = parse_file_doc('{"overview": "x", "overview_evidence": "E1, D1"}')
    assert doc.overview_evidence == ["E1", "D1"]
    _, report, c = run([ROUTES], {"overview": "x", "overview_evidence": "E1, E2", "functions": [
        {"name": "get_cart_total", "summary": "s", "evidence": "E1", "confidence": 0.9}]})
    assert c.calls == 1
    assert next(f for f in report.files).status.value == "generated"


def test_ge03_messy_citations_still_ground_the_entity():
    _, report, _ = run([ROUTES], {"overview": "x", "functions": [
        {"name": "get_cart_total", "summary": "s", "evidence": ["[E1]"], "confidence": 0.9}]})
    e = entity(report, "shop/routes.py", "get_cart_total")
    assert e.factors["grounding"] == 1.0 and e.factors["invalid_citations"] == 0.0


def test_ge04_unknown_ids_are_penalized_and_warned():
    cat = build_catalog(fa(ROUTES))
    ent = entities(fa(ROUTES))[0]
    good = score_entity(ent, FunctionDoc(name="get_cart_total", summary="s", evidence=["E1"]), cat, True)
    bad = score_entity(ent, FunctionDoc(name="get_cart_total", summary="s", evidence=["E1", "E9"]), cat, True)
    assert round(good.confidence - bad.confidence, 2) == INVALID_CITATION_PENALTY
    assert bad.factors["invalid_citations"] == 1.0
    job, _, _ = run([ROUTES], {"overview": "x", "functions": [
        {"name": "get_cart_total", "summary": "s", "evidence": ["E1", "E9"]}]})
    assert any("ignored citations not in the evidence catalog: E9" in w for w in job.warnings)


def test_ge05_citing_another_files_own_id_is_not_grounding():
    """E ids belong to one file: 'E3' in routes.py's answer is unknown even if service.py has E3."""
    _, report, _ = run([ROUTES], {"overview": "x", "functions": [
        {"name": "get_cart_total", "summary": "s", "evidence": ["E3"]}]})
    e = entity(report, "shop/routes.py", "get_cart_total")
    assert e.factors["grounding"] == 0.0 and e.factors["invalid_citations"] == 1.0


# ---------- GE-06 .. GE-08: what the evidence points at ----------

def test_ge06_endpoint_without_lines_points_at_its_handler():
    cat = build_catalog(fa(ROUTES))
    ev = cat.own["GET /carts/{cart_id}/total"]
    assert (ev.line_start, ev.line_end) == (5, 7)
    assert location(ev) == "shop/routes.py:5-7"
    assert "return CartService().total(cart_id)" in ev.excerpt


def test_ge07_endpoint_handler_can_be_a_method():
    ctrl = {"path": "CartController.java", "language": "java",
            "classes": [{"name": "CartController", "line_start": 1, "line_end": 30, "methods": [
                {"name": "total", "line_start": 12, "line_end": 18, "signature": "public double total(long id)"}]}],
            "endpoints": [{"http_method": "GET", "path": "/carts/{id}/total", "handler": "CartController.total"}]}
    ev = build_catalog(fa(ctrl)).own["GET /carts/{id}/total"]
    assert (ev.line_start, ev.line_end) == (12, 18) and "public double total(long id)" in ev.excerpt


def test_ge08_endpoint_lines_from_analyzer_win_and_unknown_handler_is_safe():
    with_lines = {**ROUTES, "endpoints": [{**ROUTES["endpoints"][0], "line_start": 4, "line_end": 4}]}
    assert location(build_catalog(fa(with_lines)).own["GET /carts/{cart_id}/total"]) == "shop/routes.py:4"
    unknown = {**ROUTES, "endpoints": [{"http_method": "POST", "path": "/x", "handler": "elsewhere.run"}]}
    ev = build_catalog(fa(unknown)).own["POST /x"]
    assert ev.line_start is None and location(ev) == "shop/routes.py"


# ---------- GE-09 .. GE-10: overloads and ids shared by the whole file ----------

OVERLOADS = {"path": "Calc.java", "language": "java", "classes": [{"name": "Calc", "methods": [
    {"name": "add", "signature": "int add(int a, int b)", "line_start": 3, "line_end": 5},
    {"name": "add", "signature": "double add(double a, double b)", "line_start": 7, "line_end": 9}]}]}


def test_ge09_citing_any_overload_grounds_the_method():
    cat = build_catalog(fa(OVERLOADS))
    assert cat.own_ids["Calc.add"] == ["E2", "E3"] and cat.own["Calc.add"].id == "E2"
    ent = next(e for e in entities(fa(OVERLOADS)) if e.key == "Calc.add")
    rep = score_entity(ent, FunctionDoc(name="add", summary="Adds.", evidence=["E3"]), cat, True)
    assert rep.factors["grounding"] == 1.0
    assert [e.id for e in rep.evidence] == ["E2", "E3"]        # both overloads shown


def test_ge10_overview_citations_appear_in_sources_but_not_entity_scores():
    job, report, _ = run([SERVICE, ROUTES], {"overview": "x", "overview_evidence": ["D1"], "functions": [
        {"name": "get_cart_total", "summary": "s", "evidence": ["E1"]}]},
        {"overview": "x", "overview_evidence": ["D1"], "classes": [
            {"name": "CartService", "summary": "s", "evidence": ["E1"], "methods": []}]}, context=[README])
    for fr in report.files:
        assert [e.id for e in fr.context_used] == ["D1"]
    assert "**D1** Cart" in job.result


# ---------- GE-11 .. GE-12: catalog consistency ----------

def test_ge11_every_cited_evidence_resolves_to_a_real_location():
    r = req([SERVICE, ROUTES], [README])
    index = build_index(r)
    for f in r.files:
        cat = build_catalog(f, retrieve(index, f))
        for ev in cat.by_id.values():
            assert ev.path and (ev.kind.value != "source" or ev.path == f.path)
            assert ev.line_start is None or ev.line_end is None or ev.line_start <= ev.line_end
            assert ev.excerpt and len(ev.excerpt) <= 300


def test_ge12_offline_mode_has_no_grounding_factor_and_no_sources():
    r = req([ROUTES], [README])
    job = jobs.create(r)
    run_job(job.id, r, generator=DocGenerator(None))
    rep = jobs.get_report(job.id)
    e = entity(rep, "shop/routes.py", "get_cart_total")
    assert "grounding" not in e.factors and rep.files[0].context_used == []
    assert e.evidence[0].id == "E1"                       # own code is still shown as evidence
