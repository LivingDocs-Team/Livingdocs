"""Documentation drift detection for pull requests (LD-145).

LD-146  pr_analyzer / diff_parser / entities  - analyze pull request changes
LD-148  doc_scanner / affected                - identify affected documentation
LD-147  detector                              - detect documentation drift
LD-149  evidence / report                     - generate drift evidence
"""
from .evidence import DriftEvidence, DriftReport
from .pipeline import run_drift_detection

__all__ = ["run_drift_detection", "DriftReport", "DriftEvidence"]
