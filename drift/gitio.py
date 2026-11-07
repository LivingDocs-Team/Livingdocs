"""Reading a pull request from a git checkout (no shell, no network)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional


class GitError(RuntimeError):
    pass


class GitRepo:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _run(self, *args: str, check: bool = True) -> Optional[str]:
        proc = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=self.root,
                              capture_output=True)
        if proc.returncode != 0:
            if check:
                raise GitError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
            return None
        return proc.stdout.decode("utf-8", errors="replace")

    @staticmethod
    def _safe_ref(ref: str) -> str:
        if not ref or ref.startswith("-"):
            raise GitError(f"invalid git revision: {ref!r}")
        return ref

    def rev_parse(self, ref: str) -> str:
        return (self._run("rev-parse", "--verify", "--end-of-options", self._safe_ref(ref) + "^{commit}") or "").strip()

    def merge_base(self, base: str, head: str) -> str:
        out = self._run("merge-base", self._safe_ref(base), self._safe_ref(head), check=False)
        return (out or self.rev_parse(base)).strip()

    def diff(self, base_sha: str, head_sha: str) -> str:
        return self._run("diff", "--no-color", "--no-ext-diff", "--find-renames", "-U3",
                         base_sha, head_sha, "--") or ""

    def show(self, rev: str, path: str) -> Optional[str]:
        return self._run("show", f"{rev}:{path}", check=False)

    def list_files(self, rev: str) -> List[str]:
        out = self._run("ls-tree", "-r", "--name-only", rev) or ""
        return [l for l in out.splitlines() if l]
