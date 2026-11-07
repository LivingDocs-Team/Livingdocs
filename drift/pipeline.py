"""High-level API: run the whole drift pipeline (analyze -> identify -> detect -> evidence)."""
from __future__ import annotations

import datetime as _dt
from typing import Callable, Mapping, Optional

from .affected import identify_affected_documentation
from .detector import detect_drift
from .doc_scanner import build_index
from .evidence import DriftReport, build_report
from .pr_analyzer import analyze_pull_request

DEFAULT_MIN_CONFIDENCE = 0.3


def run_drift_detection(diff_text: str,
                        read_old: Callable[[str], Optional[str]],
                        read_new: Callable[[str], Optional[str]],
                        docs: Mapping[str, str], *,
                        base: Optional[str] = None, head: Optional[str] = None,
                        repository: Optional[str] = None, commit: Optional[str] = None,
                        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
                        now: Optional[_dt.datetime] = None) -> DriftReport:
    """docs maps a repository path to the content of a documentation file at the PR head."""
    analysis = analyze_pull_request(diff_text, read_old, read_new, base=base, head=head)
    index = build_index(docs)
    affected = identify_affected_documentation(index, analysis)
    findings = detect_drift(index, analysis, min_confidence=min_confidence)
    return build_report(findings, affected, index, analysis, repository=repository, commit=commit, now=now)
