"""LD-148 - Identify affected documentation."""
from drift.affected import identify_affected_documentation
from drift.doc_scanner import build_index, filter_doc_paths, is_distinctive
from drift.pr_analyzer import analyze_pull_request

from drift_helpers import make_diff, readers


def affected(before, after, docs):
    old, new = readers(before, after)
    analysis = analyze_pull_request(make_diff(before, after), old, new)
    return identify_affected_documentation(build_index(docs), analysis)


DOC = """# Title

Intro mentions Cart in plain prose only.

## `Cart.add_item`

Use `cart.add_item(item)` or `add_item`.

```python
total = calculate_total(cart)
```

- `GET /api/orders/{id}` - one order
"""


def test_reference_contexts_are_classified():
    index = build_index({"d.md": DOC})
    kinds = {r.kind for r in index.find_name("calculate_total")}
    assert kinds == {"code_block"}
    assert {r.kind for r in index.find_name("Cart.add_item")} == {"heading"}
    assert {r.kind for r in index.find_name("add_item")} == {"heading", "code_span"}


def test_route_matches_any_path_parameter_style():
    index = build_index({"d.md": "`GET /api/orders/{id}`\nTry /api/orders/:order_id and /api/orders/<int:oid>\n"
                                 "But not /api/orders itself, nor /api/orders/{id}/items\n"})
    refs = index.find_route("GET /api/orders/{x}")
    assert [r.line for r in refs] == [1, 2, 2]
    assert refs[0].doc_method == "GET"
    assert index.find_route("GET /") == []


def test_file_names_and_paths_are_not_entity_references():
    index = build_index({"d.md": "See `app/cart_service.py` and `cart_service` here.\n"})
    assert [r.col_start for r in index.find_name("cart_service")] == [index.docs["d.md"].lines[0].rfind("cart_service")]


def test_relative_links_are_resolved_to_repository_paths():
    index = build_index({"Docs/a/guide.md": "[x](../../src/util.py) [y](http://x.io/src/util.py) [z](#anchor)\n"})
    assert [(l[1]) for l in index.docs["Docs/a/guide.md"].links] == ["src/util.py"]
    refs = index.find_path("src/util.py")
    assert len(refs) == 1 and refs[0].kind == "link"


def test_sections_and_code_identifiers():
    index = build_index({"d.md": DOC})
    doc = index.docs["d.md"]
    line = next(i + 1 for i, l in enumerate(doc.lines) if "cart.add_item(item)" in l)
    assert doc.sections[doc.section_of[line - 1]][2] == "`Cart.add_item`"
    assert {"item", "calculate_total", "cart"} <= doc.code_identifiers(line)


def test_distinctive_names():
    assert is_distinctive("get_order") and is_distinctive("Cart.add") and is_distinctive("CartService")
    assert not is_distinctive("get") and not is_distinctive("Cart")


def test_filter_doc_paths_skips_vendored_and_ignored():
    paths = ["README.md", "node_modules/x/README.md", "CHANGELOG.md", "Docs/a.md", "src/a.py", "docs/n.rst"]
    assert filter_doc_paths(paths, ["CHANGELOG*"]) == ["Docs/a.md", "README.md", "docs/n.rst"]


def test_affected_documents_list_every_reference():
    before = {"a.py": "def get_order(id):\n    pass\n"}
    after = {"a.py": "def get_order(id, expand=False):\n    pass\n"}
    docs = {"Docs/api.md": "Call `get_order(1)`.\n\nAlso `get_order`.\n", "Docs/other.md": "nothing here\n"}
    result = affected(before, after, docs)
    assert [d.path for d in result] == ["Docs/api.md"]
    assert [r.reference.line for r in result[0].references] == [1, 3]
    assert result[0].subjects == ["get_order"]


def test_implementation_only_changes_do_not_affect_docs():
    before = {"a.py": "def get_order(id):\n    return 1\n"}
    after = {"a.py": "def get_order(id):\n    return 2\n"}
    assert affected(before, after, {"d.md": "`get_order`\n"}) == []


def test_document_edited_in_the_pr_is_flagged():
    before = {"a.py": "def get_order(id):\n    pass\n", "d.md": "old\n"}
    after = {"a.py": "def get_order(id, x=1):\n    pass\n", "d.md": "`get_order`\n"}
    assert affected(before, after, {"d.md": "`get_order`\n"})[0].updated_in_pr


def test_class_reference_ignores_member_access_but_method_is_found_by_bare_name():
    before = {"a.py": "class Cart:\n    items: list\n    def calculate_total(self):\n        pass\n"}
    after = {"a.py": "class Cart:\n    items: list\n    extra: int\n    def calculate_total(self, tax):\n        pass\n"}
    docs = {"d.md": "## `Cart`\n\nUse `Cart.calculate_total()` and `cart.calculate_total()`.\n"}
    result = affected(before, after, docs)
    by_subject = {}
    for r in result[0].references:
        by_subject.setdefault(r.subject, []).append(r.reference.line)
    assert by_subject["Cart"] == [1]                      # heading only, not `Cart.calculate_total`
    assert by_subject["Cart.calculate_total"] == [3, 3]   # qualified + bare form, different columns


def test_deleted_and_renamed_files_are_found_by_path_and_link():
    before = {"src/gone.py": "x = 1\n", "Docs/old.md": "a\n"}
    after = {}
    docs = {"README.md": "See `src/gone.py` and [old](Docs/old.md).\n"}
    result = affected(before, after, docs)
    assert sorted(r.matched_name for r in result[0].references) == ["Docs/old.md", "src/gone.py"]
