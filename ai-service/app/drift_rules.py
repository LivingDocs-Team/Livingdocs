"""LD-151 shared pieces of the drift classifiers (LD-152 referential, LD-153 signature,
LD-154 semantic): the result of classifying one hit and small severity helpers."""
from typing import List, Optional

from .drift_models import SEVERITY_ORDER, DriftType, Severity

PARAM_WINDOW = 25        # documentation lines after a mention of the entity that describe it
BIG_CHANGE_LINES = 15


class Classified:
    def __init__(self, type_: DriftType, kind: str, severity: Severity, change: str, message: str,
                 suggestion: str, before: Optional[str] = None, after: Optional[str] = None,
                 certainty: float = 1.0, breaking: bool = False,
                 rules: Optional[List[str]] = None, details: Optional[list] = None) -> None:
        self.type, self.kind, self.severity, self.change = type_, kind, severity, change
        self.message, self.suggestion = message, suggestion
        self.before, self.after, self.certainty = before, after, certainty
        self.breaking = breaking
        self.rules = rules or []
        self.details = details or []    # DocMatch: what the documentation still says (evidence)


def bump(sev: Severity, steps: int, cap: Severity = Severity.critical) -> Severity:
    i = max(0, min(SEVERITY_ORDER.index(sev) + steps, SEVERITY_ORDER.index(cap)))
    return SEVERITY_ORDER[i]


def private(name: Optional[str]) -> bool:
    if not name or " " in name:
        return False
    short = name.rsplit(".", 1)[-1]
    return short.startswith("_") and not short.startswith("__")


def code(s: Optional[str]) -> str:
    return f"`{s}`" if s else "-"
