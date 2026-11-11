"""LD-127 Test affected documentation detection (LD-122): POST /internal/affected-documents.

A saved document of `acme/shop` documents shop/cart.py and shop/checkout.py; the checkout part
names `get_cart_total` from shop/cart.py. Source changes are in the LD-116 format.
"""
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline generator

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from drift_fixtures import BEFORE  # noqa: E402

client = TestClient(app)
SECRET = "affected-docs-internal-secret"
AUTH = {"Authorization": f"Bearer {SECRET}"}
CHECKOUT = {
    "path": "shop/checkout.py", "language": "python", "status": "ok",
    "functions": [{"name": "checkout", "parameters": [{"name": "cart_id", "type": "int"}],
                   "docstring": "Charge the customer get_cart_total(cart_id) of the cart.",
                   "lineno": 1, "end_lineno": 4}],
}


@pytest.fixture(autouse=True)
def internal_secret(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)


@pytest.fixture(scope="module")
def shop_doc():
    r = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                       "output_language": "en", "files": [BEFORE, CHECKOUT]})
    assert r.status_code == 202
    r = client.post("/documents", json={"job_id": r.json()["id"], "actor": "tester"})
    assert r.status_code == 201, r.text
    return r.json()


def find(doc_ids, *files):
    r = client.post("/internal/affected-documents", headers=AUTH,
                    json={"repository": "acme/shop", "files": list(files), "document_ids": doc_ids})
    assert r.status_code == 200, r.text
    return r.json()


def parts(result):
    return {p["path"]: p for p in result["documents"]}


def test_changed_entity_affects_its_own_part_directly_and_parts_that_name_it(shop_doc):
    result = find([shop_doc["id"]], {
        "path": "shop/cart.py", "change": "MODIFIED", "language": "python",
        "entities": [{"kind": "FUNCTION", "name": "get_cart_total", "change": "MODIFIED"}]})

    got = parts(result)
    assert set(got) == {"shop/cart.py", "shop/checkout.py"}
    own, other = got["shop/cart.py"], got["shop/checkout.py"]
    assert own["dependency"] == "direct"
    assert own["reasons"][0] == "documents changed file shop/cart.py"
    assert own["document_id"] == shop_doc["id"] and own["title"] == shop_doc["title"]
    assert own["version"] == 1 and own["documents_file"] == "shop/cart.py"
    assert other["dependency"] == "dependent"
    assert other["reasons"] == ["mentions `get_cart_total`"]
    assert other["matches"] and "get_cart_total" in other["matches"][0]["excerpt"]
    assert [p["dependency"] for p in result["documents"]] == ["direct", "dependent"]  # direct first


def test_modified_file_without_known_entities_still_affects_its_own_part(shop_doc):
    # e.g. LD-116 skipped the file (PATCH_UNAVAILABLE, FILE_TOO_LARGE, NOT_ANALYZED)
    got = parts(find([shop_doc["id"]], {"path": "shop/checkout.py", "change": "MODIFIED"}))
    assert set(got) == {"shop/checkout.py"}
    assert got["shop/checkout.py"]["dependency"] == "direct"
    assert got["shop/checkout.py"]["reasons"] == ["documents changed file shop/checkout.py"]


@pytest.mark.parametrize("change", [
    {"path": "shop/cart.py", "change": "REMOVED"},
    {"path": "shop/basket.py", "previous_path": "shop/cart.py", "change": "renamed"},
])
def test_removed_or_renamed_file_affects_its_own_part(shop_doc, change):
    got = parts(find([shop_doc["id"]], change))
    assert got["shop/cart.py"]["dependency"] == "direct"


def test_added_entity_in_new_file_and_unrelated_change_affect_nothing(shop_doc):
    result = find([shop_doc["id"]],
                  {"path": "shop/coupons.py", "change": "ADDED",
                   "entities": [{"kind": "FUNCTION", "name": "apply_coupon", "change": "ADDED"}]},
                  {"path": "shop/shipping.py", "change": "MODIFIED",
                   "entities": [{"kind": "FUNCTION", "name": "ship_order", "change": "REMOVED"}]})
    assert result["documents"] == []


def test_only_the_given_documents_are_checked(shop_doc):
    change = {"path": "shop/cart.py", "change": "REMOVED"}
    assert find([], change) == {"documents": [], "warnings": []}
    result = find(["nope"], change)
    assert result["documents"] == []
    assert result["warnings"] == ["Document 'nope' not found; it was not checked."]


def test_internal_credential_is_required(monkeypatch):
    body = {"files": [{"path": "a.py", "change": "MODIFIED"}]}
    assert client.post("/internal/affected-documents", json=body).status_code == 401
    assert client.post("/internal/affected-documents", json=body,
                       headers={"Authorization": "Bearer wrong"}).status_code == 401
    monkeypatch.delenv("INTERNAL_API_SECRET")
    assert client.post("/internal/affected-documents", json=body, headers=AUTH).status_code == 503


@pytest.mark.parametrize("files", [
    [],
    [{"path": "a.py", "change": "COPIED"}],
    [{"path": "a.py", "change": "MODIFIED",
      "entities": [{"kind": "FUNCTION", "name": "f", "change": "RENAMED"}]}],
])
def test_invalid_source_change_is_rejected(files):
    r = client.post("/internal/affected-documents", headers=AUTH, json={"files": files})
    assert r.status_code == 422
