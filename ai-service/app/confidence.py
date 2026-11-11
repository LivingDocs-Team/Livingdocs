"""Confidence scores for generated documentation (LD-340) and drift findings (LD-147).

A score in [0, 1] is computed per documented entity, then averaged per file and
per job. It does NOT rely on the AI grading itself alone: most of the weight comes
from signals we can check.

AI-written description:
    score = 0.30 * input_quality      how much the analysis tells us (source, docstring, types)
          + 0.30 * grounding          1 = cited its own code, 0.5 = cited only other evidence, 0 = none
          + 0.20 * described          1 = the AI actually described the entity
          + 0.20 * self_assessed      the AI's own 0-1 estimate (0.5 when missing or not a number)
          - 0.10 per cited id that does not exist in the evidence catalog (at most 0.30)

No AI description (offline mode or fallback after AI errors):
    score = 0.60 * input_quality      the doc only restates extracted facts and docstrings

Missing evidence: an entity without its own source evidence is multiplied by 0.70, so it can
never be rated high.

LD-356 Implement AI confidence scoring - the rules every score follows (generation and drift):

    bounded        bounded() is the only way a score leaves this module: NaN / infinity / not a
                   number -> 0, clamped to [0, 1], rounded half-up to 2 decimals (0.745 -> 0.75),
                   so the same input always gives the same score on every machine
    thresholds     HIGH and MEDIUM are defined once here; level_of() takes the level from the
                   rounded score, so the level always matches the score that is shown. Drift
                   severity (UNCERTAIN_CONFIDENCE) and the Markdown renderer use the same values
    unknown ids    penalised per id (citation_penalty), never ignored silently
    missing evidence  lowers the score (MISSING_EVIDENCE_FACTOR) instead of passing unnoticed

Levels: high >= 0.75, medium >= 0.50, low < 0.50.
"""
import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Union

from .doc_schema import ClassDoc, EndpointDoc, FunctionDoc
from .evidence import Entity, EvidenceCatalog
from .models import (ClassInfo, ConfidenceLevel, Endpoint, EntityReport, Function)

HIGH, MEDIUM = 0.75, 0.50                 # level thresholds (score >= HIGH: high, >= MEDIUM: medium)
LEVELS_TEXT = f"Levels: high >= {HIGH:.2f}, medium >= {MEDIUM:.2f}, low < {MEDIUM:.2f}."

W_INPUT, W_GROUND, W_DESCRIBED, W_SELF = 0.30, 0.30, 0.20, 0.20
INVALID_CITATION_PENALTY = 0.10           # per unknown evidence id ...
MAX_CITATION_PENALTY = 0.30               # ... at most
MISSING_EVIDENCE_FACTOR = 0.70            # no evidence of its own: never high
NO_AI_FACTOR = 0.60
DEFAULT_SELF = 0.5

METHOD = (f"AI: {W_INPUT:.2f} input quality + {W_GROUND:.2f} evidence grounding + "
          f"{W_DESCRIBED:.2f} described + {W_SELF:.2f} AI self-assessment, "
          f"-{INVALID_CITATION_PENALTY:.2f} per invalid citation (max {MAX_CITATION_PENALTY:.2f}); "
          f"without AI: {NO_AI_FACTOR:.2f} x input quality; x{MISSING_EVIDENCE_FACTOR:.2f} without "
          f"own evidence. Scores are bounded to 0-1 and rounded half-up to 2 decimals. " + LEVELS_TEXT)

ItemDoc = Union[ClassDoc, FunctionDoc, EndpointDoc]


def bounded(score: Any) -> float:
    """LD-356: a score in [0, 1], rounded half-up to 2 decimals; NaN, infinity or anything that
    is not a number counts as 0 (no confidence), never as an error or as full confidence."""
    try:
        x = float(score)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(x):
        return 0.0
    x = min(1.0, max(0.0, x))
    # round(…, 6) first removes binary noise (0.7449999999999999 is 0.745), then half-up
    return float(Decimal(repr(round(x, 6))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def level_of(score: Optional[float]) -> Optional[ConfidenceLevel]:
    """The level of the score as it is shown (2 decimals): 0.7449 -> 0.74 medium, 0.745 -> 0.75 high."""
    if score is None:
        return None
    s = bounded(score)
    if s >= HIGH:
        return ConfidenceLevel.high
    if s >= MEDIUM:
        return ConfidenceLevel.medium
    return ConfidenceLevel.low


def citation_penalty(unknown: int) -> float:
    """LD-356: what citing `unknown` ids that are not in the evidence costs."""
    return min(MAX_CITATION_PENALTY, INVALID_CITATION_PENALTY * max(0, unknown))


def _typed_ratio(fn: Function) -> float:
    slots = len(fn.parameters) + 1
    typed = sum(1 for p in fn.parameters if p.type) + (1 if fn.return_type else 0)
    return typed / slots


def input_quality(obj) -> float:
    """0-1: how much the analysis gives the writer to work with."""
    if isinstance(obj, Function):
        signals = [1.0 if obj.source else 0.0, 1.0 if obj.docstring else 0.0, _typed_ratio(obj)]
    elif isinstance(obj, ClassInfo):
        members = []
        if obj.methods:
            members.append(sum(1 for m in obj.methods if m.source) / len(obj.methods))
        if obj.fields:   # data classes (pydantic, DTO, record, enum) are described by their fields
            members.append(sum(1 for x in obj.fields if x.type or x.description or obj.kind == "enum")
                           / len(obj.fields))
        src = sum(members) / len(members) if members else 0.0
        signals = [1.0 if obj.docstring else 0.0, src]
    elif isinstance(obj, Endpoint):
        typed = (sum(1 for p in obj.parameters if p.type) / len(obj.parameters)) if obj.parameters else 1.0
        signals = [1.0 if obj.handler else 0.0, 1.0 if obj.response else 0.0, typed]
    else:
        return 0.0
    return sum(signals) / len(signals)


def score_entity(ent: Entity, doc: Optional[ItemDoc], catalog: EvidenceCatalog,
                 ai_mode: bool) -> EntityReport:
    own = catalog.own.get(ent.key)
    q = input_quality(ent.obj)
    evidence = [own] if own else []
    factors: Dict[str, float] = {"input_quality": round(q, 2)}
    penalty = 0.0

    if not ai_mode:
        score = NO_AI_FACTOR * q
        factors["ai_described"] = 0.0
    else:
        described = 1.0 if (doc is not None and doc.summary.strip()) else 0.0
        found, unknown = catalog.resolve(doc.evidence if doc else [])
        found_ids = {e.id for e in found}
        grounding = 1.0 if (own and own.id in found_ids) else (0.5 if found else 0.0)
        self_score = doc.confidence if (doc is not None and doc.confidence is not None) else DEFAULT_SELF
        penalty = citation_penalty(len(unknown))
        score = (W_INPUT * q + W_GROUND * grounding + W_DESCRIBED * described
                 + W_SELF * self_score)
        evidence += [e for e in found if not own or e.id != own.id]
        factors.update({"grounding": grounding, "ai_described": described,
                        "self_assessed": round(self_score, 2),
                        "invalid_citations": float(len(unknown))})

    if own is None:                     # LD-356: nothing of its own to check the text against
        score *= MISSING_EVIDENCE_FACTOR
    factors["own_evidence"] = 1.0 if own else 0.0
    score = bounded(score - penalty)
    return EntityReport(kind=ent.kind, name=ent.key, confidence=score, level=level_of(score),
                        evidence=evidence, factors=factors)


def average(scores: List[Optional[float]]) -> Optional[float]:
    """Mean of the known scores (None is skipped), bounded like every other score."""
    known = [s for s in scores if s is not None]
    return bounded(sum(known) / len(known)) if known else None
