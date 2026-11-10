"""LD-347 Implement source-documentation comparison: regression fixtures.

Every folder of tests/fixtures/drift_cases/ is one Pull Request on one file:

    before.py / after.py      the file at the base and head commit
    before.json / after.json  the analyzer's result for each (scripts/capture_drift_cases.py)
    docs/                     the documentation at the head commit (README, docs/...)
    case.json                 description, path / status, and the exact expected findings
                              [type, kind, entity, document]; `expected_patch` when the
                              diff-only mode differs

Each case runs twice: with the analyzer's before/after results ("analysis") and with the diff
only ("patch"). The findings must match exactly: a missing finding is a regression, an extra one
is a false positive. Cases cover referential, signature and semantic drift, documentation that is
already up to date or unrelated, and Pull Requests that change nothing that is documented.
"""
import difflib
import json
import pathlib
import re

import pytest

from app.drift import DRIFT_KINDS, analyze
from app.drift_models import ChangedFile, DriftAnalyzeRequest
from app.versions import DocumentStore

CASES_DIR = pathlib.Path(__file__).parent / "fixtures" / "drift_cases"
CASES = sorted(p.name for p in CASES_DIR.iterdir() if (p / "case.json").exists())
CATEGORIES = ("referential", "signature", "semantic", "unchanged_docs", "no_change")


def load(name):
    d = CASES_DIR / name
    meta = json.loads((d / "case.json").read_text(encoding="utf-8"))
    before = (d / "before.py").read_text(encoding="utf-8")
    after = (d / "after.py").read_text(encoding="utf-8")
    docs = [{"path": p.relative_to(d / "docs").as_posix(), "content": p.read_text(encoding="utf-8")}
            for p in sorted((d / "docs").rglob("*")) if p.is_file()]
    return d, meta, before, after, docs


HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")
FUNCNAME = re.compile(r"^[A-Za-z_$]")      # git's default hunk-header rule


def github_patch(before: str, after: str):
    """The `patch` field GitHub returns for a file: hunks only, no ---/+++ header, and after each
    @@ ... @@ the nearest line above the hunk that starts with a letter (git's default funcname,
    usually `def ...` / `class ...`), as `git diff` writes it."""
    old = before.splitlines()
    out = []
    for line in list(difflib.unified_diff(old, after.splitlines(), lineterm="", n=3))[2:]:
        m = HUNK.match(line)
        if m:
            first = int(m.group(1))          # first old line of the hunk (1-based)
            context = next((old[i] for i in range(first - 2, -1, -1) if FUNCNAME.match(old[i])), "")
            line = m.group(0) + (" " + context.strip() if context else "")
        out.append(line)
    return "\n".join(out) or None


def run(name, mode):
    d, meta, before, after, docs = load(name)
    changed = {"path": meta["path"], "status": meta["status"], "patch": github_patch(before, after)}
    if meta.get("previous_path"):
        changed["previous_path"] = meta["previous_path"]
    if mode == "analysis":
        changed["before"] = json.loads((d / "before.json").read_text(encoding="utf-8"))
        changed["after"] = json.loads((d / "after.json").read_text(encoding="utf-8"))
    req = DriftAnalyzeRequest(repository="acme/shop", files=[ChangedFile(**changed)], docs=docs,
                              document_ids=[], pull_request={"number": 347, "title": f"LD-347 {name}"})
    return meta, analyze(req, DocumentStore(None))


def found(report):
    return sorted([f.type.value, f.kind, f.entity, f.document.path] for f in report.findings)


def expected(meta, mode):
    rows = meta["expected_patch"] if mode == "patch" and "expected_patch" in meta else meta["expected"]
    return sorted(rows, key=lambda r: [x or "" for x in r])


@pytest.mark.parametrize("mode", ["analysis", "patch"])
@pytest.mark.parametrize("name", CASES)
def test_case_matches_expected_findings(name, mode):
    meta, report = run(name, mode)
    assert sorted(found(report), key=lambda r: [x or "" for x in r]) == expected(meta, mode), meta["description"]
    for w in meta.get("warnings", []):
        assert w in report.warnings
    if not expected(meta, mode):
        # unchanged documentation / no-change Pull Request: a clean report
        assert report.status.value == "no_drift"
        assert report.affected_documents == [] and report.summary.highest_severity is None
    else:
        assert report.status.value == "drift_detected"
        for f in report.findings:
            assert f.kind in DRIFT_KINDS[f.type.value]
            assert f.evidence[0].kind.value == "code_diff"
            assert any(e.kind.value == "documentation" for e in f.evidence)
            assert f.severity_assessment.level == f.severity
        assert {a.path for a in report.affected_documents} == {f.document.path for f in report.findings}


def test_corpus_covers_every_category():
    for category in CATEGORIES:
        assert [c for c in CASES if c.startswith(category)], f"no fixture for {category}"
    kinds = {row[1] for c in CASES for row in load(c)[1]["expected"]}
    assert {"entity_removed", "entity_renamed", "endpoint_moved", "module_moved", "file_moved",
            "parameter_removed", "parameter_type_changed", "parameter_added",
            "status_codes_changed", "docstring_changed"} <= kinds


def test_fixtures_are_consistent():
    for name in CASES:
        d, meta, before, after, docs = load(name)
        assert meta["description"] and docs, name
        for side, path in (("before", meta.get("previous_path") or meta["path"]), ("after", meta["path"])):
            analysis = json.loads((d / f"{side}.json").read_text(encoding="utf-8"))
            assert analysis["status"] == "ok" and analysis["path"] == path, (name, side)


# ---------- the false positives LD-347 removed, one assertion each ----------

def test_stale_details_stay_in_the_entity_section():
    _, report = run("signature_parameter_removed", "analysis")
    [f] = report.findings
    stale = [m for m in f.document.matches if m.kind == "parameter"]
    assert [m.term for m in stale] == ["timeout"]
    section_end = next(i for i, line in enumerate(load("signature_parameter_removed")[4][0]["content"]
                                                  .splitlines(), 1) if line == "## `clear_cart`")
    assert stale[0].line < section_end       # `fetch_cart`'s own line, not clear_cart's table


def test_signature_defaults_are_not_reported_again_as_behaviour():
    _, report = run("signature_type_and_default_changed", "analysis")
    assert [f.type.value for f in report.findings] == ["signature"]


def test_change_log_is_skipped_with_a_warning():
    _, report = run("unchanged_docs_acknowledge_change", "patch")
    assert not any(f.document.path == "CHANGELOG.md" for f in report.findings)
    assert any(w.startswith("CHANGELOG.md: change log") for w in report.warnings)
