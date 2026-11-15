"""LD-339: tests for RAG (retrieval-augmented generation) and knowledge retrieval, end to end.

Each test is one case of Docs/Linh/LD-339-Kiem-thu-RAG.md (RAG-xx). The AI is a fake client
that records the prompts it receives and answers with fixed JSON, so we can check what
context reached the model and how its citations come back in the documentation and report.
"""
import json
import os
import re

os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.evidence import build_catalog  # noqa: E402
from app.generator import DocGenerator  # noqa: E402
from app.jobs import jobs, run_job  # noqa: E402
from app.models import ContextDocument, GenerateRequest  # noqa: E402
from app.normalize import normalize  # noqa: E402
from app.prompts import build_file_prompt  # noqa: E402
from app.retrieval import MAX_EXCERPT_CHARS, build_index, retrieve  # noqa: E402
from app.templates import templates  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)
TPL = templates.get("default")

SERVICE = {
    "path": "shop/cart/service.py", "language": "python",
    "classes": [{"name": "CartService", "docstring": "Business rules for carts.", "line_start": 1, "line_end": 40,
                 "methods": [{"name": "total", "parameters": [{"name": "cart_id", "type": "int"}],
                              "return_type": "float", "line_start": 10, "line_end": 14,
                              "source": "def total(self, cart_id):\n    return compute_vat(subtotal)"}]}],
}
ROUTES = {
    "path": "shop/cart/routes.py", "language": "python",
    "functions": [{"name": "get_cart_total", "parameters": [{"name": "cart_id", "type": "int"}],
                   "return_type": "float", "line_start": 5, "line_end": 7,
                   "source": "def get_cart_total(cart_id):\n    return CartService().total(cart_id)"}],
    "endpoints": [{"http_method": "GET", "path": "/carts/{cart_id}/total", "handler": "get_cart_total",
                   "line_start": 4, "line_end": 7}],
}
TAX = {"path": "shop/pricing/tax.py", "language": "python",
       "functions": [{"name": "compute_vat", "parameters": [{"name": "amount", "type": "float"}],
                      "return_type": "float", "line_start": 3, "line_end": 6}]}
README = ContextDocument(path="README.md", title="Shop", content=(
    "# Shop\n\nOnline shop backend.\n\n## Cart\n\nThe cart total is computed by CartService and includes VAT.\n\n"
    "## Deployment\n\nRun docker compose up.\n"))


def req(files, context=(), scope="repository"):
    return GenerateRequest.model_validate({"scope": scope, "target": "shop", "files": files,
                                           "context": [c.model_dump() for c in context]})


class Recorder:
    """Fake LLM: records every prompt, answers with the JSON built by `reply(prompt)`."""

    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def complete(self, system, messages):
        self.prompts.append(messages[-1]["content"])
        return self.reply(messages[-1]["content"])


def cite_everything(prompt: str) -> str:
    """An answer that cites every catalog id in the prompt for every item it describes."""
    ids = re.findall(r"^- ([ECD]\d+):", prompt, re.M)
    names = re.findall(r'"name": "([^"]+)"', prompt)
    return json.dumps({"overview": "Overview.", "overview_evidence": ids,
                       "functions": [{"name": n, "summary": "Does it.", "evidence": ids, "confidence": 0.8}
                                     for n in names if n == "get_cart_total"],
                       "classes": [], "endpoints": []})


def run(files, context=(), reply=cite_everything):
    rec = Recorder(reply)
    r = req(files, list(context))
    job = jobs.create(r)
    run_job(job.id, r, generator=DocGenerator(rec, max_attempts=1, backoff_seconds=0))
    return jobs.get(job.id), jobs.get_report(job.id), rec


def prompt_for(rec: Recorder, path: str) -> str:
    """The prompt written for `path`: its own code (E1) points at that file."""
    return next(p for p in rec.prompts if re.search(rf"^- E1: .*\({re.escape(path)}[:)]", p, re.M))


# ---------- RAG-01 .. RAG-05: what reaches the prompt ----------

def test_rag01_prompt_contains_related_code_and_docs_with_locations():
    job, _, rec = run([SERVICE, ROUTES, TAX], [README])
    p = prompt_for(rec, "shop/cart/routes.py")
    assert "Related code from other files:" in p and "Existing documentation:" in p
    assert re.search(r"- C1: CartService\.total \(shop/cart/service\.py:10-14\)", p)
    assert re.search(r"- D1: Cart \(README\.md:5-8\)", p)
    assert "docker" not in p                         # unrelated passage stays out


def test_rag02_own_file_is_never_retrieved_as_related_code():
    r = req([SERVICE, ROUTES, TAX], [README])
    index = build_index(r)
    for f in r.files:
        assert all(c.path != f.path for c in retrieve(index, f).code)


def test_rag03_limits_and_excerpt_size_bound_the_prompt():
    many = [{"path": f"shop/m{i}.py", "functions": [{"name": f"cart_total_{i}", "docstring": "cart total " * 200}]}
            for i in range(12)]
    big = ContextDocument(path="big.md", content="\n\n".join(f"## Cart {i}\n\n" + "cart total " * 400 for i in range(10)))
    r = req([ROUTES, *many], [big])
    got = retrieve(build_index(r), r.files[0])
    assert len(got.code) == 4 and len(got.docs) == 3
    assert all(len(c.excerpt) <= MAX_EXCERPT_CHARS for c in got.code + got.docs)
    assert [c.ref for c in got.code] == ["C1", "C2", "C3", "C4"] and [d.ref for d in got.docs] == ["D1", "D2", "D3"]


def test_rag04_no_context_and_single_file_gives_no_context_section():
    _, _, rec = run([ROUTES])
    assert "Related code from other files" not in rec.prompts[0]
    assert "Existing documentation" not in rec.prompts[0]


def test_rag05_skipped_files_are_not_indexed():
    broken = {"path": "shop/cart/service.py", "status": "invalid", "error": "SyntaxError"}
    r = req([broken, ROUTES], [README])
    index = build_index(r)
    assert all(c.path != "shop/cart/service.py" for c in index.chunks)
    assert index.stats().files == 1


# ---------- RAG-06 .. RAG-09: citations come back correctly ----------

def test_rag06_cited_context_is_listed_in_sources_and_report():
    job, report, _ = run([SERVICE, ROUTES], [README])
    md = job.result
    routes_doc = md.split("# shop/cart/routes.py", 1)[1]
    assert "## Nguồn tham chiếu" in routes_doc
    assert "**C1** CartService" in routes_doc and "**D1** Cart — `README.md:5-8`" in routes_doc
    fr = next(f for f in report.files if f.path == "shop/cart/routes.py")
    used = {(e.id, e.kind.value, e.path) for e in fr.context_used}
    assert ("D1", "doc", "README.md") in used and any(i.startswith("C") for i, _, _ in used)


def test_rag07_ids_in_prompt_and_catalog_are_the_same():
    r = req([SERVICE, ROUTES, TAX], [README])
    for f in r.files:
        normalize(f)
    index = build_index(r)
    for f in r.files:
        cat = build_catalog(f, retrieve(index, f))
        prompt = build_file_prompt(f, TPL, "vi", cat)
        assert set(re.findall(r"^- ([ECD]\d+):", prompt, re.M)) == set(cat.by_id)


def test_rag08_uncited_context_is_not_listed_as_a_source():
    def own_only(prompt):
        return json.dumps({"overview": "x", "functions": [{"name": "get_cart_total", "summary": "s",
                                                            "evidence": ["E1"], "confidence": 0.9}]})
    job, report, _ = run([SERVICE, ROUTES], [README], reply=own_only)
    routes_doc = job.result.split("# shop/cart/routes.py", 1)[1]
    assert "Nguồn tham chiếu" not in routes_doc
    assert next(f for f in report.files if f.path == "shop/cart/routes.py").context_used == []


def test_rag09_citing_retrieved_context_counts_as_grounding():
    def cite(ids):
        return lambda prompt: json.dumps({"overview": "x", "functions": [
            {"name": "get_cart_total", "summary": "s", "evidence": ids, "confidence": 0.5}]})
    _, rep_own, _ = run([SERVICE, ROUTES], [README], reply=cite(["E1"]))
    _, rep_ctx, _ = run([SERVICE, ROUTES], [README], reply=cite(["C1"]))
    _, rep_none, _ = run([SERVICE, ROUTES], [README], reply=cite([]))

    def score(rep):
        fr = next(f for f in rep.files if f.path == "shop/cart/routes.py")
        return next(e for e in fr.entities if e.name == "get_cart_total").factors["grounding"]
    assert (score(rep_own), score(rep_ctx), score(rep_none)) == (1.0, 0.5, 0.0)


# ---------- RAG-10 .. RAG-14: knowledge retrieval quality ----------

def test_rag10_vietnamese_docs_match_vietnamese_identifiers():
    bill = {"path": "parking/hoa_don.py", "classes": [{"name": "HoaDon", "methods": [
        {"name": "tinh_tien", "parameters": [{"name": "luot_gui", "type": "LuotGui"}]}]}]}
    a = {"path": "parking/a.py", "functions": [{"name": "noop"}]}
    b = {"path": "parking/b.py", "functions": [{"name": "noop2"}]}
    guide = ContextDocument(path="huong-dan.md", content=(
        "# Hướng dẫn\n\n## Hóa đơn\n\nHóa đơn được tính từ lượt gửi xe khi xe ra.\n\n"
        "## Thẻ tháng\n\nĐăng ký thẻ tháng tại quầy.\n"))
    r = req([bill, a, b], [guide])
    docs = retrieve(build_index(r), r.files[0]).docs
    assert docs and docs[0].name == "Hóa đơn"


def test_rag11_doc_passages_keep_original_text_for_the_prompt():
    guide = ContextDocument(path="vi.md", content="## Hóa đơn\n\nHóa đơn có VAT.\n")
    r = req([{"path": "a.py", "classes": [{"name": "HoaDon"}]}], [guide])
    d = retrieve(build_index(r), r.files[0]).docs[0]
    assert d.excerpt == "## Hóa đơn\n\nHóa đơn có VAT."      # folding is only for matching


def test_rag12_same_passage_twice_uses_one_slot():
    copy = ContextDocument(path="docs/copy-of-readme.md", title="Shop", content=README.content)
    r = req([SERVICE, ROUTES], [README, copy])
    docs = retrieve(build_index(r), r.files[1]).docs
    texts = [d.excerpt for d in docs]
    assert len(texts) == len(set(texts))


def test_rag13_retrieval_is_deterministic_across_jobs():
    a, _, _ = run([SERVICE, ROUTES, TAX], [README])
    b, _, _ = run([SERVICE, ROUTES, TAX], [README])
    assert a.result == b.result


def test_rag14_preview_shows_what_the_job_prompt_gets():
    body = {"scope": "repository", "target": "shop", "files": [SERVICE, ROUTES, TAX],
            "context": [README.model_dump()]}
    preview = client.post("/retrieval/preview", json=body).json()
    _, _, rec = run([SERVICE, ROUTES, TAX], [README])
    for fr in preview["files"]:
        prompt = prompt_for(rec, fr["path"])
        for hit in fr["code"] + fr["docs"]:
            assert f"- {hit['ref']}: {hit['name']} (" in prompt


# ---------- RAG-15 .. RAG-16: rules found while testing (fixed in LD-339) ----------

def test_rag15_domain_folder_shared_by_two_of_three_files_is_kept():
    """With 3 files, 'cart' in 2 paths used to be dropped from queries (60 % rule), so routes.py
    lost the README 'Cart' passage. Now only terms in >= 80 % of >= 4 paths are dropped."""
    r = req([SERVICE, ROUTES, TAX], [README])
    index = build_index(r)
    assert "cart" not in index.common_terms
    assert [d.name for d in retrieve(index, r.files[1]).docs] == ["Cart"]


def test_rag16_repository_name_folder_is_ignored_only_for_repository_scope():
    r = req([SERVICE, ROUTES, TAX], [README])
    assert build_index(r).common_terms == {"shop"}                 # target "shop" is also a folder
    m = GenerateRequest.model_validate({"scope": "module", "target": "shop.cart",
                                        "files": [SERVICE, ROUTES, TAX], "context": [README.model_dump()]})
    assert build_index(m).common_terms == set()
