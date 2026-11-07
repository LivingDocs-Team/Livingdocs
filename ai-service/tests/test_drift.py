"""LD-150 Test drift detection (LD-145): unit tests without HTTP.

LD-146 analyze Pull Request changes, LD-147 detect / classify / rate drift,
LD-148 identify affected documentation, LD-149 generate drift evidence.
API tests are in test_drift_api.py.
"""
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline generator for the realistic-document test

import pytest  # noqa: E402

from app.drift import DriftReportStore, analyze  # noqa: E402
from app.drift_affected import DocText, collect_docs  # noqa: E402
from app.drift_changes import (analyze_file, analyze_pull_request, find_tickets,  # noqa: E402
                               numbered, parse_patch)
from app.drift_evidence import diff_excerpt  # noqa: E402
from app.drift_models import (ChangedFile, DocSource, DriftAnalyzeRequest,  # noqa: E402
                              PullRequestInfo)
from app.jobs import JobOutput, jobs, run_job  # noqa: E402
from app.models import GenerateRequest, Scope  # noqa: E402
from app.templates import templates  # noqa: E402
from app.versions import DocumentStore  # noqa: E402
from drift_fixtures import AFTER, BEFORE, CART_SECTION, PATCH, PR, README, USERS_SECTION  # noqa: E402


def store_with(sections, target="acme/shop"):
    store = DocumentStore(None)
    out = JobOutput(scope=Scope.repository, target=target, template_id="default",
                    template_name="Standard technical docs", output_language="en",
                    sections=[(p, md, "offline", 0.5) for p, md in sections], confidence=0.5)
    doc = store.create_from_job("job-1", out, title="Shop docs", actor="tester")
    return store, doc


def request(files, docs=(), document_ids=None, pr=PR):
    return DriftAnalyzeRequest(repository="acme/shop", pull_request=pr, files=list(files),
                               docs=list(docs), document_ids=document_ids)


def changes_by_name(summary):
    return {c.name: c for c in summary.entity_changes}


def finding(report, entity=None, path=None, change=None):
    out = [f for f in report.findings
           if (entity is None or f.entity == entity) and (path is None or f.document.path == path)
           and (change is None or f.change == change)]
    assert len(out) == 1, [(f.entity, f.document.path, f.change) for f in report.findings]
    return out[0]


# ---------- LD-146: unified diff ----------

def test_parse_patch_hunks_and_line_numbers():
    hunks = parse_patch(PATCH)
    assert [(h.old_start, h.old_lines, h.new_start, h.new_lines) for h in hunks] == [(8, 8, 8, 9),
                                                                                  (30, 4, 31, 4)]
    assert hunks[1].header == "class Cart:"
    rows = list(numbered(hunks[0]))
    assert rows[1] == (9, None, '-@app.get("/carts/{id}")')          # removed: old number only
    assert rows[3] == (None, 9, '+@app.get("/api/carts/{id}")')     # added: new number only
    s = analyze_file(ChangedFile(path="shop/cart.py", patch=PATCH))
    assert (s.additions, s.deletions) == (5, 4)
    assert parse_patch(None) == [] and parse_patch("") == []


def test_tickets_from_title_branch_and_body():
    pr = PullRequestInfo(number=1, title="LD-146 analyze changes", head_branch="ld-147-detect",
                         body="Refs LD-146, LD-148. Fixes UTF-8 and SHA-256 handling.")
    assert find_tickets(pr) == ["LD-146", "LD-147", "LD-148"]
    assert find_tickets(PullRequestInfo(number=2)) == []


# ---------- LD-146: entity changes from the analyzer (before / after) ----------

def test_analysis_mode_classifies_entity_changes():
    s = analyze_file(ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER))
    assert s.method == "analysis" and s.language == "python"
    ch = changes_by_name(s)

    sig = ch["get_cart_total"]
    assert sig.change.value == "signature_changed"
    assert sig.removed_parameters == ["discount"] and sig.added_parameters == ["currency"]
    assert sig.old_signature == "get_cart_total(cart_id: int, discount: float) -> float"
    assert sig.new_signature == "get_cart_total(cart_id: int, currency: str) -> float"
    assert sig.changed_lines == 5                             # diff lines inside lines 10-15

    assert ch["clear_cart"].change.value == "removed"
    assert ch["DELETE /carts/{id}"].change.value == "removed"
    assert ch["_audit"].change.value == "removed"
    assert ch["apply_coupon"].change.value == "added"

    renamed = ch["count_cart_items"]                           # same parameters and return type
    assert renamed.change.value == "renamed" and renamed.old_name == "count_items"
    moved = ch["GET /api/carts/{id}"]                          # same handler, other path
    assert moved.change.value == "renamed" and moved.old_name == "GET /carts/{id}"

    assert ch["fetch_cart"].change.value == "behavior_changed"
    assert ch["fetch_cart"].details == ["docstring changed"]
    assert ch["Cart.add"].change.value == "behavior_changed"   # body lines in the diff
    assert "Cart" not in ch                                    # its method changed, not the class


def test_analysis_mode_renamed_class_keeps_its_methods():
    before = {"path": "a.py", "classes": [{"name": "Basket", "fields": [{"name": "items"}],
                                           "methods": [{"name": "total", "return_type": "float"}]}]}
    after = {"path": "a.py", "classes": [{"name": "Cart", "fields": [{"name": "items"}],
                                          "methods": [{"name": "total", "return_type": "float"}]}]}
    s = analyze_file(ChangedFile(path="a.py", before=before, after=after))
    assert [(c.change.value, c.old_name, c.name) for c in s.entity_changes] == [
        ("renamed", "Basket", "Cart")]


def test_analysis_mode_without_information_does_not_guess_renames():
    before = {"path": "a.py", "functions": [{"name": "start"}]}
    after = {"path": "a.py", "functions": [{"name": "begin"}]}
    s = analyze_file(ChangedFile(path="a.py", before=before, after=after))
    assert sorted((c.change.value, c.name) for c in s.entity_changes) == [("added", "begin"),
                                                                           ("removed", "start")]


def test_unchanged_entities_produce_no_change():
    s = analyze_file(ChangedFile(path="shop/cart.py", before=BEFORE, after=BEFORE))
    assert s.method == "analysis" and s.entity_changes == []


def test_removed_and_added_files_use_one_side():
    gone = analyze_file(ChangedFile(path="shop/cart.py", status="removed", before=BEFORE))
    assert gone.method == "analysis"
    assert {c.change.value for c in gone.entity_changes} == {"removed"}
    new = analyze_file(ChangedFile(path="shop/cart.py", status="added", after=AFTER))
    assert {c.change.value for c in new.entity_changes} == {"added"}


# ---------- LD-146: entity changes from the diff only ----------

def test_patch_mode_python():
    s = analyze_file(ChangedFile(path="shop/cart.py", patch=PATCH))
    assert s.method == "patch"
    ch = changes_by_name(s)
    assert ch["get_cart_total"].change.value == "signature_changed"
    assert ch["get_cart_total"].removed_parameters == ["discount"]
    assert ch["get_cart_total"].source == "patch"
    assert ch["GET /api/carts/{id}"].change.value == "renamed"
    assert ch["GET /api/carts/{id}"].old_name == "GET /carts/{id}"
    assert ch["Cart.add"].change.value == "behavior_changed"   # enclosing class from the header
    assert ch["Cart.add"].changed_lines == 2


def test_patch_mode_python_removed_function_and_body_change_from_hunk_header():
    patch = """@@ -1,6 +1,2 @@ import os
-def legacy_total(cart_id):
-    return 0
-
 def other():
     pass
@@ -20,3 +16,3 @@ def fetch_cart(cart_id: int):
     cart = db.get(cart_id)
-    return cart
+    return cache.get(cart_id) or cart
"""
    ch = changes_by_name(analyze_file(ChangedFile(path="m.py", patch=patch)))
    assert ch["legacy_total"].change.value == "removed"
    assert ch["fetch_cart"].change.value == "behavior_changed"
    assert "other" not in ch


def test_patch_mode_java_methods_and_routes():
    patch = """@@ -12,9 +12,9 @@ public class OrderController {
-    @GetMapping("/orders/{id}")
-    public OrderDto getOrder(@PathVariable Long id, boolean details) {
+    @GetMapping("/v2/orders/{id}")
+    public OrderDto getOrder(@PathVariable Long id) {
         return service.find(id);
     }
-    public void cancel(Long id) {
-        service.cancel(id);
-    }
"""
    s = analyze_file(ChangedFile(path="src/OrderController.java", patch=patch))
    assert s.method == "patch" and s.language == "java"
    ch = changes_by_name(s)
    assert ch["OrderController.getOrder"].change.value == "signature_changed"
    assert ch["OrderController.getOrder"].removed_parameters == ["details"]
    assert ch["OrderController.cancel"].change.value == "removed"
    assert ch["GET /v2/orders/{id}"].change.value == "renamed"
    assert not any(c.name in ("find", "service.find") for c in s.entity_changes)


def test_unsupported_language_and_invalid_analysis():
    js = analyze_file(ChangedFile(path="web/app.js", patch="@@ -1 +1 @@\n-a()\n+b()\n"))
    assert js.method == "none" and js.entity_changes == [] and "not analysed" in js.warnings[0]
    bad = analyze_file(ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE,
                                   after={"path": "shop/cart.py", "status": "invalid",
                                          "error": "SyntaxError"}))
    assert bad.method == "patch"                        # falls back to the diff
    assert any("invalid" in w for w in bad.warnings)


def test_analyze_pull_request_totals():
    a = analyze_pull_request(PullRequestInfo(**PR), [
        ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER),
        ChangedFile(path="docs/old.md", status="removed")])
    assert a.tickets == ["LD-146", "LD-147"]
    assert (a.additions, a.deletions) == (5, 4)
    assert a.entity_changes == len(a.files[0].entity_changes) == 9
    assert a.files[1].entity_changes == [] and a.files[1].method == "none"


def test_request_rejects_duplicate_paths_and_empty_files():
    with pytest.raises(ValueError):
        request([{"path": "a.py"}, {"path": "a.py"}])
    with pytest.raises(ValueError):
        request([])
    with pytest.raises(ValueError):
        DriftAnalyzeRequest(pull_request={"number": 0}, files=[{"path": "a.py"}])


# ---------- LD-148: affected documentation ----------

def test_affected_documents_and_matching_rules():
    store, doc = store_with([("shop/cart.py", CART_SECTION), ("shop/users.py", USERS_SECTION)])
    report = analyze(request([ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE,
                                          after=AFTER)], docs=[README]), store)
    parts = {(a.source, a.path): a for a in report.affected_documents}
    assert set(parts) == {(DocSource.document, "shop/cart.py"), (DocSource.repository, "README.md")}

    cart = parts[(DocSource.document, "shop/cart.py")]
    assert cart.document_id == doc.id and cart.version == 1
    assert cart.documents_file == "shop/cart.py"
    assert cart.reasons[0] == "documents changed file shop/cart.py"
    assert "mentions `clear_cart`" in cart.reasons

    readme = parts[(DocSource.repository, "README.md")]
    lines = {m.target: m.line for m in readme.matches}
    assert lines == {"GET /carts/{id}": 3, "clear_cart": 4}   # `:id` matches `{id}`
    # shop/users.py: `get_users` is not `get_cart_total`, prose "add" is not method Cart.add
    assert (DocSource.document, "shop/users.py") not in parts


def test_plain_words_and_bare_method_names_need_code_and_own_file():
    store, _ = store_with([("shop/cart.py", CART_SECTION)])
    other = {"path": "docs/guide.md", "content": "Use `add` to add things. `Cart.add` appends.\n"}
    report = analyze(request([ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE,
                                          after=AFTER)], docs=[other]), store)
    guide = finding(report, entity="Cart.add", path="docs/guide.md")
    assert [m.term for m in guide.document.matches] == ["Cart.add"]   # not the bare `add`
    own = finding(report, entity="Cart.add", path="shop/cart.py")
    assert [m.term for m in own.document.matches] == ["add"] and own.document.matches[0].in_code


def test_collect_docs_filters_and_reports_unknown_ids():
    store, doc = store_with([("shop/cart.py", CART_SECTION)])
    texts, warnings = collect_docs(store, [doc.id, "nope"], [])
    assert [t.path for t in texts] == ["shop/cart.py"] and texts[0].version == 1
    assert warnings == ["Document 'nope' not found; it was not checked."]
    texts, _ = collect_docs(store, [], [])
    assert texts == []


def test_code_spans_blocks_and_headings():
    d = DocText(DocSource.repository, "x.md", "# `a` title\n```\nfoo(x)\n```\ntext `bar` baz\n")
    assert d.in_code(0, 0) and d.in_code(2, 0)
    line = d.lines[4]
    assert d.in_code(4, line.index("bar")) and not d.in_code(4, line.index("baz"))


# ---------- LD-147: classification, severity and confidence ----------

def full_report(docs=(README,), files=None):
    store, _ = store_with([("shop/cart.py", CART_SECTION), ("shop/users.py", USERS_SECTION)])
    files = files or [ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER)]
    return analyze(request(files, docs=docs), store)


def test_classification_and_severity():
    r = full_report()
    sec = "shop/cart.py"
    expect = {
        ("GET /api/carts/{id}", sec): ("referential", "critical"),   # endpoint path moved
        ("DELETE /carts/{id}", sec): ("referential", "critical"),    # endpoint removed
        ("clear_cart", sec): ("referential", "high"),
        ("count_cart_items", sec): ("referential", "high"),          # renamed
        ("_audit", sec): ("referential", "medium"),                  # private: one level lower
        ("get_cart_total", sec): ("signature", "high"),              # names removed `discount`
        ("fetch_cart", sec): ("semantic", "medium"),                 # docstring changed
        ("Cart.add", sec): ("semantic", "low"),                      # body changed
        ("apply_coupon", sec): ("semantic", "low"),                  # new, not documented
        ("GET /api/carts/{id}", "README.md"): ("referential", "critical"),
        ("clear_cart", "README.md"): ("referential", "high"),
    }
    got = {(f.entity, f.document.path): (f.type.value, f.severity.value) for f in r.findings}
    assert got == expect
    assert r.status.value == "drift_detected"
    assert r.summary.highest_severity.value == "critical"
    assert r.summary.by_type == {"referential": 7, "signature": 1, "semantic": 3}
    assert r.summary.by_severity == {"low": 2, "medium": 2, "high": 4, "critical": 3}
    assert r.summary.affected_documents == 2 and r.summary.changed_files == 1
    # most severe first, ids in order
    sev = ["low", "medium", "high", "critical"]
    order = [sev.index(f.severity.value) for f in r.findings]
    assert order == sorted(order, reverse=True)
    assert [f.id for f in r.findings] == [f"F{i}" for i in range(1, len(r.findings) + 1)]


def test_signature_finding_details():
    f = finding(full_report(), entity="get_cart_total")
    assert f.before == "get_cart_total(cart_id: int, discount: float) -> float"
    assert f.after == "get_cart_total(cart_id: int, currency: str) -> float"
    assert "removed parameter(s): discount" in f.message and "`discount`" in f.message
    assert "`get_cart_total(cart_id: int, currency: str) -> float`" in f.suggestion
    assert f.confidence == 1.0 and f.confidence_level == "high"


def test_signature_change_without_stale_parameter_is_medium():
    after = dict(AFTER, functions=[dict(AFTER["functions"][0], parameters=[
        {"name": "cart_id", "type": "int"}, {"name": "discount", "type": "float"},
        {"name": "currency", "type": "str"}])])
    before = dict(BEFORE, functions=[BEFORE["functions"][0]], endpoints=[], classes=[])
    after["endpoints"], after["classes"] = [], []
    r = full_report(docs=(), files=[ChangedFile(path="shop/cart.py", before=before, after=after)])
    f = finding(r, entity="get_cart_total")
    assert (f.type.value, f.severity.value) == ("signature", "medium")


def test_file_removed_and_renamed():
    r = full_report(files=[ChangedFile(path="shop/cart.py", status="removed", before=BEFORE)])
    own = finding(r, path="shop/cart.py", change="file_removed")
    assert (own.type.value, own.severity.value) == ("referential", "high")
    link = finding(r, path="README.md", change="file_removed")
    assert link.severity.value == "medium" and link.document.matches[0].line == 4
    # entities of the deleted file are covered by the file-level finding in its own section
    assert not [f for f in r.findings if f.document.path == "shop/cart.py" and f.entity]
    assert finding(r, entity="clear_cart", path="README.md").severity.value == "high"

    moved = full_report(files=[ChangedFile(path="shop/basket.py", status="renamed",
                                           previous_path="shop/cart.py")])
    own = finding(moved, path="shop/cart.py", change="file_renamed")
    assert own.severity.value == "low" and own.after == "shop/basket.py"
    readme = finding(moved, path="README.md", change="file_renamed")
    assert readme.severity.value == "medium" and readme.before == "shop/cart.py"


def test_no_drift_when_documentation_does_not_mention_the_change():
    before = {"path": "shop/users.py", "functions": [{"name": "hash_pw", "parameters": [{"name": "raw"}]}]}
    after = {"path": "shop/users.py", "functions": [{"name": "hash_pw", "parameters": [{"name": "raw"},
                                                                                        {"name": "salt"}]}]}
    r = full_report(files=[ChangedFile(path="shop/users.py", before=before, after=after)])
    assert r.status.value == "no_drift" and r.findings == []
    assert r.summary.highest_severity is None
    assert r.analysis.entity_changes == 1


def test_no_documentation_to_check():
    r = analyze(request([ChangedFile(path="shop/cart.py", before=BEFORE, after=AFTER)]),
                DocumentStore(None))
    assert r.status.value == "no_drift"
    assert any("No documentation to check" in w for w in r.warnings)


def test_patch_mode_findings_have_lower_confidence():
    exact = finding(full_report(), entity="Cart.add", path="shop/cart.py")
    diff_only = finding(full_report(files=[ChangedFile(path="shop/cart.py", patch=PATCH)]),
                        entity="Cart.add", path="shop/cart.py")
    assert diff_only.factors["method"] == 0.8 and exact.factors["method"] == 1.0
    assert diff_only.confidence < exact.confidence
    assert 0 <= diff_only.confidence <= 1


def test_realistic_generated_documentation():
    """The offline generator's own Markdown is matched (headings, signatures, parameter tables)."""
    req = GenerateRequest(scope="repository", target="acme/shop", output_language="en", files=[BEFORE])
    tpl = templates.get("default")
    job = jobs.create(req, tpl)
    run_job(job.id, req, None, tpl)
    store = DocumentStore(None)
    store.create_from_job(job.id, jobs.get_output(job.id))
    r = analyze(request([ChangedFile(path="shop/cart.py", patch=PATCH, before=BEFORE, after=AFTER)]),
                store)
    got = {(f.entity, f.type.value) for f in r.findings}
    assert ("get_cart_total", "signature") in got
    assert ("clear_cart", "referential") in got
    assert ("GET /api/carts/{id}", "referential") in got
    assert finding(r, entity="get_cart_total").severity.value == "high"  # table names `discount`


# ---------- LD-149: evidence ----------

def test_finding_evidence_code_doc_commit_ticket():
    f = finding(full_report(), entity="get_cart_total")
    kinds = [e.kind.value for e in f.evidence]
    assert kinds[0] == "code_diff" and kinds[-2:] == ["ticket", "ticket"]
    assert "commit" in kinds and "documentation" in kinds

    diff = f.evidence[0]
    assert diff.path == "shop/cart.py" and diff.commit_sha == "9f2c1e7"
    assert diff.pull_request_number == 42
    assert "-def get_cart_total(cart_id: int, discount: float) -> float:" in diff.excerpt
    assert "+    return convert(total, currency)" in diff.excerpt
    assert diff.excerpt.startswith("@@ -8,8 +8,9 @@")
    assert "class Cart" not in diff.excerpt                      # only this entity's hunk

    docs = [e for e in f.evidence if e.kind.value == "documentation"]
    lines = CART_SECTION.splitlines()
    for e in docs:
        assert e.excerpt == lines[e.line_start - 1].strip()
        assert e.version == 1 and e.document_id
    assert "get_cart_total(cart_id, discount)" in [e.excerpt for e in docs]   # stale signature

    commit = next(e for e in f.evidence if e.kind.value == "commit")
    assert commit.url == PR["url"] and commit.excerpt == "PR #42: LD-146 Cart: currency support"
    assert [e.ticket for e in f.evidence if e.kind.value == "ticket"] == ["LD-146", "LD-147"]
    assert len({e.id for e in f.evidence}) == len(f.evidence)


def test_evidence_without_diff_uses_signatures():
    r = full_report(docs=(), files=[ChangedFile(path="shop/cart.py", before=BEFORE, after=AFTER)])
    diff = finding(r, entity="clear_cart").evidence[0]
    assert diff.kind.value == "code_diff" and diff.excerpt == "- clear_cart(cart_id: int)"


def test_evidence_without_diff_shows_changed_docstring():
    r = full_report(files=[ChangedFile(path="shop/cart.py", before=BEFORE, after=AFTER)])
    f = finding(r, entity="fetch_cart")
    assert f.type.value == "semantic" and f.change == "behavior_changed"
    assert f.evidence[0].excerpt.splitlines() == [
        "  fetch_cart(cart_id: int) -> Cart",                    # same signature: shown once
        '-     """Load a cart."""',
        '+     """Load a cart from the cache first."""']
    c = changes_by_name(analyze_file(ChangedFile(path="shop/cart.py", before=BEFORE, after=AFTER)))
    assert (c["fetch_cart"].old_docstring, c["fetch_cart"].new_docstring) == (
        "Load a cart.", "Load a cart from the cache first.")
    assert c["get_cart_total"].old_docstring is None             # docstring did not change


def test_undocumented_entity_points_at_its_section():
    f = finding(full_report(), entity="apply_coupon")
    doc = next(e for e in f.evidence if e.kind.value == "documentation")
    assert doc.line_start == 1 and doc.excerpt == "# shop/cart.py"


def test_diff_excerpt_is_limited():
    big = "@@ -1,80 +1,80 @@ def f():\n" + "".join(f"-a{i}\n+b{i}\n" for i in range(40))
    text, first, last = diff_excerpt(parse_patch(big), None)
    assert text.count("\n") <= 31 and "more line(s)" in text
    assert first == 1


# ---------- report store ----------

def test_report_store_lists_newest_first_and_filters():
    store = DriftReportStore(limit=2)
    reports = [full_report(), full_report(docs=()), full_report()]
    reports[2].pull_request.number = 7
    for r in reports:
        store.add(r)
    assert store.get(reports[0].id) is None                      # oldest dropped (limit 2)
    rows = store.list()
    assert [x.id for x in rows] == [reports[2].id, reports[1].id]
    assert [x.id for x in store.list(pull_request=7)] == [reports[2].id]
    assert store.list(repository="other/repo") == []
    assert rows[0].summary.findings == len(reports[2].findings)
