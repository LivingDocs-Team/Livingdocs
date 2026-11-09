"""LD-155 Test drift classification (LD-151).

LD-152 referential, LD-153 signature, LD-154 semantic: the `kind` inside each drift type,
`breaking`, severity rules and the documentation passages that still state the old code.
"""
import difflib

import pytest

from app.drift import DRIFT_KINDS, analyze
from app.drift_affected import DocText
from app.drift_changes import analyze_file, parse_patch
from app.drift_models import ChangedFile, DocSource, DriftAnalyzeRequest
from app.drift_referential import line_map, module_of, stale_line_refs
from app.drift_semantic import extract_signals, status_codes_of, values_of, without_renames
from app.drift_signature import parameter_changes
from app.versions import DocumentStore
from drift_fixtures import AFTER, BEFORE, PATCH, PR

PR3 = {"number": 3, "title": "LD-152 orders", "head_branch": "ld-153-orders"}


def report(files, docs):
    req = DriftAnalyzeRequest(repository="acme/shop", pull_request=PR3, files=files,
                              docs=[{"path": p, "content": c} for p, c in docs], document_ids=[])
    return analyze(req, DocumentStore(None))


def only(r, kind=None, entity=None, type_=None):
    out = [f for f in r.findings if (kind is None or f.kind == kind)
           and (entity is None or f.entity == entity) and (type_ is None or f.type.value == type_)]
    assert len(out) == 1, [(f.type.value, f.kind, f.entity) for f in r.findings]
    return out[0]


def diff(old, new):
    return "\n".join(list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                               lineterm="", n=3))[2:])


def fn(name, params, ret=None, source=None, doc=None, line=1, end=None):
    return {"name": name, "parameters": [dict(zip(("name", "type", "default"), p)) for p in params],
            "return_type": ret, "source": source, "docstring": doc, "lineno": line,
            "end_lineno": end or line + 3}


def analysis(path="shop/orders.py", functions=(), endpoints=(), classes=()):
    return {"path": path, "language": "python", "status": "ok", "functions": list(functions),
            "endpoints": list(endpoints), "classes": list(classes)}


# ====================== LD-152 referential ======================

def test_module_names_of_python_and_java_files():
    assert module_of("shop/cart.py") == "shop.cart"
    assert module_of("src/shop/orders/__init__.py") == "shop.orders"
    assert module_of("services/x/src/main/java/com/acme/Order.java") == "com.acme.Order"
    assert module_of("cart.py") is None                 # one word: too common to search
    assert module_of("web/app.js") is None


def test_moved_file_still_named_by_module_and_path():
    r = report([ChangedFile(path="shop/basket.py", previous_path="shop/cart.py", status="renamed")],
               [("docs/dev.md", "Import it with `from shop.cart import Cart`.\n"),
                ("README.md", "Code: [cart](shop/cart.py).\n")])
    mod = only(r, kind="module_moved")
    assert (mod.before, mod.after) == ("shop.cart", "shop.basket")
    assert mod.document.path == "docs/dev.md" and mod.severity.value == "medium" and mod.breaking
    assert mod.document.matches[0].kind == "module"
    path = only(r, kind="file_moved")
    assert path.document.path == "README.md" and path.after == "shop/basket.py"


def test_deleted_file_named_by_module():
    r = report([ChangedFile(path="src/main/java/com/acme/Legacy.java", status="removed")],
               [("docs/arch.md", "The `com.acme.Legacy` adapter talks to the old API.\n")])
    f = only(r, kind="module_removed")
    assert f.type.value == "referential" and f.severity.value == "medium"
    assert "`com.acme.Legacy`" in f.message


def test_line_map_shifts_and_changed_lines():
    patch = "@@ -3,3 +3,4 @@\n a\n-b\n+B\n+C\n d\n@@ -20,2 +21,1 @@\n x\n-y\n"
    new_line = line_map(parse_patch(patch))
    assert new_line(1) == 1                 # before the first hunk
    assert new_line(3) == 3 and new_line(5) == 6      # context inside the hunk, mapped exactly
    assert new_line(4) is None              # changed
    assert new_line(10) == 11               # between hunks: +1
    assert new_line(21) is None and new_line(30) == 30  # after the second hunk: +1 -1


def test_stale_line_references():
    patch = "@@ -3,3 +3,4 @@\n a\n-b\n+B\n+C\n d\n"
    doc = DocText(DocSource.repository, "x.md",
                  "See `shop/a.py:1-2` (ok), `shop/a.py:10-12` (shifted),\n"
                  "`shop/a.py#L4` (changed) and shop/a.py#L8-L9.\n")
    refs = stale_line_refs(doc, "shop/a.py", "shop/a.py", parse_patch(patch))
    assert [(m.term, m.note) for m in refs] == [
        ("shop/a.py:10-12", "now shop/a.py:11-13"),
        ("shop/a.py#L4", "line 4 was changed by the Pull Request"),
        ("shop/a.py#L8-L9", "now shop/a.py:9-10")]
    assert all(m.kind == "line_ref" for m in refs)


def test_line_reference_finding_severity():
    old = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
    shifted = "# header\n" + old
    r = report([ChangedFile(path="shop/m.py", patch=diff(old, shifted))],
               [("docs/m.md", "`b` is at `shop/m.py:5-6`.\n")])
    f = only(r, kind="line_reference_stale")
    assert f.severity.value == "low" and not f.breaking
    assert "now shop/m.py:6-7" in f.message and f.entity is None

    changed = old.replace("return 2", "return 3")
    r = report([ChangedFile(path="shop/m.py", patch=diff(old, changed))],
               [("docs/m.md", "`b` is at `shop/m.py:5-6`.\n")])
    assert only(r, kind="line_reference_stale").severity.value == "medium"
    r = report([ChangedFile(path="shop/m.py", patch=diff(old, changed))],
               [("docs/m.md", "`a` is at `shop/m.py:1-2`.\n")])
    assert not [f for f in r.findings if f.kind == "line_reference_stale"]


def test_referential_kinds_of_entities_and_endpoints():
    r = report([ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER)],
               [("README.md", "`clear_cart`, `count_items`, `DELETE /carts/{id}`, `GET /carts/{id}`\n")])
    kinds = {f.entity: f.kind for f in r.findings if f.type.value == "referential"}
    assert kinds == {"clear_cart": "entity_removed", "count_cart_items": "entity_renamed",
                     "DELETE /carts/{id}": "endpoint_removed", "GET /api/carts/{id}": "endpoint_moved"}
    assert all(f.breaking for f in r.findings if f.type.value == "referential")


# ====================== LD-153 signature ======================

def test_parameter_changes():
    def kinds(old, new):
        return [(c.change.value, c.name, c.breaking) for c in parameter_changes(old, new)]

    assert kinds([("a", "int", None), ("b", "str", None)], [("a", "int", None), ("c", "str", None)]) \
        == [("renamed", "c", True)]                                        # same position and type
    assert kinds([("a", "int", None), ("b", "float", None)], [("a", "int", None), ("c", "str", None)]) \
        == [("removed", "b", True), ("added", "c", True)]                  # other type: not a rename
    assert kinds([("a", None, None)], [("a", None, None), ("b", "int", "0")]) == [("added", "b", False)]
    assert kinds([("a", None, None)], [("a", None, None), ("*args", None, None)]) == [("added", "args", False)]
    assert kinds([("a", "int", None)], [("a", "str", None)]) == [("type_changed", "a", True)]
    assert kinds([("a", None, "1")], [("a", None, None)]) == [("default_removed", "a", True)]
    assert kinds([("a", None, None)], [("a", None, "1")]) == [("default_added", "a", False)]
    assert kinds([("a", None, "1")], [("a", None, "2")]) == [("default_changed", "a", False)]
    assert kinds([("a", None, None), ("b", None, None)], [("b", None, None), ("a", None, None)]) \
        == [("reordered", "b, a", True)]
    assert kinds([("a", None, None)], [("a", None, None), ("*", None, None)]) == []   # bare `*`


def test_endpoint_http_method_change_is_a_signature_drift():
    before = analysis(endpoints=[{"http_method": "GET", "path": "/orders/{id}", "handler": "get_order"}])
    after = analysis(endpoints=[{"http_method": "POST", "path": "/orders/{order_id}", "handler": "get_order"}])
    s = analyze_file(ChangedFile(path="shop/orders.py", before=before, after=after))
    [c] = s.entity_changes
    assert (c.change.value, c.name, c.old_name) == ("signature_changed", "POST /orders/{order_id}", "GET /orders/{id}")
    assert c.aspects == ["http_method"] and c.breaking

    r = report([ChangedFile(path="shop/orders.py", before=before, after=after)],
               [("docs/api.md", "Call `GET /orders/{id}` to read an order.\n")])
    f = only(r, kind="endpoint_method_changed")
    assert f.type.value == "signature" and f.severity.value == "high" and f.breaking
    assert "HTTP method: GET -> POST" in f.message


def test_endpoint_method_change_in_java_diff():
    patch = """@@ -10,4 +10,4 @@ public class OrderController {
-    @GetMapping("/orders/{id}/cancel")
+    @PostMapping("/orders/{id}/cancel")
     public void cancel(@PathVariable Long id) {
         service.cancel(id);
     }
"""
    s = analyze_file(ChangedFile(path="src/OrderController.java", patch=patch))
    c = next(c for c in s.entity_changes if c.kind == "endpoint")
    assert (c.change.value, c.old_name, c.name) == ("signature_changed", "GET /orders/{id}/cancel",
                                                    "POST /orders/{id}/cancel")
    assert c.source == "patch" and c.breaking


def test_optional_parameter_is_not_breaking():
    before = analysis(functions=[fn("list_orders", [("page", "int", None)], "list")])
    after = analysis(functions=[fn("list_orders", [("page", "int", None), ("size", "int", "20")], "list")])
    r = report([ChangedFile(path="shop/orders.py", before=before, after=after)],
               [("docs/api.md", "`list_orders(page)` lists orders.\n")])
    f = only(r, entity="list_orders")
    assert (f.kind, f.breaking, f.severity.value) == ("parameter_added", False, "low")
    assert f.rules[0] == "not breaking: low"


def test_documented_old_type_and_default_raise_severity():
    before = analysis(functions=[fn("get_order", [("order_id", "int", None), ("verbose", "bool", "False")], "dict")])
    after = analysis(functions=[fn("get_order", [("order_id", "str", None), ("verbose", "bool", "True")], "dict")])
    doc = ("### `get_order`\n\n| Name | Type | Default |\n|---|---|---|\n"
           "| `order_id` | int | - |\n| `verbose` | bool | False |\n")
    r = report([ChangedFile(path="shop/orders.py", before=before, after=after)], [("docs/api.md", doc)])
    f = only(r, entity="get_order")
    assert (f.kind, f.breaking, f.severity.value) == ("parameter_type_changed", True, "high")
    shown = {(m.kind, m.term, m.line) for m in f.document.matches if m.kind != "name"}
    assert shown == {("type", "order_id int", 5), ("default", "verbose False", 6)}
    assert "documentation still states the old detail: +1" in f.rules
    assert {e.line_start for e in f.evidence if e.kind.value == "documentation"} >= {5, 6}


def test_return_type_change():
    before = analysis(functions=[fn("total", [("cart_id", "int", None)], "float")])
    after = analysis(functions=[fn("total", [("cart_id", "int", None)], "Decimal")])
    s = analyze_file(ChangedFile(path="shop/orders.py", before=before, after=after))
    [c] = s.entity_changes
    assert (c.old_return_type, c.new_return_type, c.aspects) == ("float", "Decimal", ["return_type"])
    r = report([ChangedFile(path="shop/orders.py", before=before, after=after)],
               [("docs/api.md", "`total(cart_id)` returns a float.\n")])
    assert only(r, entity="total").kind == "return_type_changed"


def test_class_field_change_is_class_contract():
    before = analysis(classes=[{"name": "Order", "fields": [{"name": "id", "type": "int"},
                                                            {"name": "note", "type": "str"}]}])
    after = analysis(classes=[{"name": "Order", "fields": [{"name": "id", "type": "int"}]}])
    r = report([ChangedFile(path="shop/orders.py", before=before, after=after)],
               [("docs/model.md", "`Order` has `id` and `note`.\n")])
    f = only(r, entity="Order")
    assert (f.kind, f.breaking) == ("class_contract_changed", True)


# ====================== LD-154 semantic ======================

def test_signals_from_code():
    old = '''def f(x):
    """Old text."""
    # timeout 99 in a comment is ignored
    if x is None:
        raise HTTPException(status_code=404)
    if x < 0:
        raise ValueError("negative")
    return {"timeout": 30, "mode": "fast", "n": 1}
'''
    new = old.replace("404", "410").replace("ValueError", "LookupError").replace("30", "60") \
        .replace("Old text.", "New text.")
    got = {s.kind: (s.removed, s.added) for s in extract_signals(old, new)}
    assert got["status_codes"] == (["404"], ["410"])
    assert got["exceptions"] == (["ValueError"], ["LookupError"])
    assert got["values"] == (["30"], ["60"])               # not 99 (comment), not 1 (trivial)
    assert got["docstring"] == (["Old text."], ["New text."])
    assert status_codes_of("ResponseEntity.status(HttpStatus.NOT_FOUND)") == {"404"}
    assert status_codes_of("raise HTTPException(status.HTTP_409_CONFLICT)") == {"409"}
    assert values_of("x = 'ab' + '--' + \"VND\"", set()) == {"ab", "VND"}   # punctuation only: no
    assert extract_signals("void f() throws IOException {", "void f() {")[0].removed == ["IOException"]


def test_value_changes_that_follow_a_rename_are_ignored():
    sig = extract_signals('raise ValueError("quantity must be positive")',
                          'raise ValueError("qty must be positive")')
    assert without_renames(sig, [("quantity", "qty")]) == []


def test_status_code_change_with_stale_documentation():
    src = 'def get_order(order_id: int) -> dict:\n    raise HTTPException(status_code={})\n'
    before = analysis(functions=[fn("get_order", [("order_id", "int", None)], "dict", src.format(404))])
    after = analysis(functions=[fn("get_order", [("order_id", "int", None)], "dict", src.format(410))])
    doc = "### `get_order`\n\nReturns `404` when the order does not exist.\n"
    r = report([ChangedFile(path="shop/orders.py", before=before, after=after)], [("docs/api.md", doc)])
    f = only(r, entity="get_order")
    assert (f.type.value, f.kind, f.severity.value, f.breaking) == ("semantic", "status_codes_changed",
                                                                    "high", True)
    assert [(m.kind, m.term, m.line) for m in f.document.matches if m.kind != "name"] == [
        ("status_code", "404", 3)]
    assert f.factors["certainty"] == 0.9 and f.confidence_level == "high"
    assert any(e.excerpt == "Returns `404` when the order does not exist." for e in f.evidence)


def test_value_change_and_quoted_docstring():
    src = 'def connect(host: str) -> None:\n    """{}"""\n    open(host, timeout={})\n'
    old_doc, new_doc = "Opens a connection that times out quickly.", "Opens a connection with a long timeout."
    before = analysis(functions=[fn("connect", [("host", "str", None)], "None", src.format(old_doc, 30), old_doc)])
    after = analysis(functions=[fn("connect", [("host", "str", None)], "None", src.format(new_doc, 120), new_doc)])
    doc = "## `connect`\n\nOpens a connection that times out quickly.\nThe timeout is 30 seconds.\n"
    r = report([ChangedFile(path="shop/orders.py", before=before, after=after)], [("docs/net.md", doc)])
    f = only(r, entity="connect")
    assert f.kind == "values_changed" and f.severity.value == "high"   # docstring +1, stale text +1
    assert {(m.kind, m.line) for m in f.document.matches if m.kind != "name"} == {("docstring", 3),
                                                                                 ("value", 4)}


def test_body_change_without_signals_is_implementation_changed():
    r = report([ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER)],
               [("docs/cart.md", "`Cart.add` appends an item.\n")])
    f = only(r, entity="Cart.add")
    assert (f.kind, f.severity.value, f.breaking) == ("implementation_changed", "low", False)


def test_signature_and_behaviour_change_give_two_findings():
    old = ('@app.get("/orders/{order_id}")\n'
           'def get_order(order_id: int) -> dict:\n'
           '    raise HTTPException(status_code=404)\n')
    new = old.replace("order_id: int", "order_id: str").replace("404", "410")
    r = report([ChangedFile(path="shop/orders.py", patch=diff(old, new))],
               [("docs/api.md", "`get_order(order_id: int)` returns 404 for unknown orders.\n")])
    kinds = sorted((f.type.value, f.kind) for f in r.findings if f.entity == "get_order")
    assert kinds == [("semantic", "status_codes_changed"), ("signature", "parameter_type_changed")]


def test_undocumented_entity_kind():
    r = report([ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER)], [])
    assert all(f.kind == "undocumented_entity" for f in r.findings if f.change == "added")


# ====================== report ======================

def test_every_finding_has_a_known_kind_rules_and_summary():
    r = report([ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER)],
               [("README.md", "`clear_cart`, `get_cart_total(cart_id, discount)`, see `shop/cart.py:16-18`.\n")])
    assert r.findings
    for f in r.findings:
        assert f.kind in DRIFT_KINDS[f.type.value] and f.rules
    assert sum(r.summary.by_kind.values()) == r.summary.findings
    assert r.summary.breaking == sum(1 for f in r.findings if f.breaking)
    assert list(r.summary.by_kind) == [k for t in ("referential", "signature", "semantic")
                                       for k in DRIFT_KINDS[t] if k in r.summary.by_kind]


@pytest.mark.parametrize("kind_list", list(DRIFT_KINDS.values()))
def test_kind_lists_have_no_duplicates(kind_list):
    assert len(kind_list) == len(set(kind_list))
