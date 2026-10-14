"""Confidence scores for generated documentation (LD-340).

A score in [0, 1] is computed per documented entity, then averaged per file and
per job. It does NOT rely on the AI grading itself alone: most of the weight comes
from signals we can check.

AI-written description:
    score = 0.30 * input_quality      how much the analysis tells us (source, docstring, types)
          + 0.30 * grounding          1 = cited its own code, 0.5 = cited only other evidence, 0 = none
          + 0.20 * described          1 = the AI actually described the entity
          + 0.20 * self_assessed      the AI's own 0-1 estimate (0.5 when missing)
          - 0.10 if it cited ids that do not exist in the evidence catalog

No AI description (offline mode or fallback after AI errors):
    score = 0.60 * input_quality      the doc only restates extracted facts and docstrings

Levels: high >= 0.75, medium >= 0.50, low < 0.50.
"""
from typing import Dict, List, Optional, Union

from .doc_schema import ClassDoc, EndpointDoc, FunctionDoc
from .evidence import Entity, EvidenceCatalog
from .models import (ClassInfo, ConfidenceLevel, Endpoint, EntityReport, Function)

METHOD = ("AI: 0.30 input quality + 0.30 evidence grounding + 0.20 described + 0.20 AI "
          "self-assessment, -0.10 for invalid citations; without AI: 0.60 x input quality. "
          "Levels: high >= 0.75, medium >= 0.50, low < 0.50.")

W_INPUT, W_GROUND, W_DESCRIBED, W_SELF = 0.30, 0.30, 0.20, 0.20
INVALID_CITATION_PENALTY = 0.10
NO_AI_FACTOR = 0.60
DEFAULT_SELF = 0.5

ItemDoc = Union[ClassDoc, FunctionDoc, EndpointDoc]


def level_of(score: Optional[float]) -> Optional[ConfidenceLevel]:
    if score is None:
        return None
    if score >= 0.75:
        return ConfidenceLevel.high
    if score >= 0.50:
        return ConfidenceLevel.medium
    return ConfidenceLevel.low


def _typed_ratio(fn: Function) -> float:
    slots = len(fn.parameters) + 1
    typed = sum(1 for p in fn.parameters if p.type) + (1 if fn.return_type else 0)
    return typed / slots


def input_quality(obj) -> float:
    """0-1: how much the analysis gives the writer to work with."""
    if isinstance(obj, Function):
        signals = [1.0 if obj.source else 0.0, 1.0 if obj.docstring else 0.0, _typed_ratio(obj)]
    elif isinstance(obj, ClassInfo):
        src = (sum(1 for m in obj.methods if m.source) / len(obj.methods)) if obj.methods else 0.0
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

    if not ai_mode:
        score = NO_AI_FACTOR * q
        factors["ai_described"] = 0.0
    else:
        described = 1.0 if (doc is not None and doc.summary.strip()) else 0.0
        found, unknown = catalog.resolve(doc.evidence if doc else [])
        found_ids = {e.id for e in found}
        grounding = 1.0 if (own and own.id in found_ids) else (0.5 if found else 0.0)
        self_score = doc.confidence if (doc is not None and doc.confidence is not None) else DEFAULT_SELF
        penalty = INVALID_CITATION_PENALTY if unknown else 0.0
        score = (W_INPUT * q + W_GROUND * grounding + W_DESCRIBED * described
                 + W_SELF * self_score - penalty)
        evidence += [e for e in found if not own or e.id != own.id]
        factors.update({"grounding": grounding, "ai_described": described,
                        "self_assessed": round(self_score, 2),
                        "invalid_citations": float(len(unknown))})

    score = round(max(0.0, min(1.0, score)), 2)
    return EntityReport(kind=ent.kind, name=ent.key, confidence=score, level=level_of(score),
                        evidence=evidence, factors=factors)


def average(scores: List[float]) -> Optional[float]:
    return round(sum(scores) / len(scores), 2) if scores else None
