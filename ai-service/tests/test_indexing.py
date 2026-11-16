"""LD-335: document & code indexing for retrieval (endpoints, class fields, Markdown sections)."""
import os

os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.models import ContextDocument, GenerateRequest  # noqa: E402
from app.retrieval import build_index, retrieve, split_document  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

SERVICE = {
    "path": "shop/cart_service.py", "language": "python",
    "classes": [{"name": "CartService", "docstring": "Business rules for carts.",
                 "line_start": 3, "line_end": 30,
                 "methods": [{"name": "apply_discount", "parameters": [{"name": "code", "type": "str"}],
                              "return_type": "float", "line_start": 10, "line_end": 14}]}],
}
ROUTES = {
    "path": "shop/routes.py", "language": "python",
    "functions": [{"name": "post_discount", "line_start": 5, "line_end": 9,
                   "source": "def post_discount(code):\n    return CartService().apply_discount(code)"}],
    "endpoints": [{"http_method": "POST", "path": "/carts/{cart_id}/discount", "handler": "post_discount",
                   "parameters": [{"name": "cart_id", "type": "int"}], "request_body": "DiscountCode",
                   "response": "Cart total after discount", "line_start": 4, "line_end": 9}],
}
MODELS = {
    "path": "shop/models.py", "language": "python",
    "classes": [{"name": "Invoice", "kind": "class", "line_start": 1, "line_end": 8,
                 "fields": [{"name": "vat_rate", "type": "float"}, {"name": "license_plate", "type": "str"}]}],
}
GUIDE = ContextDocument(path="docs/guide.md", title="Guide", content="\n".join([
    "# Shop",                      # 1
    "",                            # 2
    "Intro.",                      # 3
    "",                            # 4
    "## Cart",                     # 5
    "",                            # 6
    "Discount codes lower the cart total.",  # 7
    "",                            # 8
    "```bash",                     # 9
    "# install the service",       # 10  <- shell comment, not a heading
    "pip install shop",            # 11
    "```",                         # 12
    "",                            # 13
    "### VAT",                     # 14
    "",                            # 15
    "Invoices add the VAT rate.",  # 16
    "",                            # 17
    "## Deployment",               # 18
    "",                            # 19
    "Run docker compose up.",      # 20
]))


def req(files, context=()):
    return GenerateRequest.model_validate({"scope": "repository", "target": "shop", "files": files,
                                           "context": [c.model_dump() for c in context]})


def test_endpoints_are_indexed_and_found_from_the_service_file():
    r = req([SERVICE, ROUTES])
    names = {c.name: c for c in build_index(r).chunks}
    ep = names["POST /carts/{cart_id}/discount"]
    assert ep.entity == "endpoint" and ep.path == "shop/routes.py" and (ep.line_start, ep.line_end) == (4, 9)
    assert ep.excerpt.splitlines()[0] == "POST /carts/{cart_id}/discount -> post_discount"
    assert "request: DiscountCode" in ep.excerpt
    got = retrieve(build_index(r), r.files[0])                 # cart_service.py
    assert "POST /carts/{cart_id}/discount" in [c.name for c in got.code]


def test_class_fields_are_indexed():
    r = req([MODELS, ROUTES])
    inv = next(c for c in build_index(r).chunks if c.name == "Invoice")
    assert "fields: vat_rate: float, license_plate: str" in inv.excerpt
    assert {"vat", "rate", "license", "plate"} <= set(inv.tokens)


def test_hash_lines_in_code_fences_are_not_headings():
    chunks = split_document(GUIDE)
    assert all(c.name != "install the service" for c in chunks)
    cart = next(c for c in chunks if "Discount codes" in c.excerpt)
    assert cart.name == "Cart" and (cart.line_start, cart.line_end) == (5, 13)
    assert "pip install shop" in cart.excerpt          # the code block stays with its section


def test_sections_keep_heading_path_and_line_numbers():
    by_name = {c.name: c for c in split_document(GUIDE)}
    assert by_name["VAT"].section == "Shop > Cart > VAT"
    assert (by_name["VAT"].line_start, by_name["VAT"].line_end) == (14, 17)
    assert by_name["Deployment"].section == "Shop > Deployment"      # a level-2 heading closes "Cart"
    assert by_name["Shop"].section == "Shop"
    assert all(c.entity == "section" for c in by_name.values())
    # the parent heading is searchable from the child passage
    assert "cart" in by_name["VAT"].tokens


def test_document_without_headings_uses_title():
    doc = ContextDocument(path="notes.txt", title="Notes", content="Plain text about carts.")
    (only,) = split_document(doc)
    assert (only.name, only.section, only.line_start, only.line_end) == ("Notes", "Notes", 1, 1)


def test_index_stats_count_every_kind():
    r = req([SERVICE, ROUTES, MODELS, {"path": "bad.py", "status": "invalid", "error": "x"}], [GUIDE])
    st = build_index(r).stats()
    assert st.files == 3 and st.documents == 1
    assert st.chunks == {"class": 2, "endpoint": 1, "function": 1, "method": 1, "section": 4}
    assert st.vocabulary > 10


def test_retrieved_hits_carry_scores_sorted_and_index_is_untouched():
    r = req([SERVICE, ROUTES], [GUIDE])
    index = build_index(r)
    got = retrieve(index, r.files[1])
    scores = [c.score for c in got.code]
    assert scores == sorted(scores, reverse=True) and all(0 < s <= 1 for s in scores)
    assert all(c.score == 0.0 and c.ref == "" for c in index.chunks)   # results are copies


def test_retrieval_is_deterministic():
    r = req([SERVICE, ROUTES, MODELS], [GUIDE])
    a = [(c.ref, c.name, c.score) for c in retrieve(build_index(r), r.files[1]).code]
    b = [(c.ref, c.name, c.score) for c in retrieve(build_index(r), r.files[1]).code]
    assert a == b


def test_preview_endpoint():
    body = {"scope": "repository", "target": "shop",
            "files": [SERVICE, ROUTES, {"path": "bad.py", "status": "invalid", "error": "x"}],
            "context": [GUIDE.model_dump()]}
    jobs_before = len(client.get("/jobs").json())
    r = client.post("/retrieval/preview", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["index"]["files"] == 2 and out["index"]["documents"] == 1
    assert [f["path"] for f in out["files"]] == ["shop/cart_service.py", "shop/routes.py"]
    routes = out["files"][1]
    assert routes["code"][0]["ref"] == "C1" and routes["code"][0]["path"] == "shop/cart_service.py"
    assert routes["docs"][0]["ref"] == "D1" and routes["docs"][0]["section"].startswith("Shop")
    assert all(h["score"] > 0 for h in routes["code"] + routes["docs"])
    assert len(client.get("/jobs").json()) == jobs_before          # nothing generated


def test_preview_validates_input():
    assert client.post("/retrieval/preview", json={"scope": "repository", "target": "x",
                                                   "files": []}).status_code == 422
