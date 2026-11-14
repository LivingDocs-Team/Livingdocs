"""LD-353: documentation update suggestions (POST /suggestions/updates).

Cases SG-xx of Docs/Linh/LD-353-Documentation-Update-Suggestions.md. Input: the drift fixture
(shop/cart.py before / after a Pull Request), a saved document generated from the old code and
the repository README.
"""
import json
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline generator

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import suggestions as sg  # noqa: E402
from drift_fixtures import AFTER, BEFORE, PATCH, PR, README  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def saved_document(lang="vi", files=(BEFORE,)):
    r = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                       "output_language": lang, "files": list(files)})
    r = client.post("/documents", json={"job_id": r.json()["id"], "actor": "tester"})
    assert r.status_code == 201, r.text
    return r.json()


def body(doc_ids, **extra):
    data = {"repository": "acme/shop", "pull_request": PR,
            "files": [{"path": "shop/cart.py", "patch": PATCH, "before": BEFORE, "after": AFTER}],
            "docs": [README], "document_ids": doc_ids}
    data.update(extra)
    return data


def suggest(doc_ids, **extra):
    r = client.post("/suggestions/updates", json=body(doc_ids, **extra))
    assert r.status_code == 201, r.text
    return r.json()


def about(batch, entity, path="shop/cart.py"):
    return next(s for s in batch["suggestions"] if entity in s["entities"] and s["target"]["path"] == path)


@pytest.fixture(scope="module")
def doc():
    return saved_document()


@pytest.fixture(scope="module")
def batch(doc):
    return suggest([doc["id"]])


# ---------- SG-01: API ----------

def test_sg01_batch_is_kept_and_can_be_read(batch, doc):
    assert batch["source"] == "code_change" and batch["pull_request"]["number"] == 42
    assert all(s["status"] == "pending" and s["batch_id"] == batch["id"] for s in batch["suggestions"])
    assert client.get(f"/suggestions/batches/{batch['id']}").json() == batch
    listed = client.get("/suggestions", params={"batch_id": batch["id"]}).json()
    assert {s["id"] for s in listed} == {s["id"] for s in batch["suggestions"]}
    one = batch["suggestions"][0]
    assert client.get(f"/suggestions/{one['id']}").json() == one
    by_doc = client.get("/suggestions", params={"document_id": doc["id"], "batch_id": batch["id"]}).json()
    assert by_doc and all(s["target"]["document_id"] == doc["id"] for s in by_doc)
    assert client.get("/suggestions/nope").status_code == 404
    assert client.get("/suggestions/batches/nope").status_code == 404


# ---------- SG-02 .. SG-08: the rules ----------

def test_sg02_renamed_function_is_renamed_everywhere_in_its_section(batch):
    s = about(batch, "count_cart_items")
    assert s["operation"] == "replace" and s["confidence"] == 0.9 and s["method"] == "rule"
    assert "### `count_items`" in s["original"] and "### `count_cart_items`" in s["proposed"]
    assert "count_cart_items(cart_id)" in s["proposed"] and "count_items" not in s["proposed"]
    assert s["reasons"] == ["`count_items` was renamed to `count_cart_items`"]


def test_sg03_signature_change_updates_call_and_parameter_table(batch):
    s = about(batch, "get_cart_total")
    p = s["proposed"]
    assert "get_cart_total(cart_id, currency)" in p and "discount" not in p
    assert "| `cart_id` | int | - | - |" in p and "| `currency` | str | - | - |" in p
    assert p.index("`cart_id`") < p.index("`currency`")
    assert s["changes"] == ["signature_changed"] and s["evidence"] == ["X1 shop/cart.py:10-15"]
    assert "-| `discount` | float | - | - |" in s["diff"] and "+| `currency` | str | - | - |" in s["diff"]


def test_sg04_removed_entity_section_is_deleted(batch):
    s = about(batch, "clear_cart")
    assert s["operation"] == "delete" and s["proposed"] == "" and s["confidence"] == 0.85
    assert s["original"].startswith("### `clear_cart`")
    ep = about(batch, "DELETE /carts/{id}")
    assert ep["operation"] == "delete" and ep["original"].startswith("### `DELETE /carts/{id}`")


def test_sg05_repository_markdown_rename_and_removed_mention(batch):
    s = about(batch, "GET /api/carts/{id}", "README.md")
    assert s["target"]["source"] == "repository" and s["target"]["document_id"] is None
    assert "`GET /api/carts/{id}`" in s["proposed"] and "/carts/:id" not in s["proposed"]
    assert "clear_cart" not in s["proposed"] and "We add items to a cart." in s["proposed"]
    assert s["confidence"] == 0.5                  # deleting a line of free text is uncertain
    ep = about(batch, "GET /api/carts/{id}")
    assert "### `GET /api/carts/{id}`" in ep["proposed"]


def test_sg06_new_function_gets_a_section_after_the_other_functions(batch):
    s = about(batch, "apply_coupon")
    assert s["operation"] == "insert"
    # same passage: fetch_cart's docstring update + the new section after it
    added = s["proposed"].split("> Độ tin cậy: **0.40 (thấp)** · Bằng chứng: `shop/cart.py:27-28`", 1)[1]
    assert "\n### `apply_coupon`\n" in added and "apply_coupon(code)" in added
    assert "**Tham số**" in added and "| `code` | str | - | - |" in added
    assert "Mới thêm (PR #42)" in added
    assert "### `fetch_cart`" in s["original"]       # last function section of the document


def test_sg06b_english_document_gets_english_section():
    en = saved_document("en")
    s = about(suggest([en["id"]], docs=[]), "apply_coupon")
    assert "**Parameters**" in s["proposed"] and "No description. (PR #42)" in s["proposed"]


def test_sg07_new_method_goes_under_its_class():
    after = {**AFTER, "classes": [{**AFTER["classes"][0], "methods": AFTER["classes"][0]["methods"] + [
        {"name": "remove", "parameters": [{"name": "item"}], "lineno": 34, "end_lineno": 36}]}]}
    d = saved_document()
    b = suggest([d["id"]], docs=[], files=[{"path": "shop/cart.py", "before": BEFORE, "after": after}])
    s = about(b, "Cart.remove")
    assert "#### `add`" in s["original"] and "\n#### `remove`\n" in s["proposed"]


def test_sg08_behaviour_change_needs_review_unless_docstring_changed(batch):
    s = about(batch, "Cart.add")
    assert s["operation"] == "review" and s["proposed"] is None and s["method"] == "none"
    assert s["diff"] == "" and "behaviour changed" in s["reasons"][0]
    f = about(batch, "fetch_cart")
    assert "Load a cart from the cache first." in f["proposed"] and "the docstring changed" in f["reasons"]


# ---------- SG-09: suggestions point at real text ----------

def test_sg09_original_is_the_exact_text_of_the_target_lines(batch, doc):
    section = next(s for s in client.get(f"/documents/{doc['id']}/versions/1").json()["sections"]
                   if s["path"] == "shop/cart.py")["markdown"].split("\n")
    readme = README["content"].split("\n")
    for s in batch["suggestions"]:
        lines = section if s["target"]["source"] == "document" else readme
        t = s["target"]
        assert s["original"] == "\n".join(lines[t["line_start"] - 1:t["line_end"]])
        assert t["version"] == (1 if t["document_id"] else None)
    assert all(s["diff"].startswith(f"--- a/{s['target']['path']}") for s in batch["suggestions"] if s["diff"])


def test_sg10_parameter_rename_retype_and_return_type():
    before = {"path": "shop/tax.py", "language": "python", "functions": [
        {"name": "vat", "parameters": [{"name": "amount", "type": "int"}, {"name": "rate", "type": "float"}],
         "return_type": "int", "lineno": 1, "end_lineno": 3}]}
    after = {"path": "shop/tax.py", "language": "python", "functions": [
        {"name": "vat", "parameters": [{"name": "value", "type": "int"}, {"name": "rate", "type": "Decimal"}],
         "return_type": "Decimal", "lineno": 1, "end_lineno": 3}]}
    d = saved_document("en", [before])
    b = suggest([d["id"]], docs=[], files=[{"path": "shop/tax.py", "before": before, "after": after}])
    p = about(b, "vat", "shop/tax.py")["proposed"]
    assert "vat(value, rate)" in p and "| `value` | int |" in p and "| `rate` | Decimal |" in p
    assert "**Returns:** `Decimal`" in p


# ---------- SG-11: the AI ----------

class FakeAI:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def complete(self, system, messages):
        self.prompts.append(messages[-1]["content"])
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer(messages[-1]["content"]) if callable(self.answer) else self.answer


def with_ai(monkeypatch, doc, answer, **extra):
    fake = FakeAI(answer)
    monkeypatch.setattr(sg, "get_client", lambda use_ai=True: fake if use_ai else None)
    return suggest([doc["id"]], **extra), fake


def test_sg11_ai_rewrites_from_the_change_context(monkeypatch, doc):
    def answer(prompt):
        return json.dumps({"proposed": "### `rewritten`\n\nBy the AI.", "reason": "AI reason"})
    b, fake = with_ai(monkeypatch, doc, answer)
    s = about(b, "get_cart_total")
    assert s["method"] == "ai" and s["proposed"] == "### `rewritten`\n\nBy the AI." and s["confidence"] == 0.75
    assert "AI reason" in s["reasons"]
    review = about(b, "Cart.add")
    assert review["operation"] == "replace" and review["method"] == "ai"     # AI wrote the text
    assert about(b, "clear_cart")["method"] == "rule"                        # deletes stay rules
    p = next(x for x in fake.prompts if "get_cart_total(cart_id, discount)" in x)
    assert "X1: diff" in p and "Mechanical update" in p and "get_cart_total(cart_id, currency)" in p


@pytest.mark.parametrize("answer", ["not json", json.dumps({"proposed": ""}), RuntimeError("API down")])
def test_sg11b_bad_ai_answer_keeps_the_rule_result(monkeypatch, doc, answer):
    b, _ = with_ai(monkeypatch, doc, answer)
    s = about(b, "get_cart_total")
    assert s["method"] == "rule" and "get_cart_total(cart_id, currency)" in s["proposed"]


def test_sg11c_use_ai_false_does_not_call_it(monkeypatch, doc):
    b, fake = with_ai(monkeypatch, doc, "x", use_ai=False)
    assert fake.prompts == [] and all(s["method"] != "ai" for s in b["suggestions"])


# ---------- SG-12: nothing to suggest ----------

def test_sg12_warnings_when_nothing_to_suggest():
    b = suggest([], docs=[])
    assert b["suggestions"] == [] and any("No documentation was given" in w for w in b["warnings"])
    b = suggest([], docs=[{"path": "docs/other.md", "content": "# Other\n\nNothing about carts.\n"}])
    assert b["suggestions"] == [] and any("No documentation passage needs to change" in w for w in b["warnings"])
    assert client.post("/suggestions/updates", json=body([], output_language="fr")).status_code == 422
