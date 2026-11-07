"""LD-149 - Generate drift evidence (JSON + Markdown report)."""
import datetime
import json

from drift.report import render_markdown

from drift_helpers import find, run

NOW = datetime.datetime(2026, 11, 7, 10, 0, 0, tzinfo=datetime.timezone.utc)
BEFORE = {"src/cart.py": "class Cart:\n    def add_item(self, item, qty=1):\n        return 1\n"}
AFTER = {"src/cart.py": "class Cart:\n    def add_item(self, item, quantity=1, coupon=None):\n        return 1\n"}
DOC = "# API\n\n## Cart.add_item\n\nCall `cart.add_item(item, qty)`.\n\nMore text.\n"


def report(**kw):
    return run(BEFORE, AFTER, {"Docs/api.md": DOC}, now=NOW, commit="a" * 40, repository="acme/shop", **kw)


def test_evidence_links_documentation_and_code():
    (e,) = find(report(), "DRIFT003")
    assert e.doc.path == "Docs/api.md" and e.doc.line == 5 and e.doc.section == "Cart.add_item"
    highlighted = [x for x in e.doc.excerpt if x["highlight"]]
    assert len(highlighted) == 1 and "add_item(item, qty)" in highlighted[0]["text"]
    assert [x["line"] for x in e.doc.excerpt] == [3, 4, 5, 6, 7]
    assert e.code.file_path == "src/cart.py" and (e.code.start_line, e.code.end_line) == (2, 3)
    assert e.code.before_signature != e.code.after_signature and "coupon" in e.code.after_signature
    assert "+    def add_item(self, item, quantity=1, coupon=None):" in e.code.diff_excerpt
    assert e.code.commit_hash == "a" * 40 and e.reasons and e.suggestion


def test_diff_excerpt_is_trimmed_to_the_changed_entity():
    before = {"a.py": "".join(f"def f{i}(x):\n    pass\n\n" for i in range(8))}
    after = {"a.py": before["a.py"].replace("def f3(x):", "def f3(x, y):")}
    rep = run(before, after, {"d.md": "`f3(x)`\n"})
    (e,) = find(rep, "DRIFT003")
    assert "f3(x, y)" in e.code.diff_excerpt and "f7" not in e.code.diff_excerpt and "f0" not in e.code.diff_excerpt


def test_json_report_has_a_stable_schema():
    data = json.loads(report().to_json())
    assert data["schema_version"] == "1.0" and data["generated_at"] == "2026-11-07T10:00:00+00:00"
    assert data["repository"] == "acme/shop" and data["commit_hash"] == "a" * 40
    assert set(data["summary"]) >= {"files_changed", "entities_changed", "documents_scanned",
                                    "documents_with_drift", "drift_findings", "by_severity"}
    ev = data["evidence"][0]
    assert set(ev) == {"id", "rule_id", "drift_type", "severity", "confidence", "entity", "kind", "summary",
                       "reasons", "suggestion", "doc", "code", "doc_updated_in_pr"}
    # same field names as the project's GroundingEvidence
    assert {"file_path", "start_line", "end_line", "code_snippet", "commit_hash"} <= set(ev["code"])
    assert data["affected_documents"][0]["path"] == "Docs/api.md"


def test_report_without_drift_is_explicit_about_it():
    rep = run(BEFORE, AFTER, {"Docs/api.md": "Nothing about the cart.\n"}, now=NOW)
    assert not rep.has_drift and rep.summary["drift_findings"] == 0
    assert "No documentation drift detected" in render_markdown(rep)


def test_markdown_report_content():
    text = render_markdown(report())
    assert text.startswith("## Documentation Drift Report")
    assert "| 1 | HIGH | `Docs/api.md:5` | `Cart.add_item` | DRIFT003 signature_changed |" in text
    assert "**Fix:**" in text and "<details><summary>Evidence</summary>" in text
    assert "```diff" in text


def test_markdown_uses_a_longer_fence_when_the_excerpt_contains_backticks():
    doc = "## Cart.add_item\n\n```python\nx = cart.add_item(item, qty)\n```\n"
    rep = run(BEFORE, AFTER, {"d.md": doc}, now=NOW)
    text = render_markdown(rep)
    assert "````" in text   # the quoted code fence cannot terminate the report's own fence


def test_markdown_is_capped_for_large_reports():
    before = {"a.py": "".join(f"def func_number_{i}(x):\n    pass\n" for i in range(300))}
    docs = {"d.md": "".join(f"`func_number_{i}` is documented here.\n\n" for i in range(300))}
    rep = run(before, {"a.py": "x = 1\n"}, docs, now=NOW)
    assert len(rep.evidence) == 300
    text = render_markdown(rep)
    assert len(text) <= 60_000 and "more finding(s)" in text or "truncated" in text


def test_document_edited_in_pr_is_reported():
    before = {**BEFORE, "Docs/api.md": "old\n"}
    after = {**AFTER, "Docs/api.md": DOC}
    rep = run(before, after, {"Docs/api.md": DOC}, now=NOW)
    (e,) = find(rep, "DRIFT003")
    assert e.doc_updated_in_pr
    assert "document was edited in this PR" in render_markdown(rep)


def test_summary_counts_by_severity():
    rep = report()
    assert rep.summary["by_severity"]["high"] >= 1
    assert rep.summary["documents_with_drift"] == 1
