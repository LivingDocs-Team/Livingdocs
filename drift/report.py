"""Markdown rendering of a DriftReport (for PR comments and the GitHub job summary)."""
from __future__ import annotations

import re
from typing import List

from .evidence import DriftEvidence, DriftReport

MAX_FINDINGS_DETAILED = 30
GITHUB_COMMENT_LIMIT = 60_000


def _fence(text: str, lang: str = "") -> str:
    longest = max([len(m.group(0)) for m in re.finditer(r"`+", text)] + [2])
    ticks = "`" * (longest + 1)
    return f"{ticks}{lang}\n{text}\n{ticks}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: DriftReport, max_detailed: int = MAX_FINDINGS_DETAILED) -> str:
    s = report.summary
    out: List[str] = ["## Documentation Drift Report", ""]
    if report.base or report.head:
        out.append(f"Compared `{report.base or '?'}` -> `{report.head or '?'}`"
                   + (f" (commit `{report.commit_hash[:10]}`)" if report.commit_hash else "") + "  ")
    out.append(f"{s['files_changed']} files changed, {s['entities_changed']} code entities changed "
               f"({s['api_changes']} affecting the public API), {s['documents_scanned']} documents scanned.")
    out.append("")

    if not report.evidence:
        out.append("**No documentation drift detected.**")
        if report.affected_documents:
            out += ["", "Documents that mention the changed code (still consistent): "
                    + ", ".join(f"`{d['path']}`" for d in report.affected_documents)]
    else:
        sev = s["by_severity"]
        out.append(f"**{s['drift_findings']} drift finding(s)** in {s['documents_with_drift']} document(s): "
                   f"{sev['high']} high, {sev['medium']} medium, {sev['low']} low.")
        out += ["", "| # | Severity | Document | Code | Rule | Confidence |", "|---|---|---|---|---|---|"]
        for n, e in enumerate(report.evidence, 1):
            out.append(f"| {n} | {e.severity.upper()} | `{_cell(e.doc.path)}:{e.doc.line}` | `{_cell(e.entity)}` "
                       f"| {e.rule_id} {e.drift_type} | {e.confidence:.2f} |")
        out.append("")
        for n, e in enumerate(report.evidence[:max_detailed], 1):
            out += _render_finding(n, e)
        if len(report.evidence) > max_detailed:
            out.append(f"_{len(report.evidence) - max_detailed} more finding(s) are listed in the table above "
                       f"and in the JSON report._")
            out.append("")

    if report.warnings:
        out += ["### Warnings", ""] + [f"- {w}" for w in report.warnings] + [""]
    out.append(f"<sub>Generated {report.generated_at} - schema {report.schema_version}</sub>")
    text = "\n".join(out) + "\n"
    if len(text) > GITHUB_COMMENT_LIMIT:
        text = text[:GITHUB_COMMENT_LIMIT - 200].rsplit("\n", 1)[0] + "\n\n_Report truncated; see the JSON report._\n"
    return text


def _render_finding(n: int, e: DriftEvidence) -> List[str]:
    out = [f"### {n}. `{e.entity}` - {e.drift_type} ({e.severity.upper()}, {e.confidence:.2f})", ""]
    out.append(f"- **Document:** `{e.doc.path}` line {e.doc.line}"
               + (f", section \"{e.doc.section}\"" if e.doc.section else "")
               + (" (document was edited in this PR)" if e.doc_updated_in_pr else ""))
    if e.code.start_line:
        out.append(f"- **Code:** `{e.code.file_path}:{e.code.start_line}-{e.code.end_line}` ({e.code.change_type})")
    else:
        out.append(f"- **Code:** `{e.code.file_path}` ({e.code.change_type})")
    out += [f"- **Why:** {r}" for r in e.reasons[:4]]
    out += [f"- **Fix:** {e.suggestion}", "", "<details><summary>Evidence</summary>", ""]
    excerpt = "\n".join(f"{'>' if x['highlight'] else ' '}{x['line']:>4} | {x['text']}" for x in e.doc.excerpt)
    out += [f"Documentation `{e.doc.path}`:", "", _fence(excerpt), ""]
    if e.code.before_signature != e.code.after_signature:
        out += ["Signature:", "", _fence(f"- {e.code.before_signature or '(none)'}\n+ {e.code.after_signature or '(none)'}", "diff"), ""]
    if e.code.diff_excerpt:
        out += [f"Diff of `{e.code.file_path}`:", "", _fence(e.code.diff_excerpt, "diff"), ""]
    out += ["</details>", ""]
    return out
