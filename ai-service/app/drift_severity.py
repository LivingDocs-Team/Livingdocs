"""LD-156 Drift severity assessment.

LD-157 Implement drift severity rules
    One table, RULES, holds every rule that decides how severe a drift finding is. A classifier
    (LD-152 / LD-153 / LD-154) only says which *base* rule applies and which *adjustments* apply,
    each with the documentation passages that prove it. Nothing else sets a severity.

        base rule      the starting level, from what changed and where it is documented
        adjustment     +1 / -1 level, e.g. the documentation still states the old detail (+1),
                       a private name (-1), an uncertain match (-1)
        cap            the highest level of a drift type (semantic: High)

LD-158 Implement severity classification
    The level is turned into a score 0-100 inside its band, so findings of the same level are
    ordered by confidence, and classify_score() maps any score back to a level:

        Low 0-24 | Medium 25-49 | High 50-74 | Critical 75-100

    Each level has a meaning and a recommended action (SEVERITY_LEVELS). A document part and the
    whole report take the level of their most severe finding.

LD-159 / evidence
    Every assessment lists the base rule and each adjustment with the ids of the evidence that
    supports it (X1 code diff, D1.. documentation passages), so the UI and the Markdown report can
    show *why* a finding has its level.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .drift_models import (SEVERITY_ORDER, DocMatch, DriftEvidence, DriftType, Severity,
                           SeverityAdjustment, SeverityAssessment)

UNCERTAIN_CONFIDENCE = 0.5     # below: the documentation names the code only weakly


@dataclass(frozen=True)
class Rule:
    id: str
    kind: str                    # base | adjustment
    label: str                   # short text, also used in DriftFinding.rules
    description: str
    level: Optional[Severity] = None     # base rules
    delta: int = 0                       # adjustments


def _base(id_: str, level: Severity, label: str, description: str) -> Rule:
    return Rule(id_, "base", label, description, level=level)


def _adj(id_: str, delta: int, label: str, description: str) -> Rule:
    return Rule(id_, "adjustment", label, description, delta=delta)


RULES: Dict[str, Rule] = {r.id: r for r in [
    # ---------- base rules: referential (LD-152) ----------
    _base("endpoint_gone", Severity.critical, "documented endpoint removed or moved",
          "An HTTP endpoint the documentation describes no longer exists at that method and path: "
          "clients written from the documentation fail."),
    _base("entity_gone", Severity.high, "documented code removed or renamed",
          "A class, function or method the documentation describes was removed or renamed: code "
          "written from the documentation no longer works."),
    _base("file_section_removed", Severity.high, "section of a deleted file",
          "The documented file was deleted: the whole section is obsolete."),
    _base("file_reference_removed", Severity.medium, "mention of a deleted file",
          "A link, path or module name of a file the Pull Request deletes."),
    _base("file_reference_moved", Severity.medium, "old path of a moved file",
          "A link, path or module name of a file that moved: readers land on a missing file."),
    _base("own_section_moved", Severity.low, "the moved file's own section",
          "The section generated from the moved file still shows its old path."),
    _base("line_reference_changed", Severity.medium, "line reference into changed lines",
          "A line reference (path:12-30) points at lines the Pull Request changed."),
    _base("line_reference_shifted", Severity.low, "line reference shifted",
          "A line reference still points at the same code, which moved to other line numbers."),
    # ---------- base rules: signature (LD-153) ----------
    _base("breaking_signature", Severity.medium, "breaking change",
          "Documented usage stops working: a parameter was removed, renamed, made required or "
          "changed type, the order changed, or the return type, HTTP method or contract changed."),
    _base("compatible_signature", Severity.low, "not breaking",
          "The documented usage still works (optional parameter added, default changed) but the "
          "documentation is incomplete."),
    # ---------- base rules: semantic (LD-154) ----------
    _base("behaviour_changed", Severity.low, "behaviour change",
          "Same signature, different behaviour: the description may be outdated."),
    _base("undocumented_entity", Severity.low, "new entity not documented",
          "New code in a documented file that its section does not describe."),
    # ---------- adjustments ----------
    _adj("public_endpoint", +1, "HTTP endpoint",
         "The changed contract belongs to an HTTP endpoint used by other services and clients."),
    _adj("doc_states_old_detail", +1, "documentation still states the old detail",
         "The documentation still shows the removed parameter, the old type or default, the old "
         "status code, exception, value or docstring (see the evidence)."),
    _adj("contract_behaviour", +1, "callers see different results",
         "Status codes, exceptions or the documented description (docstring) changed."),
    _adj("large_change", +1, "large change",
         "15 or more changed lines inside the entity."),
    _adj("private_name", -1, "private name",
         "A private name (_name) is rarely used outside its module."),
    _adj("uncertain_match", -1, "uncertain match",
         f"The documentation names the code only weakly (confidence < {UNCERTAIN_CONFIDENCE}), "
         "for example a bare method name in prose."),
]}

CAPS: Dict[str, Severity] = {DriftType.semantic.value: Severity.high}

BASE_RULE_OF_KIND: Dict[str, Tuple[str, ...]] = {
    "endpoint_removed": ("endpoint_gone",), "endpoint_moved": ("endpoint_gone",),
    "entity_removed": ("entity_gone",), "entity_renamed": ("entity_gone",),
    "file_removed": ("file_section_removed", "file_reference_removed"),
    "module_removed": ("file_reference_removed",),
    "file_moved": ("file_reference_moved", "own_section_moved"),
    "module_moved": ("file_reference_moved", "own_section_moved"),
    "line_reference_stale": ("line_reference_changed", "line_reference_shifted"),
    "status_codes_changed": ("behaviour_changed",), "exceptions_changed": ("behaviour_changed",),
    "values_changed": ("behaviour_changed",), "docstring_changed": ("behaviour_changed",),
    "implementation_changed": ("behaviour_changed",),
    "undocumented_entity": ("undocumented_entity",),
}
"""Base rules a kind may use (signature kinds: breaking_signature / compatible_signature)."""

# ---------- LD-158 classification ----------

SCORE_BANDS: Dict[Severity, Tuple[int, int]] = {
    Severity.low: (0, 24), Severity.medium: (25, 49), Severity.high: (50, 74),
    Severity.critical: (75, 100),
}

SEVERITY_LEVELS: Dict[str, Dict[str, str]] = {
    "critical": {"label": "Critical", "meaning": "The documentation describes an API that no longer "
                 "exists or works: anyone following it fails.",
                 "action": "Fix the documentation before merging the Pull Request."},
    "high": {"label": "High", "meaning": "Documented code was removed, renamed or changed in a "
             "breaking way, and the documentation still shows the old version.",
             "action": "Update the documentation in this Pull Request or right after it."},
    "medium": {"label": "Medium", "meaning": "The documentation is partly wrong: an old path, a "
               "changed contract or behaviour it still describes.",
               "action": "Update the documentation before the next release."},
    "low": {"label": "Low", "meaning": "The documentation is incomplete or slightly out of date "
            "(new optional parameter, moved line numbers, undocumented code).",
            "action": "Review when convenient."},
}


def classify_score(score: int) -> Severity:
    """Map a score 0-100 to a level (LD-158)."""
    for level in reversed(SEVERITY_ORDER):
        if score >= SCORE_BANDS[level][0]:
            return level
    return Severity.low


def score_of(level: Severity, confidence: float) -> int:
    """A score inside the level's band: more confident findings rank higher."""
    lo, hi = SCORE_BANDS[level]
    mid = (lo + hi) // 2
    return max(lo, min(hi, mid + round((confidence - 0.5) * 20)))


def highest(levels: Sequence[Optional[Severity]]) -> Optional[Severity]:
    present = [lv for lv in levels if lv is not None]
    return max(present, key=SEVERITY_ORDER.index) if present else None


# ---------- LD-157 assessment ----------

def _evidence_ids(matches: Sequence[DocMatch], evidence: Sequence[DriftEvidence]) -> List[str]:
    ids = []
    for m in matches:
        for e in evidence:
            if e.kind.value == "documentation" and e.line_start == m.line and e.id not in ids:
                ids.append(e.id)
    return ids


def assess(type_: DriftType, base: str, adjustments: Sequence[Tuple[str, Sequence[DocMatch]]],
           confidence: float, evidence: Sequence[DriftEvidence]) -> SeverityAssessment:
    """Level, score and the reasons for one finding."""
    rule = RULES[base]
    code_ids = [e.id for e in evidence if e.kind.value == "code_diff"]
    doc_ids = [e.id for e in evidence if e.kind.value == "documentation"]
    steps: List[SeverityAdjustment] = []
    for rid, matches in adjustments:
        r = RULES[rid]
        steps.append(SeverityAdjustment(rule=rid, delta=r.delta, label=r.label, reason=r.description,
                                        evidence=_evidence_ids(matches, evidence) or code_ids))
    if confidence < UNCERTAIN_CONFIDENCE:
        r = RULES["uncertain_match"]
        steps.append(SeverityAdjustment(rule=r.id, delta=r.delta, label=r.label,
                                        reason=r.description, evidence=doc_ids[:1]))
    i = SEVERITY_ORDER.index(rule.level) + sum(s.delta for s in steps)
    cap = CAPS.get(type_.value)
    top = SEVERITY_ORDER.index(cap) if cap else len(SEVERITY_ORDER) - 1
    level = SEVERITY_ORDER[max(0, min(i, top))]
    capped = cap if cap is not None and i > top else None
    parts = [f"{rule.label} ({rule.level.value})"] + [
        f"{s.label} ({'+' if s.delta > 0 else ''}{s.delta})" for s in steps]
    if capped:
        parts.append(f"capped at {cap.value} for {type_.value} drift")
    return SeverityAssessment(
        level=level, score=score_of(level, confidence), base_rule=base, base_level=rule.level,
        base_label=rule.label, base_reason=rule.description,
        base_evidence=code_ids + doc_ids[:1], adjustments=steps, capped_at=capped,
        summary=f"{SEVERITY_LEVELS[level.value]['label']}: " + ", ".join(parts) + ".")


def rule_strings(a: SeverityAssessment) -> List[str]:
    """Short form kept in DriftFinding.rules (LD-151)."""
    out = [f"{a.base_label}: {a.base_level.value}"]
    out += [f"{s.label}: {'+' if s.delta > 0 else ''}{s.delta}" for s in a.adjustments]
    if a.capped_at:
        out.append(f"capped at {a.capped_at.value}")
    return out


def rules_table() -> List[dict]:
    """GET /drift/severity-rules: every rule, for the UI legend and the documentation."""
    return [{"id": r.id, "kind": r.kind, "label": r.label, "description": r.description,
             "level": r.level.value if r.level else None, "delta": r.delta} for r in RULES.values()]



