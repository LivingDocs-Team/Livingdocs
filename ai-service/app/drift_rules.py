"""LD-151 shared pieces of the drift classifiers (LD-152 referential, LD-153 signature,
LD-154 semantic): the result of classifying one hit and small severity helpers."""
from typing import List, Optional, Tuple

from .drift_models import DriftType, Severity

PARAM_WINDOW = 25        # documentation lines after a mention of the entity that describe it
BIG_CHANGE_LINES = 15


class Classified:
    """Result of classifying one hit. The severity is not decided here: `base` names the base rule
    and `adjust` the adjustments (rule id, documentation passages that prove it) of
    app.drift_severity.RULES (LD-157); drift.detect() turns them into a SeverityAssessment."""

    def __init__(self, type_: DriftType, kind: str, base: str, change: str, message: str,
                 suggestion: str, before: Optional[str] = None, after: Optional[str] = None,
                 certainty: float = 1.0, breaking: bool = False,
                 adjust: Optional[List[Tuple[str, list]]] = None,
                 details: Optional[list] = None) -> None:
        self.type, self.kind, self.base, self.change = type_, kind, base, change
        self.message, self.suggestion = message, suggestion
        self.before, self.after, self.certainty = before, after, certainty
        self.breaking = breaking
        self.adjust = adjust or []
        self.details = details or []    # DocMatch: what the documentation still says (evidence)
        self.severity: Optional[Severity] = None      # set by drift_severity.assess


def private(name: Optional[str]) -> bool:
    if not name or " " in name:
        return False
    short = name.rsplit(".", 1)[-1]
    return short.startswith("_") and not short.startswith("__")


def code(s: Optional[str]) -> str:
    return f"`{s}`" if s else "-"



