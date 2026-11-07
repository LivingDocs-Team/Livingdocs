"""LD-146 - Analyze pull request changes."""
from drift.diff_parser import parse_unified_diff, reconstruct_old
from drift.entities import ExtractionError, extract_entities
from drift.models import ChangeType, FileStatus
from drift.pr_analyzer import analyze_pull_request, compare_entities

import pytest
from drift_helpers import GIT_AVAILABLE, GitSandbox, make_diff, readers


def analyze(before, after):
    old, new = readers(before, after)
    return analyze_pull_request(make_diff(before, after), old, new)


def changes_by_name(analysis):
    return {c.name: c for c in analysis.entity_changes}


# ---------------------------------------------------------------- diff parser

def test_parse_modified_added_and_deleted_files():
    diff = make_diff({"a.py": "x = 1\ny = 2\n", "gone.py": "z = 1\n"},
                     {"a.py": "x = 1\ny = 3\n", "new.py": "q = 1\n"})
    files = {f.path: f for f in parse_unified_diff(diff)}
    assert files["a.py"].status == FileStatus.MODIFIED
    assert (files["a.py"].added_lines, files["a.py"].removed_lines) == (1, 1)
    assert files["new.py"].status == FileStatus.ADDED
    assert files["gone.py"].status == FileStatus.DELETED
    assert files["gone.py"].removed_lines == 1


def test_parse_pure_rename_and_binary_and_quoted_path():
    diff = (
        "diff --git a/old name.md b/new name.md\n"
        "similarity index 100%\n"
        "rename from old name.md\n"
        "rename to new name.md\n"
        "diff --git a/logo.png b/logo.png\n"
        "index 1..2 100644\n"
        "Binary files a/logo.png and b/logo.png differ\n"
        'diff --git "a/caf\\303\\251.py" "b/caf\\303\\251.py"\n'
        'index 1..2 100644\n'
        '--- "a/caf\\303\\251.py"\n'
        '+++ "b/caf\\303\\251.py"\n'
        "@@ -1 +1 @@\n-a = 1\n+a = 2\n")
    files = {f.path: f for f in parse_unified_diff(diff)}
    assert files["new name.md"].status == FileStatus.RENAMED
    assert files["new name.md"].old_path == "old name.md"
    assert files["logo.png"].binary
    assert "caf\u00e9.py" in files


def test_parse_plain_diff_without_git_header_and_no_newline_marker():
    diff = ("--- a/x.py\t2026-01-01\n+++ b/x.py\t2026-01-02\n@@ -1,2 +1,2 @@\n a = 1\n-b = 2\n"
            "\\ No newline at end of file\n+b = 3\n"
            "--- a/y.py\n+++ b/y.py\n@@ -1 +1 @@\n-c\n+d\n")
    files = parse_unified_diff(diff)
    assert [f.path for f in files] == ["x.py", "y.py"]
    assert files[0].added_lines == 1 and files[0].removed_lines == 1


def test_removed_line_starting_with_dashes_is_not_a_file_header():
    diff = ("diff --git a/n.md b/n.md\n--- a/n.md\n+++ b/n.md\n@@ -1,2 +1,1 @@\n"
            "--- a note that looks like a header\n keep\n")
    files = parse_unified_diff(diff)
    assert len(files) == 1 and files[0].removed_lines == 1


def test_empty_or_garbage_diff_yields_no_files():
    assert parse_unified_diff("") == []
    assert parse_unified_diff("not a diff at all\n") == []


def test_reconstruct_old_matches_original_content():
    old = "".join(f"line {i}\n" for i in range(1, 31))
    new = old.replace("line 5\n", "line five\nextra\n").replace("line 25\n", "")
    change = parse_unified_diff(make_diff({"f.txt": old}, {"f.txt": new}))[0]
    assert reconstruct_old(new, change) == old
    added = parse_unified_diff(make_diff({}, {"f.txt": new}))[0]
    assert reconstruct_old(new, added) is None
    deleted = parse_unified_diff(make_diff({"f.txt": old}, {}))[0]
    assert reconstruct_old(None, deleted) == old


# ---------------------------------------------------------------- entity extraction

PY = '''
from fastapi import APIRouter
router = APIRouter(prefix="/api")

class Cart(Base):
    """doc"""
    items: list[str]

    def add(self, item, qty: int = 1) -> None:
        pass

    @staticmethod
    def make(a, *args, k=1, **kw):
        pass

@router.get("/orders/{id}")
async def get_order(id: int) -> Order:
    return 1
'''


def test_python_extraction_signatures_routes_and_fields():
    ents = {e.name: e for e in extract_entities("a.py", PY, "python")}
    assert ents["Cart"].bases == ("Base",) and ents["Cart"].fields == ("items: list[str]",)
    add = ents["Cart.add"]
    assert add.kind == "method" and add.param_names == ("item", "qty")
    assert add.params[1].has_default and add.params[1].type == "int" and add.return_type == "None"
    make = ents["Cart.make"]
    assert [p.variadic for p in make.params] == ["", "*", "", "**"]
    order = ents["get_order"]
    assert order.kind == "function" and order.routes == ("GET /api/orders/{id}",)
    assert order.signature.startswith("async def get_order")


def test_python_syntax_error_raises_extraction_error():
    with pytest.raises(ExtractionError):
        extract_entities("bad.py", "def broken(:\n", "python")


JAVA = '''
package shop;
@RestController
@RequestMapping("/api/orders")
public class OrderController extends Base implements Foo<T> {
    private final OrderService service;
    public OrderController(OrderService service) { this.service = service; }

    @GetMapping("/{id}")
    public ResponseEntity<Order> getOrder(@PathVariable("id") long id, @RequestParam String q) {
        String s = "{ not a brace";   // } also not a brace
        return null;
    }
    @PostMapping
    public Order create(@RequestBody OrderDto dto) throws Exception { return null; }
    @RequestMapping(value = "/legacy", method = RequestMethod.DELETE)
    void legacy() {}
    public record Point(int x, int y) {}
}
'''


def test_java_extraction_spring_routes_methods_and_records():
    ents = {e.name: e for e in extract_entities("O.java", JAVA, "java")}
    assert ents["OrderController"].bases == ("Base", "Foo")
    assert "service: OrderService" in ents["OrderController"].fields
    get = ents["OrderController.getOrder"]
    assert get.routes == ("GET /api/orders/{id}",)
    assert get.param_names == ("id", "q") and get.return_type == "ResponseEntity<Order>"
    assert ents["OrderController.create"].routes == ("POST /api/orders",)
    assert ents["OrderController.legacy"].routes == ("DELETE /api/orders/legacy",)
    assert ents["OrderController.Point"].fields == ("x: int", "y: int")


# ---------------------------------------------------------------- entity comparison

def test_parameter_added_removed_and_retyped():
    before = {"a.py": "def f(a, b: int, c=1):\n    pass\n"}
    after = {"a.py": "def f(a, b: str, d=2):\n    pass\n"}
    c = changes_by_name(analyze(before, after))["f"]
    assert c.change_type == ChangeType.MODIFIED and c.signature_changed and c.api_changed
    assert c.params_added == ("d",) and c.params_removed == ("c",) and c.params_changed == ("b",)


def test_return_type_change_and_default_change_are_api_changes():
    before = {"a.py": "def f(a=1) -> int:\n    pass\n"}
    after = {"a.py": "def f(a) -> str:\n    pass\n"}
    c = changes_by_name(analyze(before, after))["f"]
    assert c.return_changed and c.params_changed == ("a",)


def test_body_only_change_is_not_an_api_change():
    before = {"a.py": "def f(a):\n    return 1\n"}
    after = {"a.py": "def f(a):\n    return 2\n"}
    c = changes_by_name(analyze(before, after))["f"]
    assert c.body_changed and not c.api_changed


def test_docstring_or_comment_only_change_is_ignored():
    before = {"a.py": 'def f(a):\n    """old"""\n    return 1\n'}
    after = {"a.py": 'def f(a):\n    """new docs"""\n    return 1  # note\n'}
    assert analyze(before, after).entity_changes == []


def test_added_removed_and_renamed_entities():
    before = {"a.py": "def keep():\n    pass\n\ndef old_name(x):\n    return x * 2\n\ndef gone(a, b):\n    pass\n"}
    after = {"a.py": "def keep():\n    pass\n\ndef new_name(x):\n    return x * 2\n\ndef fresh(z):\n    pass\n"}
    by = changes_by_name(analyze(before, after))
    assert by["new_name"].change_type == ChangeType.RENAMED and by["new_name"].renamed_from == "old_name"
    assert by["gone"].change_type == ChangeType.REMOVED
    assert by["fresh"].change_type == ChangeType.ADDED


def test_entity_moved_between_files():
    before = {"a.py": "def shared(x):\n    return x\n", "b.py": "pass_ = 1\n"}
    after = {"a.py": "pass_ = 0\n", "b.py": "def shared(x):\n    return x\n"}
    by = changes_by_name(analyze(before, after))
    assert by["shared"].change_type == ChangeType.MOVED and by["shared"].moved_from == "a.py"
    assert by["shared"].file == "b.py"


def test_route_change_is_detected_on_the_handler():
    before = {"a.py": 'from f import app\n@app.get("/a")\ndef h():\n    pass\n'}
    after = {"a.py": 'from f import app\n@app.post("/b")\ndef h():\n    pass\n'}
    c = changes_by_name(analyze(before, after))["h"]
    assert c.routes_removed == ("GET /a",) and c.routes_added == ("POST /b",) and c.api_changed


def test_class_attribute_and_base_changes():
    before = {"a.py": "class M(Base):\n    a: int\n    b: str\n"}
    after = {"a.py": "class M(Other):\n    a: int\n    c: float\n"}
    c = changes_by_name(analyze(before, after))["M"]
    assert c.bases_changed and c.members_removed == ("b: str",) and c.members_added == ("c: float",)


def test_java_overloads_are_compared_independently():
    before = {"A.java": "class A {\n  void run(int a) {}\n  void run(String s) {}\n}\n"}
    after = {"A.java": "class A {\n  void run(int a, int b) {}\n  void run(String s) {}\n}\n"}
    result = analyze(before, after).entity_changes
    assert len(result) == 1 and result[0].name == "A.run"
    assert result[0].params_added == ("b",)


def test_unparseable_file_gives_a_warning_not_a_crash():
    before = {"a.py": "def f():\n    pass\n"}
    after = {"a.py": "def f(:\n"}
    analysis = analyze(before, after)
    assert analysis.entity_changes == []
    assert any("cannot parse" in w for w in analysis.warnings)


def test_non_code_files_and_doc_files_are_listed_but_not_analyzed():
    analysis = analyze({"README.md": "a\n", "x.txt": "1\n"}, {"README.md": "b\n", "x.txt": "2\n"})
    assert analysis.entity_changes == []
    assert analysis.doc_files_changed == ["README.md"]
    assert analysis.summary()["files_changed"] == 2


def test_compare_entities_identical_versions_yield_nothing():
    ents = extract_entities("a.py", PY, "python")
    assert compare_entities(ents, ents) == []


@pytest.mark.skipif(not GIT_AVAILABLE, reason="git is not installed")
def test_real_git_diff_with_rename_and_reconstruction(tmp_path):
    box = GitSandbox(tmp_path)
    box.write({"src/cart.py": "class Cart:\n    def add(self, item):\n        return item\n" * 1,
               "src/old.py": "def keep(a):\n    return a\n" + "# filler\n" * 10})
    box.commit("base")
    box.branch("feature")
    (tmp_path / "src" / "old.py").rename(tmp_path / "src" / "renamed.py")
    box.write({"src/cart.py": "class Cart:\n    def add(self, item, qty=1):\n        return item\n"})
    box.commit("change")
    diff = box.diff()
    files = {f.path: f for f in parse_unified_diff(diff)}
    assert files["src/renamed.py"].status == FileStatus.RENAMED and files["src/renamed.py"].old_path == "src/old.py"
    new_cart = (tmp_path / "src" / "cart.py").read_text()
    assert reconstruct_old(new_cart, files["src/cart.py"]) == "class Cart:\n    def add(self, item):\n        return item\n"
