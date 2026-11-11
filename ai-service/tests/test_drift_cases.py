"""LD-347 Implement source-documentation comparison: regression fixtures.

tests/fixtures/drift_cases.json holds one Pull Request per case: the changed file at the base
and head commit, the analyzer's result for each (scripts/capture_drift_cases.py), the
documentation at the head commit, and the exact expected findings [type, kind, entity, document].

Each case runs twice - with the analyzer results ("analysis") and with the diff only ("patch",
as GitHub returns it) - and the findings must match exactly: a missing finding is a regression,
an extra one is a false positive. Cases cover referential, signature and semantic drift,
documentation that is already up to date or unrelated, and Pull Requests that change nothing.
"""
import difflib
import json
import pathlib
import re

import pytest

from app.drift import DRIFT_KINDS, analyze
from app.drift_models import ChangedFile, DriftAnalyzeRequest
from app.versions import DocumentStore

DATA = json.loads((pathlib.Path(__file__).parent / "fixtures" / "drift_cases.json").read_text(encoding="utf-8"))
CASES = {c["name"]: c for c in DATA["cases"]}
CATEGORIES = ("referential", "signature", "semantic", "unchanged_docs", "no_change")
HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")
FUNCNAME = re.compile(r"^[A-Za-z_$]")        # git's default rule for the text after @@ ... @@


def github_patch(before: str, after: str):
    """The `patch` GitHub returns for a file: hunks only, and after each `@@ ... @@` the nearest
    line above the hunk that starts with a letter (usually `def ...` / `class ...`)."""
    old = before.splitlines()
    out = []
    for line in list(difflib.unified_diff(old, after.splitlines(), lineterm="", n=3))[2:]:
        m = HUNK.match(line)
        if m:
            first = int(m.group(1))
            context = next((old[i] for i in range(first - 2, -1, -1) if FUNCNAME.match(old[i])), "")
            line = m.group(0) + (" " + context.strip() if context else "")
        out.append(line)
    return "\n".join(out) or None


def run(name: str, mode: str):
    c = CASES[name]
    changed = {"path": c["path"], "status": c["status"], "patch": github_patch(c["before"], c["after"])}
    if c.get("previous_path"):
        changed["previous_path"] = c["previous_path"]
    if mode == "analysis":
        changed["before"], changed["after"] = c["before_analysis"], c["after_analysis"]
    req = DriftAnalyzeRequest(repository="acme/shop", files=[ChangedFile(**changed)], document_ids=[],
                              docs=[{"path": p, "content": t} for p, t in sorted(c["docs"].items())],
                              pull_request={"number": 347, "title": f"LD-347 {name}"}, ai_review=False)
    return analyze(req, DocumentStore(None))


def rows(items):
    return sorted((list(r) for r in items), key=lambda r: [x or "" for x in r])


@pytest.mark.parametrize("mode", ["analysis", "patch"])
@pytest.mark.parametrize("name", sorted(CASES))
def test_case_matches_expected_findings(name, mode):
    c = CASES[name]
    report = run(name, mode)
    got = rows([f.type.value, f.kind, f.entity, f.document.path] for f in report.findings)
    assert got == rows(c["expected"]), c["description"]
    for w in c["warnings"]:
        assert w in report.warnings
    if not c["expected"]:              # unchanged documentation / no-change Pull Request
        assert report.status.value == "no_drift" and report.affected_documents == []
        assert report.summary.highest_severity is None and report.review.status.value == "not_required"
        return
    assert report.status.value == "drift_detected"
    assert {a.path for a in report.affected_documents} == {f.document.path for f in report.findings}
    for f in report.findings:
        assert f.kind in DRIFT_KINDS[f.type.value]
        assert f.evidence[0].kind.value == "code_diff"
        assert any(e.kind.value == "documentation" for e in f.evidence)
        assert f.severity_assessment.level == f.severity
        assert f.resolution.status.value == "open"


def test_corpus_covers_every_category_and_kind():
    for category in CATEGORIES:
        assert [n for n in CASES if n.startswith(category)], f"no fixture for {category}"
    kinds = {r[1] for c in CASES.values() for r in c["expected"]}
    assert {"entity_removed", "entity_renamed", "endpoint_moved", "module_moved", "file_moved",
            "parameter_removed", "parameter_type_changed", "parameter_added",
            "status_codes_changed", "docstring_changed"} <= kinds


def test_fixtures_are_consistent():
    for name, c in CASES.items():
        assert c["description"] and c["docs"], name
        for side, path in (("before", c.get("previous_path") or c["path"]), ("after", c["path"])):
            assert c[f"{side}_analysis"]["status"] == "ok", (name, side)
            assert c[f"{side}_analysis"]["path"] == path, (name, side)


# ---------- the false positives LD-347 removed ----------

def test_stale_details_are_taken_from_the_entity_section_only():
    [f] = run("signature_parameter_removed", "analysis").findings
    stale = [m for m in f.document.matches if m.kind == "parameter"]
    lines = CASES["signature_parameter_removed"]["docs"]["docs/api.md"].splitlines()
    assert [m.term for m in stale] == ["timeout"]
    assert stale[0].line < lines.index("## `clear_cart`") + 1     # fetch_cart's own line


def test_one_change_gives_one_finding():
    # the changed default on the `def` line is not also a semantic "values" change, and the
    # endpoint is not reported a second time for its handler's parameters
    assert [(f.type.value, f.entity) for f in run("signature_type_and_default_changed", "analysis").findings] \
        == [("signature", "get_total")]
