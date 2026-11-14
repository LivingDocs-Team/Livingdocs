"""LD-159 Display drift severity: a drift report as Markdown, grouped by severity.

Made to be pasted as a Pull Request comment or shown in the UI: the overall level and the action
it calls for, a count per level, then every finding under its level with *why* it has that level
(base rule and adjustments, each with the ids of its evidence) and the evidence itself.
"""
from typing import List, Optional

from .drift_models import SEVERITY_ORDER, DriftFinding, DriftReport, Severity
from .drift_severity import SCORE_BANDS, SEVERITY_LEVELS

ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}
MAX_EXCERPT_LINES = 12


def at_least(findings: List[DriftFinding], min_severity: Optional[Severity]) -> List[DriftFinding]:
    if min_severity is None:
        return list(findings)
    floor = SEVERITY_ORDER.index(min_severity)
    return [f for f in findings if SEVERITY_ORDER.index(f.severity) >= floor]


def badge(level: Severity) -> str:
    return f"{ICON[level.value]} **{SEVERITY_LEVELS[level.value]['label']}**"


def _where(f: DriftFinding) -> str:
    d = f.document
    if d.document_id:
        return f"`{d.path}` (saved document {d.title or d.document_id}, v{d.version})"
    return f"`{d.path}`"


def _why(f: DriftFinding) -> List[str]:
    a = f.severity_assessment
    if a is None:
        return [f"- **Why {f.severity.value}:** " + "; ".join(f.rules)]
    refs = lambda ids: f" [{', '.join(ids)}]" if ids else ""   # noqa: E731
    out = [f"- **Why {SEVERITY_LEVELS[a.level.value]['label']}** (score {a.score}):",
           f"  - {a.base_label}: starts at {a.base_level.value}{refs(a.base_evidence)}"]
    for s in a.adjustments:
        out.append(f"  - {s.label}: {'+' if s.delta > 0 else ''}{s.delta}{refs(s.evidence)}")
    if a.capped_at:
        out.append(f"  - capped at {a.capped_at.value} for {f.type.value} drift")
    return out


def _evidence(f: DriftFinding) -> List[str]:
    out = ["<details><summary>Evidence</summary>", ""]
    for e in f.evidence:
        if e.kind.value == "code_diff":
            where = f"`{e.path}:{e.line_start}`" if e.line_start else f"`{e.path}`"
            lines = (e.excerpt or "").splitlines()[:MAX_EXCERPT_LINES]
            out += [f"- **{e.id}** code diff {where}", "", "  ```diff", *[f"  {x}" for x in lines], "  ```"]
        elif e.kind.value == "documentation":
            out.append(f"- **{e.id}** `{e.path}:{e.line_start}` — {e.excerpt}")
        elif e.kind.value == "commit":
            sha = f"`{e.commit_sha[:7]}` " if e.commit_sha else ""
            link = f" ({e.url})" if e.url else ""
            out.append(f"- **{e.id}** commit {sha}{e.excerpt or ''}{link}")
        else:
            out.append(f"- **{e.id}** ticket {e.ticket}")
    return out + ["", "</details>"]


def render(report: DriftReport, min_severity: Optional[Severity] = None) -> str:
    pr = report.pull_request
    findings = at_least(report.findings, min_severity)
    title = f"PR #{pr.number}" + (f": {pr.title}" if pr.title else "")
    out = [f"## Documentation drift — {title}", ""]
    meta = [x for x in (f"repository `{report.repository}`" if report.repository else None,
                        f"commit `{pr.head_sha[:7]}`" if pr.head_sha else None,
                        "tickets " + ", ".join(report.tickets) if report.tickets else None) if x]
    if meta:
        out += [" · ".join(meta), ""]
    top = report.summary.highest_severity
    if top is None:
        out += ["✅ **No documentation drift.** The checked documentation matches the code.", ""]
        return "\n".join(out)
    out += [f"**Overall severity:** {badge(top)} (score {report.summary.severity_score}) — "
            f"{SEVERITY_LEVELS[top.value]['action']}", "",
            "| Severity | Findings | Meaning |", "|---|---:|---|"]
    for level in reversed(SEVERITY_ORDER):
        n = report.summary.by_severity.get(level.value, 0)
        lo, hi = SCORE_BANDS[level]
        out.append(f"| {ICON[level.value]} {SEVERITY_LEVELS[level.value]['label']} ({lo}-{hi}) | {n} | "
                   f"{SEVERITY_LEVELS[level.value]['meaning']} |")
    out.append("")
    if report.affected_documents:
        out += ["**Affected documentation:** " + ", ".join(
            f"`{a.path}` {ICON[a.severity.value] if a.severity else ''}".rstrip()
            for a in report.affected_documents), ""]
    if min_severity is not None:
        out += [f"_Showing {len(findings)} of {len(report.findings)} findings "
                f"({min_severity.value} and above)._", ""]
    for level in reversed(SEVERITY_ORDER):
        group = [f for f in findings if f.severity == level]
        if not group:
            continue
        out += [f"### {ICON[level.value]} {SEVERITY_LEVELS[level.value]['label']} ({len(group)})", ""]
        for f in group:
            name = f" — `{f.entity}`" if f.entity else ""
            flag = " · breaking" if f.breaking else ""
            out += [f"#### {f.id} · {f.type.value.capitalize()} · {f.kind}{flag}{name}", "",
                    f.message, "",
                    f"- **Where:** {_where(f)}",
                    *_why(f),
                    f"- **Suggestion:** {f.suggestion}",
                    f"- **Confidence:** {f.confidence:.2f} ({f.confidence_level})", "",
                    *_evidence(f), ""]
    return "\n".join(out).rstrip() + "\n"



