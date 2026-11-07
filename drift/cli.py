"""Command line entry point:  python -m drift --base origin/main --head HEAD"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from .detector import HIGH, MEDIUM
from .evidence import DriftReport
from .gitio import GitError
from .pipeline import DEFAULT_MIN_CONFIDENCE
from .report import render_markdown
from .sources import run_on_diff_file, run_on_git

THRESHOLDS = {"none": None, "low": 0.0, "medium": MEDIUM, "high": HIGH}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="drift", description="Detect documentation drift caused by a pull request.")
    p.add_argument("--repo", default=".", help="repository root (default: current directory)")
    src = p.add_argument_group("pull request source (choose one)")
    src.add_argument("--base", help="base revision, e.g. origin/main (uses git)")
    src.add_argument("--head", default="HEAD", help="head revision (default: HEAD)")
    src.add_argument("--diff-file", help="unified diff of the PR; the working tree is taken as the PR head")
    p.add_argument("--ignore", action="append", default=[], metavar="GLOB",
                   help="documentation files to skip (repeatable); CHANGELOG* is always skipped")
    p.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE,
                   help=f"hide findings below this confidence (default {DEFAULT_MIN_CONFIDENCE})")
    p.add_argument("--format", choices=["markdown", "json", "both"], default="markdown")
    p.add_argument("--output-dir", help="write drift-report.json / drift-report.md here")
    p.add_argument("--fail-on", choices=list(THRESHOLDS), default="none",
                   help="exit with status 1 when a finding of at least this severity exists (default: never)")
    p.add_argument("--repository", help="repository name stored in the report (default: folder name)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo).resolve()
    try:
        report = _run(args, repo_root)
    except (GitError, OSError, ValueError) as exc:
        print(f"drift: error: {exc}", file=sys.stderr)
        return 2

    markdown = render_markdown(report)
    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "drift-report.json").write_text(report.to_json(), encoding="utf-8")
        (out / "drift-report.md").write_text(markdown, encoding="utf-8")
    if args.format in ("json", "both"):
        print(report.to_json())
    if args.format in ("markdown", "both"):
        print(markdown)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(markdown)

    threshold = THRESHOLDS[args.fail_on]
    if threshold is not None and any(e.confidence >= threshold for e in report.evidence):
        return 1
    return 0


def _run(args: argparse.Namespace, root: Path) -> DriftReport:
    if bool(args.base) == bool(args.diff_file):
        raise ValueError("give either --base (git mode) or --diff-file")
    ignore = list(args.ignore)
    if args.output_dir:   # never scan our own reports
        try:
            ignore.append(Path(args.output_dir).resolve().relative_to(root).as_posix() + "/*")
        except ValueError:
            pass
    common = dict(ignore=ignore, min_confidence=args.min_confidence, repository=args.repository)
    if args.diff_file:
        return run_on_diff_file(root, Path(args.diff_file), **common)
    return run_on_git(root, args.base, args.head, **common)


if __name__ == "__main__":
    sys.exit(main())
