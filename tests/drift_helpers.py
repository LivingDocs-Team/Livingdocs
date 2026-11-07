"""Helpers shared by the documentation drift tests (LD-150)."""
import difflib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

from drift import run_drift_detection

GIT_AVAILABLE = shutil.which("git") is not None


def make_diff(before: Dict[str, str], after: Dict[str, str]) -> str:
    """Build a git-style unified diff between two {path: content} snapshots."""
    out = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old == new:
            continue
        out.append(f"diff --git a/{path} b/{path}")
        if old is None:
            out.append("new file mode 100644")
        elif new is None:
            out.append("deleted file mode 100644")
        fromfile = "/dev/null" if old is None else f"a/{path}"
        tofile = "/dev/null" if new is None else f"b/{path}"
        out += list(difflib.unified_diff((old or "").splitlines(), (new or "").splitlines(),
                                         fromfile, tofile, lineterm=""))
    return "\n".join(out) + "\n"


def readers(before: Dict[str, str], after: Dict[str, str]):
    return before.get, after.get


def run(before: Dict[str, str], after: Dict[str, str], docs: Dict[str, str], **kwargs):
    """Run the whole pipeline on in-memory snapshots; `docs` are the documents at the PR head."""
    read_old, read_new = readers(before, after)
    kwargs.setdefault("min_confidence", 0.0)
    return run_drift_detection(make_diff(before, after), read_old, read_new, docs, **kwargs)


def find(report, rule_id: Optional[str] = None, entity: Optional[str] = None):
    return [e for e in report.evidence
            if (rule_id is None or e.rule_id == rule_id) and (entity is None or e.entity == entity)]


class GitSandbox:
    """A throw-away git repository with a `main` commit and helpers to add a PR commit."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "drift@example.test")
        self._git("config", "user.name", "Drift Test")
        self._git("config", "commit.gpgsign", "false")

    def _git(self, *args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull})
        assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"
        return proc.stdout

    def write(self, files: Dict[str, str]) -> None:
        for path, content in files.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def remove(self, *paths: str) -> None:
        for path in paths:
            (self.root / path).unlink()

    def commit(self, message: str) -> str:
        self._git("add", "-A")
        self._git("commit", "-q", "-m", message)
        return self._git("rev-parse", "HEAD").strip()

    def branch(self, name: str) -> None:
        self._git("checkout", "-q", "-b", name)

    def diff(self, base: str = "main", head: str = "HEAD") -> str:
        return self._git("diff", base, head)
