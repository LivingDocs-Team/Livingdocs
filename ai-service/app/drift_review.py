"""LD-346 AI-based documentation drift analysis: AI review, explanations and resolution.

The rules (LD-347 comparison, LD-348 detection, LD-349 classification, LD-350 severity) decide
*what* drifted, its type and its severity, so a report is stable and auditable. The AI then
reviews the findings like a second reviewer (LD-351 evidence):

    verdict            confirmed | disputed | uncertain - it never changes type or severity
    explanation        plain language, citing the finding's own evidence ids (X1 code diff,
                       D1.. documentation lines); unknown ids are dropped, an explanation with no
                       valid citation is not trusted (verdict uncertain)
    suggested_update   the documentation text to write instead (from the evidence only)

One AI call reviews all findings of a report (the most severe first, at most MAX_REVIEWED);
invalid JSON is retried with a repair message, like the documentation generator (LD-340).
Without ANTHROPIC_API_KEY, or when the AI gives no valid answer, the review runs offline: the
explanation and the suggestion are built from the rules and the evidence, verdict not_reviewed.

Resolution: every finding starts `open`; reviewers set it to acknowledged, resolved or dismissed
(a dismissal needs a reason). The report's `review` shows the progress.
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

from .drift_models import (AIDriftReview, AIVerdict, DriftFinding, DriftReport, FindingResolution,
                           ResolutionEvent, ResolutionStatus, ResolutionUpdate, ReviewProgress,
                           ReviewStatus, now)
from .generator import AnthropicClient, LLMClient

log = logging.getLogger(__name__)

MAX_REVIEWED = 20
MAX_EXCERPT = 600

SYSTEM_PROMPT = """You review documentation drift findings for LivingDocs.
A rule-based detector compared a Pull Request's code changes with the project's documentation and
reported findings. For each finding decide, from its evidence only, whether the documentation is
really outdated:
- "confirmed": the documentation passage still describes the old code;
- "disputed": the passage is actually still correct (for example it already describes the new
  code, or it is about something else);
- "uncertain": the evidence does not settle it.
Explain in at most 60 words, for a developer, citing evidence ids in square brackets such as [X1]
or [D2]. Use only ids listed for that finding. Then give `suggested_update`: the documentation
text to write instead (one short Markdown passage built only from the evidence), or null when
the passage should simply be removed or when you dispute the finding.
Answer with JSON only: {"reviews": [{"id": "F1", "verdict": "...", "explanation": "...",
"evidence": ["X1", "D1"], "suggested_update": "..." | null}, ...]} - one entry per finding."""

REPAIR_PROMPT = ("Your answer was not valid: {error}. Answer again with JSON only, in the form "
                 '{{"reviews": [{{"id": "F1", "verdict": "confirmed|disputed|uncertain", '
                 '"explanation": "...", "evidence": ["X1"], "suggested_update": null}}]}}.')
CITATION = re.compile(r"\[([A-Z]\d+)\]")


class InvalidReview(ValueError):
    pass


# ---------- prompt ----------

def _evidence_lines(f: DriftFinding) -> List[str]:
    out = []
    for e in f.evidence:
        if e.kind.value == "code_diff":
            out.append(f"  {e.id} code diff {e.path}:{e.line_start or '?'}\n"
                       + "\n".join("      " + x for x in (e.excerpt or "")[:MAX_EXCERPT].splitlines()))
        elif e.kind.value == "documentation":
            out.append(f"  {e.id} documentation {e.path}:{e.line_start}: {e.excerpt}")
        elif e.kind.value == "commit":
            out.append(f"  {e.id} commit {(e.commit_sha or '')[:7]} {e.excerpt or ''}".rstrip())
        else:
            out.append(f"  {e.id} ticket {e.ticket}")
    return out


def build_prompt(report: DriftReport, findings: List[DriftFinding]) -> str:
    pr = report.pull_request
    parts = [f"Pull Request #{pr.number}: {pr.title}".rstrip(": "),
             f"Repository: {report.repository or '-'}", "", "Findings:"]
    for f in findings:
        parts += [f"- {f.id} [{f.type.value} / {f.kind}, severity {f.severity.value}] "
                  f"entity {f.entity or '-'} in documentation {f.document.path}",
                  f"  message: {f.message}"]
        if f.before or f.after:
            parts.append(f"  before: {f.before or '-'}  after: {f.after or '-'}")
        parts.append("  evidence:")
        parts += _evidence_lines(f)
    return "\n".join(parts)


# ---------- parsing ----------

def parse_reviews(text: str, findings: List[DriftFinding]) -> Tuple[Dict[str, AIDriftReview], List[str]]:
    """{finding id: review} from the AI's JSON; raises InvalidReview when it cannot be read."""
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidReview(f"not JSON ({exc.msg})")
    items = data.get("reviews") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise InvalidReview('missing "reviews" list')
    by_id = {f.id: f for f in findings}
    out: Dict[str, AIDriftReview] = {}
    warnings: List[str] = []
    for item in items:
        if not isinstance(item, dict) or item.get("id") not in by_id:
            continue
        f = by_id[item["id"]]
        try:
            verdict = AIVerdict(item.get("verdict"))
        except ValueError:
            verdict = AIVerdict.uncertain
        if verdict == AIVerdict.not_reviewed:
            verdict = AIVerdict.uncertain
        explanation = str(item.get("explanation") or "").strip()[:800]
        known = {e.id for e in f.evidence}
        cited = [x for x in dict.fromkeys([*(item.get("evidence") or []), *CITATION.findall(explanation)])
                 if isinstance(x, str)]
        unknown = [x for x in cited if x not in known]
        if unknown:
            warnings.append(f"{f.id}: AI cited unknown evidence {', '.join(unknown)}; ignored.")
        cited = [x for x in cited if x in known]
        for x in unknown:                       # remove made-up citations from the text
            explanation = re.sub(r"\s+([.,;:])", r"\1", explanation.replace(f"[{x}]", "")).strip()
        suggestion = item.get("suggested_update")
        suggestion = str(suggestion).strip()[:1500] if suggestion else None
        if not explanation or not cited:
            verdict = AIVerdict.uncertain       # not grounded in the evidence: not trusted
            suggestion = None
        out[f.id] = AIDriftReview(mode="ai", verdict=verdict, explanation=explanation, evidence=cited,
                                  suggested_update=suggestion if verdict != AIVerdict.disputed else None)
    if not out:
        raise InvalidReview("no review for any finding id")
    return out, warnings


# ---------- offline explanation (also the fallback) ----------

def offline_review(f: DriftFinding) -> AIDriftReview:
    """Explanation and suggested update built from the rules and the evidence only."""
    docs = [e for e in f.evidence if e.kind.value == "documentation"]
    code = [e for e in f.evidence if e.kind.value == "code_diff"]
    where = f"`{docs[0].path}:{docs[0].line_start}` [{docs[0].id}]" if docs else f"`{f.document.path}`"
    change = f" [{code[0].id}]" if code else ""
    a = f.severity_assessment
    why = f" It is {f.severity.value} because: {a.base_label}" + "".join(
        f", {s.label}" for s in a.adjustments) + "." if a else ""
    explanation = (f"{f.message} The code change{change} makes the passage at {where} outdated.{why}")
    suggestion = None
    if docs and f.before and f.after and f.before in (docs[0].excerpt or ""):
        suggestion = docs[0].excerpt.replace(f.before, f.after)
    elif docs and f.type.value == "referential" and f.after is None:
        suggestion = None                       # removed code: delete the passage
    return AIDriftReview(mode="offline", verdict=AIVerdict.not_reviewed, explanation=explanation,
                         evidence=[e.id for e in (code[:1] + docs[:1])], suggested_update=suggestion)


# ---------- reviewer ----------

class DriftReviewer:
    def __init__(self, client: Optional[LLMClient] = None, max_attempts: int = 2,
                 model: Optional[str] = None) -> None:
        self.client = client
        self.max_attempts = max(1, max_attempts)
        self.model = model

    @property
    def mode(self) -> str:
        return "ai" if self.client else "offline"

    def review(self, report: DriftReport) -> DriftReport:
        """Fill `ai_review` of every finding and the report's review progress."""
        for f in report.findings:
            f.ai_review = offline_review(f)
        chosen = report.findings[:MAX_REVIEWED]      # findings are ordered most severe first
        if self.client is not None and chosen:
            reviews, warnings = self._ask(report, chosen)
            report.warnings.extend(warnings)
            for f in chosen:
                if f.id in reviews:
                    r = reviews[f.id]
                    r.model = self.model
                    if r.suggested_update is None and r.verdict != AIVerdict.disputed:
                        r.suggested_update = f.ai_review.suggested_update
                    f.ai_review = r
            if len(report.findings) > MAX_REVIEWED:
                report.warnings.append(f"Only the {MAX_REVIEWED} most severe findings were reviewed by the AI.")
        refresh_progress(report, self.mode)
        return report

    def _ask(self, report: DriftReport, findings: List[DriftFinding]) -> Tuple[Dict[str, AIDriftReview], List[str]]:
        messages = [{"role": "user", "content": build_prompt(report, findings)}]
        warnings: List[str] = []
        for attempt in range(1, self.max_attempts + 1):
            try:
                text = self.client.complete(SYSTEM_PROMPT, messages)
            except Exception as exc:                 # API / network error
                log.warning("AI drift review failed (attempt %d): %s", attempt, exc)
                warnings.append(f"AI review failed (attempt {attempt}): {exc}")
                continue
            try:
                reviews, notes = parse_reviews(text, findings)
                return reviews, warnings + notes
            except InvalidReview as exc:
                warnings.append(f"AI review returned an invalid answer (attempt {attempt}): {exc}")
                messages = messages + [{"role": "assistant", "content": text or "(empty)"},
                                       {"role": "user", "content": REPAIR_PROMPT.format(error=exc)}]
        warnings.append("AI review unavailable; explanations were built from the rules and evidence.")
        return {}, warnings


def get_reviewer() -> DriftReviewer:
    if os.getenv("ANTHROPIC_API_KEY"):
        client = AnthropicClient()
        return DriftReviewer(client, max_attempts=int(os.getenv("LLM_MAX_ATTEMPTS", "2")),
                             model=client.model)
    return DriftReviewer(None)


# ---------- review progress and resolution ----------

def refresh_progress(report: DriftReport, ai_mode: Optional[str] = None) -> ReviewProgress:
    p = report.review
    counts = {s: 0 for s in ResolutionStatus}
    for f in report.findings:
        counts[f.resolution.status] += 1
    verdicts = [f.ai_review.verdict for f in report.findings if f.ai_review]
    p.open, p.acknowledged = counts[ResolutionStatus.open], counts[ResolutionStatus.acknowledged]
    p.resolved, p.dismissed = counts[ResolutionStatus.resolved], counts[ResolutionStatus.dismissed]
    p.ai_confirmed = verdicts.count(AIVerdict.confirmed)
    p.ai_disputed = verdicts.count(AIVerdict.disputed)
    p.ai_uncertain = verdicts.count(AIVerdict.uncertain)
    if ai_mode:
        p.ai_mode = ai_mode
    if not report.findings:
        p.status = ReviewStatus.not_required
    elif p.open == len(report.findings):
        p.status = ReviewStatus.pending
    elif p.open + p.acknowledged == 0:
        p.status = ReviewStatus.completed
    else:
        p.status = ReviewStatus.in_progress
    return p


class ResolutionError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def resolve(report: DriftReport, finding_id: str, update: ResolutionUpdate) -> DriftFinding:
    f = next((x for x in report.findings if x.id == finding_id), None)
    if f is None:
        raise ResolutionError(404, f"Finding '{finding_id}' not found in this report")
    note = (update.note or "").strip() or None
    if update.status == ResolutionStatus.dismissed and not note:
        raise ResolutionError(422, "A reason (note) is required to dismiss a finding")
    r: FindingResolution = f.resolution
    if r.status == update.status and r.note == note:
        return f                                   # no change: no new history entry
    at = now()
    r.history.append(ResolutionEvent(status=update.status, actor=update.actor, note=note, at=at))
    r.status, r.actor, r.note, r.updated_at = update.status, update.actor, note, at
    refresh_progress(report)
    return f
