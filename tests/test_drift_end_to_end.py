"""LD-150 - Test drift detection end to end: real git repositories, the CLI and the diff-file mode."""
import json

import pytest

from drift.cli import main
from drift.sources import run_on_diff_file, run_on_git

from drift_helpers import GIT_AVAILABLE, GitSandbox, find

pytestmark_git = pytest.mark.skipif(not GIT_AVAILABLE, reason="git is not installed")

BASE_FILES = {
    "src/cart.py": ("from fastapi import APIRouter\nrouter = APIRouter(prefix='/api')\n\n"
                    "class Cart:\n    def add_item(self, item, qty=1):\n        return 1\n\n"
                    "@router.get('/orders/{order_id}')\ndef get_order(order_id: int):\n    return {}\n\n"
                    "def legacy_checkout(cart):\n    pass\n"),
    "src/utils.py": "def helper():\n    pass\n",
    "Docs/api.md": ("# Cart API\n\nCall `cart.add_item(item, qty)`.\n\n- `GET /api/orders/{order_id}`\n\n"
                    "Use `legacy_checkout(cart)`. See [utils](../src/utils.py).\n"),
}


def make_pr(tmp_path):
    box = GitSandbox(tmp_path)
    box.write(BASE_FILES)
    box.commit("base")
    box.branch("feature")
    box.write({"src/cart.py": (
        "from fastapi import APIRouter\nrouter = APIRouter(prefix='/api')\n\n"
        "class Cart:\n    def add_item(self, item, quantity=1, coupon=None):\n        return 1\n\n"
        "@router.get('/v2/orders/{order_id}')\ndef get_order(order_id: int):\n    return {}\n")})
    box.remove("src/utils.py")
    box.commit("change api")
    return box


@pytestmark_git
def test_git_pull_request_is_analyzed_end_to_end(tmp_path):
    make_pr(tmp_path)
    report = run_on_git(tmp_path, "main", "HEAD", min_confidence=0.0)
    rules = sorted((e.rule_id, e.entity) for e in report.evidence)
    assert rules == [("DRIFT001", "legacy_checkout"), ("DRIFT003", "Cart.add_item"),
                     ("DRIFT005", "get_order"), ("DRIFT007", "src/utils.py")]
    assert report.commit_hash and len(report.commit_hash) == 40
    assert report.summary["files_changed"] == 2 and report.summary["documents_scanned"] == 1


@pytestmark_git
def test_diff_file_mode_gives_the_same_findings_as_git_mode(tmp_path):
    box = make_pr(tmp_path)
    diff_file = tmp_path.parent / (tmp_path.name + ".diff")
    diff_file.write_text(box.diff(), encoding="utf-8")
    from_git = run_on_git(tmp_path, "main", "HEAD", min_confidence=0.0)
    from_diff = run_on_diff_file(tmp_path, diff_file, min_confidence=0.0)
    key = lambda r: sorted((e.id, e.confidence) for e in r.evidence)  # noqa: E731
    assert key(from_git) == key(from_diff)


@pytestmark_git
def test_updating_the_documentation_in_the_pr_removes_the_drift(tmp_path):
    box = make_pr(tmp_path)
    box.write({"Docs/api.md": ("# Cart API\n\nCall `cart.add_item(item, quantity, coupon)`.\n\n"
                               "- `GET /api/v2/orders/{order_id}`\n")})
    box.commit("update docs")
    report = run_on_git(tmp_path, "main", "HEAD", min_confidence=0.0)
    assert report.evidence == []


@pytestmark_git
def test_cli_writes_reports_and_sets_exit_code(tmp_path, capsys):
    make_pr(tmp_path)
    out = tmp_path / "drift-out"
    code = main(["--repo", str(tmp_path), "--base", "main", "--output-dir", str(out),
                 "--format", "json", "--fail-on", "high"])
    assert code == 1
    data = json.loads((out / "drift-report.json").read_text(encoding="utf-8"))
    assert data["summary"]["drift_findings"] == len(data["evidence"]) >= 4
    assert "## Documentation Drift Report" in (out / "drift-report.md").read_text(encoding="utf-8")
    assert json.loads(capsys.readouterr().out)["schema_version"] == "1.0"
    assert main(["--repo", str(tmp_path), "--base", "main"]) == 0           # report only by default


@pytestmark_git
def test_cli_appends_to_the_github_step_summary(tmp_path, monkeypatch):
    make_pr(tmp_path)
    summary = tmp_path.parent / (tmp_path.name + "-summary.md")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    main(["--repo", str(tmp_path), "--base", "main", "--format", "json"])
    assert "Documentation Drift Report" in summary.read_text(encoding="utf-8")


@pytestmark_git
def test_cli_reports_usage_and_git_errors_with_exit_code_2(tmp_path, capsys):
    box = GitSandbox(tmp_path)
    box.write({"a.py": "x = 1\n"})
    box.commit("one")
    assert main(["--repo", str(tmp_path), "--base", "does-not-exist"]) == 2
    assert main(["--repo", str(tmp_path)]) == 2                              # neither --base nor --diff-file
    assert "drift: error" in capsys.readouterr().err


@pytestmark_git
def test_ignore_option_skips_documents(tmp_path):
    make_pr(tmp_path)
    report = run_on_git(tmp_path, "main", "HEAD", ignore=["Docs/*"], min_confidence=0.0)
    assert report.evidence == []


@pytestmark_git
def test_unchanged_code_and_docs_only_pr_has_no_drift(tmp_path):
    box = GitSandbox(tmp_path)
    box.write(BASE_FILES)
    box.commit("base")
    box.branch("docs-only")
    box.write({"Docs/api.md": BASE_FILES["Docs/api.md"] + "\nExtra paragraph.\n"})
    box.commit("docs")
    report = run_on_git(tmp_path, "main", "HEAD", min_confidence=0.0)
    assert report.evidence == [] and report.summary["entities_changed"] == 0


@pytestmark_git
def test_diff_file_mode_never_reads_outside_the_repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "secret.py").write_text("def secret(a):\n    pass\n", encoding="utf-8")
    diff = ("diff --git a/../secret.py b/../secret.py\n--- a/../secret.py\n+++ b/../secret.py\n"
            "@@ -1,2 +1,2 @@\n-def secret(a):\n+def secret(a, b):\n     pass\n")
    diff_file = tmp_path / "evil.diff"
    diff_file.write_text(diff, encoding="utf-8")
    report = run_on_diff_file(repo, diff_file)
    assert report.summary["entities_changed"] == 0
    assert any("content not available" in w for w in report.warnings)
