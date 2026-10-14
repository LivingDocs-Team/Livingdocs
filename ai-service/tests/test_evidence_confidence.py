"""Tests for LD-340 retrieval context, evidence and confidence scores."""
import json
import os

os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.confidence import NO_AI_FACTOR, input_quality, level_of  # noqa: E402
from app.evidence import build_catalog  # noqa: E402
from app.generator import DocGenerator  # noqa: E402
from app.jobs import jobs, run_job  # noqa: E402
from app.models import (ContextDocument, FileAnalysis, FileResultStatus,  # noqa: E402
                        GenerateRequest)
from app.prompts import build_file_prompt  # noqa: E402
from app.retrieval import build_index, retrieve, split_document, tokenize  # noqa: E402
from app.templates import templates  # noqa: E402
from main import app  # noqa: E402

TPL = templates.get("default")

SERVICE = {
    "path": "shop/cart_service.py", "language": "python",
    "classes": [{"name": "CartService", "docstring": "Business rules for shopping carts.",
                 "line_start": 3, "line_end": 20,
                 "methods": [{"name": "total", "signature": "def total(self, cart_id: int) -> float",
                              "parameters": [{"name": "cart_id", "type": "int"}], "return_type": "float",
                              "source": "def total(self, cart_id: int) -> float:\n    ...",
                              "line_start": 10, "line_end": 14}]}],
}
ROUTES = {
    "path": "shop/routes.py", "language": "python",
    "functions": [{"name": "get_cart_total", "signature": "async def get_cart_total(cart_id: int) -> float",
                   "parameters": [{"name": "cart_id", "type": "int"}], "return_type": "float",
                   "docstring": "Return the cart total.",
                   "source": "async def get_cart_total(cart_id: int) -> float:\n    return CartService().total(cart_id)",
                   "line_start": 5, "line_end": 7}],
    "endpoints": [{"http_method": "GET", "path": "/carts/{cart_id}/total", "handler": "get_cart_total",
                   "parameters": [{"name": "cart_id", "type": "int"}], "response": "float",
                   "line_start": 4}],
}
README = ContextDocument(path="README.md", title="Shop", content=(
    "# Shop\n\nIntro text.\n\n## Cart\n\nThe cart total includes VAT and is computed by "
    "CartService. Totals are returned in VND.\n\n## Deployment\n\nRun docker compose up.\n"))


def req(files, context=(), scope="repository"):
    return GenerateRequest.model_validate({"scope": scope, "target": "shop", "files": files,
                                           "context": [c.model_dump() for c in context]})


class FakeClient:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def complete(self, system, messages):
        self.calls.append(messages)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def ai(*responses):
    c = FakeClient(*responses)
    return DocGenerator(c, max_attempts=len(responses) or 1, backoff_seconds=0), c


# ---------- retrieval ----------

def test_tokenize_splits_identifiers():
    assert tokenize("getCartTotal cart_id") == ["get", "cart", "total", "cart", "id"]


def test_split_document_keeps_headings_and_line_numbers():
    chunks = split_document(README)
    cart = next(c for c in chunks if "VAT" in c.excerpt)
    assert cart.name == "Cart" and cart.line_start == 5 and cart.path == "README.md"


def test_retrieves_related_code_from_other_files_and_relevant_docs():
    r = req([SERVICE, ROUTES], [README])
    got = retrieve(build_index(r), r.files[1])           # routes.py
    assert got.code and all(c.path == "shop/cart_service.py" for c in got.code)
    assert got.code[0].ref == "C1" and "CartService" in {c.name.split(".")[0] for c in got.code}
    assert got.docs and got.docs[0].ref == "D1" and "VAT" in got.docs[0].excerpt
    assert all("docker" not in d.excerpt for d in got.docs)


def test_no_context_means_no_retrieval_noise():
    r = req([ROUTES])
    got = retrieve(build_index(r), r.files[0])
    assert got.code == [] and got.docs == []


# ---------- prompt / catalog ----------

def test_prompt_lists_evidence_catalog():
    r = req([SERVICE, ROUTES], [README])
    f = r.files[1]
    cat = build_catalog(f, retrieve(build_index(r), f))
    p = build_file_prompt(f, TPL, "vi", cat)
    assert "Evidence catalog" in p
    assert "E1: get_cart_total (shop/routes.py:5-7)" in p
    assert "E2: GET /carts/{cart_id}/total (shop/routes.py:4)" in p
    assert "C1:" in p and "D1:" in p and "VAT" in p


# ---------- confidence ----------

def answer(**over):
    data = {"overview": "Cart API.", "overview_evidence": ["E1", "D1"],
            "functions": [{"name": "get_cart_total", "summary": "Trả về tổng tiền giỏ hàng.",
                           "parameters": [{"name": "cart_id", "description": "Mã giỏ."}],
                           "returns": "Tổng tiền.", "evidence": ["E1", "C1", "D1"], "confidence": 0.8}],
            "endpoints": [{"method": "GET", "path": "/carts/{cart_id}/total",
                           "summary": "Lấy tổng tiền.", "evidence": ["E2"], "confidence": 0.9}]}
    data.update(over)
    return json.dumps(data)


def run_routes(gen, context=(README,)):
    r = req([SERVICE, ROUTES], list(context))
    f = r.files[1]
    return gen.document_file(f, TPL, "vi", retrieve(build_index(r), f))


def test_grounded_ai_description_scores_high_with_exact_formula():
    g, _ = ai(answer())
    res = run_routes(g)
    fn = next(e for e in res.report.entities if e.name == "get_cart_total")
    # input quality 1.0 (source, docstring, all typed) -> .3 + .3*1 + .2*1 + .2*.8 = .96
    assert fn.confidence == 0.96 and fn.level.value == "high"
    assert [e.id for e in fn.evidence] == ["E1", "C1", "D1"]
    assert fn.evidence[0].line_start == 5 and fn.evidence[2].path == "README.md"


def test_evidence_and_confidence_are_rendered():
    g, _ = ai(answer())
    md = run_routes(g).markdown
    assert "Độ tin cậy: **0.96 (cao)**" in md
    assert "`shop/routes.py:5-7`" in md and "D1 `README.md:5-" in md
    assert "## Nguồn tham chiếu" in md and "**D1** Cart" in md


def test_uncited_description_scores_lower_than_cited():
    cited = run_routes(ai(answer())[0]).report
    bare = json.loads(answer())
    for item in bare["functions"] + bare["endpoints"]:
        item["evidence"] = []
    uncited = run_routes(ai(json.dumps(bare))[0]).report
    assert uncited.confidence < cited.confidence
    fn = next(e for e in uncited.entities if e.name == "get_cart_total")
    assert fn.factors["grounding"] == 0.0 and [e.id for e in fn.evidence] == ["E1"]


def test_invalid_citations_are_dropped_penalised_and_reported():
    bad = json.loads(answer())
    bad["functions"][0]["evidence"] = ["E1", "X9", "D7"]
    res = run_routes(ai(json.dumps(bad))[0])
    fn = next(e for e in res.report.entities if e.name == "get_cart_total")
    assert [e.id for e in fn.evidence] == ["E1"] and fn.factors["invalid_citations"] == 2
    assert fn.confidence == 0.86          # 0.96 - 0.10 penalty
    assert any("X9" in w and "D7" in w for w in res.warnings)


def test_bad_self_confidence_does_not_break_parsing():
    weird = json.loads(answer())
    weird["functions"][0]["confidence"] = "very sure"
    fn = next(e for e in run_routes(ai(json.dumps(weird))[0]).report.entities if e.name == "get_cart_total")
    assert fn.factors["self_assessed"] == 0.5


def test_offline_and_fallback_scores_use_input_quality_only():
    off = run_routes(DocGenerator(None))
    assert off.status == FileResultStatus.offline
    fn = next(e for e in off.report.entities if e.name == "get_cart_total")
    assert fn.confidence == round(NO_AI_FACTOR * 1.0, 2) and fn.level.value == "medium"
    fb = run_routes(ai("x", "x", "x")[0])
    assert fb.status == FileResultStatus.fallback
    assert fb.report.confidence < run_routes(ai(answer())[0]).report.confidence
    assert fb.report.context_used == []


def test_input_quality_and_levels():
    weak = FileAnalysis.model_validate({"path": "a.py", "functions": [
        {"name": "f", "parameters": [{"name": "x"}]}]}).functions[0]
    assert input_quality(weak) == 0.0
    assert level_of(0.75).value == "high" and level_of(0.5).value == "medium" and level_of(0.49).value == "low"


# ---------- job + API ----------

client = TestClient(app)


def test_job_report_endpoint_and_job_confidence():
    r = client.post("/generate", json={"scope": "repository", "target": "shop",
                                       "files": [SERVICE, ROUTES, {"path": "x.rb", "status": "unsupported"}],
                                       "context": [README.model_dump()]})
    job = client.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] == "completed" and job["confidence"] is not None
    assert all(fr["confidence"] is not None for fr in job["file_results"] if fr["status"] == "offline")
    rep = client.get(f"/jobs/{job['id']}/report").json()
    assert rep["confidence"] == job["confidence"] and "0.30 input quality" in rep["method"]
    routes = next(f for f in rep["files"] if f["path"] == "shop/routes.py")
    ep = next(e for e in routes["entities"] if e["kind"] == "endpoint")
    assert ep["evidence"][0]["line_start"] == 4
    assert next(f for f in rep["files"] if f["path"] == "x.rb")["status"] == "skipped"
    md = client.get(f"/jobs/{job['id']}/result").text
    assert "Độ tin cậy chung" in md


def test_report_for_unknown_job_is_404():
    assert client.get("/jobs/nope/report").status_code == 404


def test_invalid_line_numbers_rejected():
    bad = {**ROUTES, "functions": [{**ROUTES["functions"][0], "line_start": 0}]}
    assert client.post("/generate", json={"scope": "file", "target": "x", "files": [bad]}).status_code == 422


def test_job_run_directly_with_ai_uses_retrieved_context():
    g, c = ai(answer(functions=[], endpoints=[]), answer())
    r = req([SERVICE, ROUTES], [README])
    job = jobs.create(r)
    run_job(job.id, r, generator=g)
    prompt_routes = c.calls[1][0]["content"]
    assert "Related code from other files" in prompt_routes and "Existing documentation" in prompt_routes
