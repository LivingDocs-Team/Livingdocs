"""Where a pull request comes from: a git range, or a diff file next to a checkout."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional

from .diff_parser import parse_unified_diff, reconstruct_old
from .doc_scanner import filter_doc_paths
from .evidence import DriftReport
from .gitio import GitRepo
from .pipeline import DEFAULT_MIN_CONFIDENCE, run_drift_detection

DEFAULT_IGNORE = ("CHANGELOG*", "node_modules/*", "drift-report*")


def run_on_git(root: Path, base: str, head: str = "HEAD", *, ignore: Iterable[str] = (),
               min_confidence: float = DEFAULT_MIN_CONFIDENCE,
               repository: Optional[str] = None) -> DriftReport:
    """Compare `head` with its merge base with `base`; documentation is read at `head`."""
    git = GitRepo(root)
    head_sha = git.rev_parse(head)
    base_sha = git.merge_base(base, head)
    diff_text = git.diff(base_sha, head_sha)
    paths = filter_doc_paths(git.list_files(head_sha), [*DEFAULT_IGNORE, *ignore])
    docs = {p: git.show(head_sha, p) or "" for p in paths}
    return run_drift_detection(
        diff_text, lambda p: git.show(base_sha, p), lambda p: git.show(head_sha, p), docs,
        base=base, head=head, repository=repository or Path(root).resolve().name,
        commit=head_sha, min_confidence=min_confidence)


def run_on_diff_file(root: Path, diff_file: Path, *, ignore: Iterable[str] = (),
                     min_confidence: float = DEFAULT_MIN_CONFIDENCE,
                     repository: Optional[str] = None) -> DriftReport:
    """The working tree under `root` is the PR head; old files are rebuilt from the diff."""
    root = Path(root).resolve()
    diff_text = Path(diff_file).read_text(encoding="utf-8", errors="replace")
    changes = {}
    for fc in parse_unified_diff(diff_text):
        changes[fc.path] = fc
        if fc.old_path:
            changes[fc.old_path] = fc

    def read_new(path: str) -> Optional[str]:
        target = (root / path).resolve()
        if root not in target.parents or not target.is_file():   # never read outside the repository
            return None
        return target.read_text(encoding="utf-8", errors="replace")

    def read_old(path: str) -> Optional[str]:
        fc = changes.get(path)
        return reconstruct_old(read_new(fc.path), fc) if fc else read_new(path)

    paths = filter_doc_paths(
        (p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()), [*DEFAULT_IGNORE, *ignore])
    docs: Dict[str, str] = {p: read_new(p) or "" for p in paths}
    return run_drift_detection(diff_text, read_old, read_new, docs, head="working tree",
                               repository=repository or root.name, min_confidence=min_confidence)
