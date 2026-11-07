"""LD-147 - Detect documentation drift (rules DRIFT001 - DRIFT010)."""
from drift.detector import HIGH, MEDIUM

from drift_helpers import find, run


def src(body):
    return {"src/shop.py": body}


# ---------------------------------------------------------------- DRIFT001 removed

def test_removed_function_still_documented_is_high():
    report = run(src("def legacy_checkout(a):\n    pass\n\ndef keep():\n    pass\n"),
                 src("def keep():\n    pass\n"),
                 {"d.md": "Use `legacy_checkout(cart)` for old flows.\n"})
    (e,) = find(report, "DRIFT001")
    assert e.entity == "legacy_checkout" and e.severity == "high" and e.doc.line == 1


def test_common_short_name_is_only_medium_confidence():
    report = run(src("def legacy(a):\n    pass\n"), src("x = 1\n"), {"d.md": "Use `legacy(cart)`.\n"})
    (e,) = find(report, "DRIFT001")
    assert e.severity == "medium"


def test_removed_function_not_mentioned_gives_no_drift():
    report = run(src("def legacy():\n    pass\n"), src("x = 1\n"), {"d.md": "Nothing relevant.\n"})
    assert report.evidence == []


def test_entity_that_still_exists_elsewhere_is_not_reported_as_removed():
    before = {"a.py": "def shared_helper(x):\n    pass\n", "b.py": "def other():\n    pass\n"}
    after = {"a.py": "def other_a():\n    pass\n", "b.py": "def shared_helper(x):\n    pass\n"}
    report = run(before, after, {"d.md": "`shared_helper(x)`\n"})
    assert find(report, "DRIFT001") == []


def test_plain_prose_mention_of_common_word_is_ignored():
    report = run(src("def run():\n    pass\n"), src("x = 1\n"), {"d.md": "We run the tests every day.\n"})
    assert report.evidence == []


# ---------------------------------------------------------------- DRIFT002 renamed

def test_renamed_function_old_name_in_docs():
    before = src("def old_total(x):\n    return x * 2\n")
    after = src("def new_total(x):\n    return x * 2\n")
    report = run(before, after, {"d.md": "Call `old_total(5)`.\nAnd `new_total(5)`.\n"})
    (e,) = find(report, "DRIFT002")
    assert e.doc.line == 1 and "new_total" in e.suggestion


def test_rename_note_mentioning_both_names_is_not_drift():
    before = src("def old_total(x):\n    return x * 2\n")
    after = src("def new_total(x):\n    return x * 2\n")
    report = run(before, after, {"d.md": "`old_total` was renamed to `new_total`.\n"})
    assert report.evidence == []


# ---------------------------------------------------------------- DRIFT003 signature

def test_verbatim_old_signature_in_code_block():
    before = src("class Cart:\n    def add_item(self, item, qty=1):\n        pass\n")
    after = src("class Cart:\n    def add_item(self, item, quantity=1, coupon=None):\n        pass\n")
    doc = "## Cart.add_item\n\n```python\ndef add_item(self, item, qty=1)\n```\n"
    (e,) = find(run(before, after, {"d.md": doc}), "DRIFT003")
    assert e.confidence >= HIGH and "old signature" in e.reasons[0]


def test_documentation_already_updated_in_the_same_pr_is_clean():
    before = src("def add(item, qty=1):\n    pass\n")
    after = src("def add(item, qty=1, coupon=None):\n    pass\n")
    docs = {"d.md": "Call `add(item, qty, coupon)`.\n\n```python\ndef add(item, qty=1, coupon=None)\n```\n"}
    assert find(run(before, after, docs), "DRIFT003") == []


def test_call_example_with_old_parameter_names():
    before = src("def add_item(item, qty):\n    pass\n")
    after = src("def add_item(item, quantity):\n    pass\n")
    (e,) = find(run(before, after, {"d.md": "Run `add_item(item, qty)` now.\n"}), "DRIFT003")
    assert e.severity == "high"


def test_call_example_arity_matches_only_the_old_signature():
    before = src("def connect(host, port):\n    pass\n")
    after = src("def connect(host):\n    pass\n")
    (e,) = find(run(before, after, {"d.md": "`connect('localhost', 80)`\n"}), "DRIFT003")
    assert "old signature" in e.reasons[0]


def test_old_declaration_is_still_flagged_when_only_optional_parameters_are_added():
    before = src("def f(a):\n    pass\n")
    after = src("def f(a, b=1):\n    pass\n")
    (e,) = find(run(before, after, {"d.md": "```python\ndef f(a)\n```\n"}), "DRIFT003")
    assert "old signature" in e.reasons[0]


def test_optional_parameter_may_be_omitted_in_examples():
    before = src("def f(a):\n    pass\n")
    after = src("def f(a, b=1):\n    pass\n")
    assert find(run(before, after, {"d.md": "`f(1)` and `f(a)`\n"}), "DRIFT003") == []


def test_removed_parameter_still_listed_in_section_is_medium():
    before = src("def search(query, limit):\n    pass\n")
    after = src("def search(query):\n    pass\n")
    doc = "## `search`\n\nParameters:\n\n- `query` - text\n- `limit` - max rows\n"
    (e,) = find(run(before, after, {"d.md": doc}), "DRIFT003")
    assert MEDIUM <= e.confidence < HIGH and "limit" in e.reasons[0]


def test_new_parameter_not_documented_is_low():
    before = src("def search(query, limit):\n    pass\n")
    after = src("def search(query, limit, offset):\n    pass\n")
    doc = "## `search`\n\n| name | type |\n|---|---|\n| query | str |\n| limit | int |\n"
    (e,) = find(run(before, after, {"d.md": doc}), "DRIFT003")
    assert e.severity == "low" and "offset" in e.reasons[0]


def test_java_signature_in_docs():
    before = {"A.java": "class A {\n  public Order getOrder(long id) { return null; }\n}\n"}
    after = {"A.java": "class A {\n  public Order getOrder(long id, boolean expand) { return null; }\n}\n"}
    (e,) = find(run(before, after, {"d.md": "Signature: `Order getOrder(long id)`\n"}), "DRIFT003")
    assert e.confidence >= HIGH


# ---------------------------------------------------------------- DRIFT004 return type

def test_return_type_changed():
    before = src("def total(c) -> float:\n    pass\n")
    after = src("def total(c) -> Decimal:\n    pass\n")
    doc = "## `total`\n\nReturns `float`.\n"
    (e,) = find(run(before, after, {"d.md": doc}), "DRIFT004")
    assert "Decimal" in e.suggestion


def test_return_type_documented_correctly_is_clean():
    before = src("def total(c) -> float:\n    pass\n")
    after = src("def total(c) -> Decimal:\n    pass\n")
    assert find(run(before, after, {"d.md": "## `total`\n\nReturns `Decimal`.\n"}), "DRIFT004") == []


# ---------------------------------------------------------------- DRIFT005 routes

ROUTES_BEFORE = src('from f import app\n@app.get("/orders/{id}")\ndef get_order(id):\n    pass\n')


def test_route_path_changed():
    after = src('from f import app\n@app.get("/v2/orders/{id}")\ndef get_order(id):\n    pass\n')
    (e,) = find(run(ROUTES_BEFORE, after, {"d.md": "- `GET /orders/{id}`\n"}), "DRIFT005")
    assert e.severity == "high" and "/v2/orders" in e.suggestion


def test_route_http_method_changed():
    after = src('from f import app\n@app.post("/orders/{id}")\ndef get_order(id):\n    pass\n')
    (e,) = find(run(ROUTES_BEFORE, after, {"d.md": "- `GET /orders/{id}`\n- `POST /orders/{id}`\n"}), "DRIFT005")
    assert e.doc.line == 1


def test_removed_endpoint_still_documented():
    after = src("x = 1\n")
    (e,) = find(run(ROUTES_BEFORE, after, {"d.md": "`GET /orders/:id` returns an order\n"}), "DRIFT005")
    assert "no longer exists" in e.reasons[0]


def test_route_documented_with_new_path_is_clean():
    after = src('from f import app\n@app.get("/v2/orders/{id}")\ndef get_order(id):\n    pass\n')
    assert find(run(ROUTES_BEFORE, after, {"d.md": "`GET /v2/orders/{id}`\n"}), "DRIFT005") == []


def test_spring_class_prefix_change_moves_all_routes():
    before = {"C.java": '@RequestMapping("/api")\nclass C {\n  @GetMapping("/items")\n  List<Item> items() { return null; }\n}\n'}
    after = {"C.java": '@RequestMapping("/api/v2")\nclass C {\n  @GetMapping("/items")\n  List<Item> items() { return null; }\n}\n'}
    (e,) = find(run(before, after, {"d.md": "`GET /api/items`\n"}), "DRIFT005")
    assert e.entity == "C.items"


# ---------------------------------------------------------------- DRIFT006 attributes

def test_class_attribute_removed_but_documented():
    before = src("class Order:\n    id: int\n    legacy_code: str\n")
    after = src("class Order:\n    id: int\n")
    doc = "## `Order`\n\n- `id` - identifier\n- `legacy_code` - old code\n"
    (e,) = find(run(before, after, {"d.md": doc}), "DRIFT006")
    assert "legacy_code" in e.reasons[0]


def test_class_attribute_added_but_undocumented():
    before = src("class Order:\n    order_id: int\n    status: str\n")
    after = src("class Order:\n    order_id: int\n    status: str\n    priority: int\n")
    doc = "## `Order`\n\n- `order_id`\n- `status`\n"
    (e,) = find(run(before, after, {"d.md": doc}), "DRIFT006")
    assert e.severity == "low"


# ---------------------------------------------------------------- DRIFT007/8/10 files

def test_deleted_file_referenced_by_path_and_link():
    report = run({"src/util.py": "x = 1\n"}, {}, {"d.md": "See [util](src/util.py).\n"})
    (e,) = find(report, "DRIFT007")
    assert e.doc.line == 1 and e.severity == "high"


def test_modified_file_reference_is_not_drift():
    report = run({"src/util.py": "x = 1\n"}, {"src/util.py": "x = 2\n"}, {"d.md": "See `src/util.py`.\n"})
    assert report.evidence == []
    assert report.affected_documents[0]["path"] == "d.md"


def test_moved_entity_with_old_path_in_same_section():
    before = {"a.py": "def shared_helper(x):\n    return x\n", "b.py": "y = 1\n"}
    after = {"a.py": "y = 0\n", "b.py": "def shared_helper(x):\n    return x\n"}
    doc = "## Helpers\n\n`shared_helper` lives in `a.py`.\n"
    (e,) = find(run(before, after, {"d.md": doc}), "DRIFT010")
    assert "b.py" in e.suggestion


# ---------------------------------------------------------------- DRIFT009 undocumented endpoint

def test_new_endpoint_missing_from_documentation_that_lists_siblings():
    before = src('from f import app\n@app.get("/orders")\ndef list_orders():\n    pass\n')
    after = before_plus = src('from f import app\n@app.get("/orders")\ndef list_orders():\n    pass\n\n'
                              '@app.post("/orders")\ndef create_order():\n    pass\n')
    (e,) = find(run(before, after, {"api.md": "- `GET /orders`\n"}), "DRIFT009")
    assert e.severity == "low" and e.entity == "create_order"


def test_new_endpoint_in_unrelated_docs_is_ignored():
    before = src("x = 1\n")
    after = src('from f import app\n@app.get("/health")\ndef health():\n    pass\n')
    assert run(before, after, {"d.md": "Nothing about endpoints.\n"}).evidence == []


# ---------------------------------------------------------------- post-processing

def test_removed_class_suppresses_findings_of_its_methods_on_the_same_line():
    before = src("class Cart:\n    def add_item(self, x):\n        pass\n")
    after = src("x = 1\n")
    report = run(before, after, {"d.md": "Use `Cart` and `Cart.add_item(x)`.\n\nSeparately `Cart.add_item`.\n"})
    assert {(e.entity, e.doc.line) for e in report.evidence} == {("Cart", 1), ("Cart.add_item", 3)}


def test_min_confidence_filters_weak_findings():
    before = src("def search(query, limit):\n    pass\n")
    after = src("def search(query, limit, offset):\n    pass\n")
    docs = {"d.md": "## `search`\n\n| name |\n|---|\n| query |\n| limit |\n"}
    assert run(before, after, docs, min_confidence=0.0).evidence
    assert run(before, after, docs, min_confidence=0.6).evidence == []


def test_finding_ids_are_stable_and_unique():
    before = src("def a_func(x):\n    pass\n\ndef b_func(x):\n    pass\n")
    after = src("x = 1\n")
    docs = {"d.md": "`a_func`\n\n`b_func`\n"}
    ids1 = [e.id for e in run(before, after, docs).evidence]
    ids2 = [e.id for e in run(before, after, docs).evidence]
    assert ids1 == ids2 and len(set(ids1)) == 2
