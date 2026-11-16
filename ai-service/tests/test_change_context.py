"""LD-338: context retrieval for code changes (POST /drift/context).

Cases CC-xx of Docs/Linh/LD-338-Context-Retrieval-Code-Changes.md. Input: the drift fixture
(shop/cart.py before/after a Pull Request), two more files of the repository and some docs.
"""
import os
import re

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline generator

from fastapi.testclient import TestClient  # noqa: E402

from app.change_context import MAX_DIFF_LINES  # noqa: E402
from drift_fixtures import AFTER, BEFORE, PATCH, PR, README  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

CHECKOUT = {"path": "shop/checkout.py", "language": "python", "functions": [
    {"name": "checkout", "parameters": [{"name": "cart_id", "type": "int"}], "lineno": 3, "end_lineno": 6,
     "source": "def checkout(cart_id):\n    total = get_cart_total(cart_id, 'VND')\n    return pay(total)"}]}
RATES = {"path": "shop/rates.py", "language": "python", "functions": [
    {"name": "convert", "parameters": [{"name": "amount", "type": "float"}, {"name": "currency", "type": "str"}],
     "return_type": "float", "docstring": "Convert an amount to a currency.", "lineno": 1, "end_lineno": 4}]}
LOG = {"path": "tools/log.py", "language": "python", "functions": [
    {"name": "write_log", "parameters": [{"name": "line", "type": "str"}], "lineno": 1, "end_lineno": 2}]}
GUIDE = {"path": "docs/pricing.md", "content": (
    "# Pricing\n\n## Currencies\n\nAmounts are converted to the currency of the customer.\n\n"
    "## Discounts\n\nA discount is subtracted from the cart total.\n\n## Deployment\n\nUse docker.\n")}


def body(**extra):
    data = {"repository": "acme/shop", "pull_request": PR,
            "files": [{"path": "shop/cart.py", "patch": PATCH, "before": BEFORE, "after": AFTER}],
            "docs": [README, GUIDE], "document_ids": [], "repository_files": [CHECKOUT, RATES, LOG]}
    data.update(extra)
    return data


def context(**extra):
    r = client.post("/drift/context", json=body(**extra))
    assert r.status_code == 200, r.text
    return r.json()


def entity(data, name):
    return next(e for e in data["entities"] if e["name"] == name)


def saved_document():
    r = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                       "output_language": "en", "files": [BEFORE]})
    job_id = r.json()["id"]
    r = client.post("/documents", json={"job_id": job_id, "actor": "tester"})
    assert r.status_code == 201, r.text
    return r.json()


# ---------- CC-01 .. CC-03: what each changed entity gets ----------

def test_cc01_one_context_per_changed_entity_and_nothing_stored():
    before = len(client.get("/drift/reports").json())
    data = context()
    changes = {e["name"]: e["change"] for e in data["entities"]}
    assert changes["get_cart_total"] == "signature_changed"
    assert changes["clear_cart"] == "removed" and changes["apply_coupon"] == "added"
    assert changes["GET /api/carts/{id}"] == "renamed"
    assert data["index"]["files"] == 4 and data["index"]["documents"] == 2
    assert data["tickets"] == ["LD-146", "LD-147"]
    assert len(client.get("/drift/reports").json()) == before


def test_cc02_diff_holds_only_the_entitys_lines():
    e = entity(context(), "get_cart_total")
    assert e["diff"]["ref"] == "X1" and (e["diff"]["line_start"], e["diff"]["line_end"]) == (10, 15)
    assert "+    return convert(total, currency)" in e["diff"]["lines"]
    assert not any("items.insert" in x for x in e["diff"]["lines"])        # Cart.add's change
    assert (e["diff"]["added"], e["diff"]["removed"]) == (3, 2)
    add = entity(context(), "Cart.add")
    assert add["diff"]["lines"] == ["     def add(self, item):", "-        self.items.append(item)",
                                    "+        self.items.insert(0, item)"]


def test_cc03_related_code_is_labelled_by_how_it_is_linked():
    code = {c["name"]: c["relation"] for c in entity(context(), "get_cart_total")["code"]}
    assert code["checkout"] == "caller"                       # calls get_cart_total
    assert code["GET /api/carts/{id}"] == "caller"            # route served by it
    assert code["convert"] == "callee"                        # used by the new code
    assert "write_log" not in code                            # unrelated
    assert "get_cart_total" not in code                       # never itself
    ep = entity(context(), "GET /api/carts/{id}")["code"]
    assert ep[0]["name"] == "get_cart_total" and ep[0]["relation"] == "handler"


# ---------- CC-04 .. CC-06: documentation ----------

def test_cc04_saved_document_passages_that_name_the_entity_come_first():
    doc = saved_document()
    e = entity(context(document_ids=[doc["id"]]), "get_cart_total")
    first = e["docs"][0]
    assert first["relation"] == "mentions" and first["document_id"] == doc["id"]
    assert first["version"] == 1 and first["path"] == "shop/cart.py"
    assert "get_cart_total" in first["matched"]
    assert first["ref"] == "D1" and "get_cart_total" in first["excerpt"]
    mentions = [d for d in e["docs"] if d["relation"] == "mentions"]
    assert all(d["score"] == 1.0 for d in mentions)
    assert [d["relation"] for d in e["docs"]] == sorted((d["relation"] for d in e["docs"]),
                                                        key=lambda r: r != "mentions")


def test_cc05_old_name_in_repository_markdown_is_found_for_renamed_endpoint():
    e = entity(context(), "GET /api/carts/{id}")
    m = next(d for d in e["docs"] if d["relation"] == "mentions")
    assert m["path"] == "README.md" and "GET /carts/:id" in m["excerpt"]


def test_cc06_new_entity_points_at_the_documentation_of_its_file():
    doc = saved_document()
    e = entity(context(document_ids=[doc["id"]]), "apply_coupon")
    own = [d for d in e["docs"] if d["relation"] == "file_doc"]
    assert own and own[0]["path"] == "shop/cart.py" and own[0]["document_id"] == doc["id"]
    assert "Documentation generated from this file" in e["prompt"]


def test_cc07_related_docs_must_share_enough_with_the_change():
    docs = entity(context(), "get_cart_total")["docs"]
    names = [d["name"] for d in docs]
    assert "Discounts" in names and "Currencies" in names      # discount removed, currency added
    assert "Deployment" not in names
    assert entity(context(), "_audit")["docs"] == []


# ---------- CC-08 .. CC-10: limits and the prompt ----------

def test_cc08_k_limits_and_zero():
    e = entity(context(k_code=1, k_docs=1), "get_cart_total")
    assert len(e["code"]) == 1 and len([d for d in e["docs"] if d["relation"] == "related"]) <= 1
    e = entity(context(k_code=0, k_docs=0), "get_cart_total")
    assert e["code"] == [] and e["docs"] == []
    assert client.post("/drift/context", json=body(k_code=11)).status_code == 422


def test_cc09_prompt_cites_every_item_once():
    e = entity(context(), "get_cart_total")
    p = e["prompt"]
    assert p.startswith("Changed code: function `get_cart_total` in shop/cart.py changed its signature.")
    assert "Before: get_cart_total(cart_id: int, discount: float) -> float" in p
    assert "X1: diff (shop/cart.py:10-15)" in p and "```diff" in p
    refs = re.findall(r"^- ([CD]\d+) \[", p, re.M)
    assert sorted(refs) == sorted(i["ref"] for i in e["code"] + e["docs"])
    assert [i["ref"] for i in e["code"]] == [f"C{n}" for n in range(1, len(e["code"]) + 1)]


def test_cc10_long_diff_is_truncated():
    lines = "\n".join(f"+    x{i} = {i}" for i in range(100))
    patch = f"@@ -10,1 +10,101 @@\n def get_cart_total(cart_id: int, currency: str) -> float:\n{lines}\n"
    after = {**AFTER, "functions": [{**AFTER["functions"][0], "end_lineno": 110}]}
    data = context(files=[{"path": "shop/cart.py", "patch": patch, "before": BEFORE, "after": after}])
    d = entity(data, "get_cart_total")["diff"]
    assert len(d["lines"]) == MAX_DIFF_LINES and d["truncated"] is True and d["added"] == 100
    assert "... (diff truncated)" in entity(data, "get_cart_total")["prompt"]


# ---------- CC-11 .. CC-13: other inputs ----------

def test_cc11_patch_only_change_still_gets_diff_and_docs():
    data = context(files=[{"path": "shop/cart.py", "patch": PATCH}])
    e = entity(data, "get_cart_total")
    assert e["diff"] and any(x.startswith("+") for x in e["diff"]["lines"])
    assert any(c["name"] == "checkout" and c["relation"] == "caller" for c in e["code"])


def test_cc12_removed_file_is_not_indexed():
    removed = {"path": "shop/rates.py", "status": "removed",
               "patch": "@@ -1,4 +0,0 @@\n-def convert(amount, currency):\n-    return amount\n",
               "before": RATES}
    data = context(files=[{"path": "shop/cart.py", "patch": PATCH, "before": BEFORE, "after": AFTER}, removed])
    assert data["index"]["files"] == 3
    assert all(c["path"] != "shop/rates.py" for e in data["entities"] for c in e["code"])
    gone = entity(data, "convert")
    assert gone["change"] == "removed"


def test_cc13_same_input_same_context_and_no_docs_warning():
    assert context() == context()
    data = context(docs=[])
    assert any("No documentation was given" in w for w in data["warnings"])
    assert all(e["docs"] == [] for e in data["entities"])
