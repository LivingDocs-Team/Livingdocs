"""LD-145 Documentation drift detection (LD-147 detect / classify / rate).

Pipeline for one Pull Request:

    LD-146  drift_changes.analyze_pull_request   changed files -> changed code entities
    LD-148  drift_affected.find_affected         -> documentation parts that refer to them
    LD-147  classify (this module)               -> findings: type + severity + confidence
    LD-149  drift_evidence.build_evidence        -> code diff, doc passage, commit, ticket

Classification (BR-49):

    Referential  the documentation names code that is gone: a removed or renamed entity, an
                 endpoint path that moved, a deleted or moved source file
    Signature    the documentation describes an entity whose parameters, return type, fields or
                 endpoint contract changed
    Semantic     the entity keeps its signature but its body or docstring changed, or a new
                 entity was added to a documented file and is not described

Severity (Low < Medium < High < Critical):

    removed / renamed entity            High    (endpoint: Critical)
    signature changed                   Medium  (endpoint +1; the doc names a removed parameter +1)
    behaviour changed                   Low     (docstring changed +1; >= 15 changed lines +1)
    new entity not documented           Low
    section of a deleted file           High;   other mention of a deleted file: Medium
    moved file named in the docs        Medium; the moved file's own section: Low
    private names (_name)               -1      (never below Low)

Confidence (0-1, same levels as LD-340: high >= 0.75, medium >= 0.50):

    match      1.00 full name / path in code or a heading (or a removed parameter is named),
               0.80 full name in prose, or the bare method / file name in code of the file's own
               section, 0.65 bare name otherwise, 0.90 file-level finding on the file's section
    method     1.00 entity changes from the analyzer (before/after), 0.80 from the diff only
    location   1.00 section generated from the changed file, 0.85 other documentation
    certainty  1.00 removed / renamed / signature, 0.80 new entity, 0.70 behaviour change
"""
import threading
import uuid
from collections import Counter, OrderedDict
from typing import List, Optional, Tuple

from .confidence import level_of
from .drift_affected import FILE_REMOVED, FILE_RENAMED, DocText, Hit, collect_docs, entity_terms, \
    find_affected, search
from .drift_changes import analyze_pull_request
from .drift_evidence import build_evidence
from .drift_models import (SEVERITY_ORDER, AffectedDocument, DriftAnalyzeRequest, DriftFinding,
                           DriftReport, DriftReportSummary, DriftStatus, DriftSummary, DriftType,
                           EntityChangeType, PullRequestAnalysis, Severity)

METHOD = ("Entity changes from the analyzer's before/after results (or the diff), matched against "
          "saved documents and repository Markdown. Referential: removed/renamed code or moved "
          "files still named; Signature: documented parameters/contract changed; Semantic: "
          "behaviour changed or new code undocumented. Confidence = match x method x location x "
          "certainty; levels: high >= 0.75, medium >= 0.50, low < 0.50.")

BIG_CHANGE_LINES = 15


def _bump(sev: Severity, steps: int, cap: Severity = Severity.critical) -> Severity:
    i = max(0, min(SEVERITY_ORDER.index(sev) + steps, SEVERITY_ORDER.index(cap)))
    return SEVERITY_ORDER[i]


def _private(name: Optional[str]) -> bool:
    if not name or " " in name:
        return False
    short = name.rsplit(".", 1)[-1]
    return short.startswith("_") and not short.startswith("__")


def _code(s: Optional[str]) -> str:
    return f"`{s}`" if s else "-"


# ---------- LD-147: classify one hit ----------

class Classified:
    def __init__(self, type_: DriftType, severity: Severity, change: str, message: str,
                 suggestion: str, before: Optional[str] = None, after: Optional[str] = None,
                 certainty: float = 1.0) -> None:
        self.type, self.severity, self.change = type_, severity, change
        self.message, self.suggestion = message, suggestion
        self.before, self.after, self.certainty = before, after, certainty


def classify(hit: Hit) -> Optional[Classified]:
    t, f, c = hit.target, hit.target.file, hit.target.change
    where = "this section" if hit.documents_file else "the documentation"

    if t.file_event == FILE_REMOVED:
        if hit.documents_file:
            return Classified(DriftType.referential, Severity.high, FILE_REMOVED,
                              f"{where} documents {_code(f.path)}, which the Pull Request deletes.",
                              "Remove the section or move its content to the code that replaces it.",
                              before=f.path)
        return Classified(DriftType.referential, Severity.medium, FILE_REMOVED,
                          f"The documentation links or names {_code(f.path)}, "
                          "which the Pull Request deletes.",
                          f"Remove or replace the reference to {_code(f.path)}.", before=f.path)
    if t.file_event == FILE_RENAMED:
        if not hit.matches:
            return None
        sev = Severity.low if hit.documents_file else Severity.medium
        return Classified(DriftType.referential, sev, FILE_RENAMED,
                          f"{where.capitalize()} still names {_code(f.previous_path)}, "
                          f"moved to {_code(f.path)}.",
                          f"Replace {_code(f.previous_path)} with {_code(f.path)}.",
                          before=f.previous_path, after=f.path)
    if c is None:
        return None

    private = -1 if _private(c.name) else 0
    endpoint = c.kind == "endpoint"

    if c.change == EntityChangeType.added:
        if not hit.documents_file or private or f.status.value == "added":
            return None
        if search(hit.doc, entity_terms(c.kind, c.name), own_file=True):
            return None  # already described (e.g. the section was edited by hand)
        return Classified(DriftType.semantic, Severity.low, "added",
                          f"New {c.kind} {_code(c.name)} in {_code(f.path)} "
                          "is not described in this section.",
                          f"Document {_code(c.new_signature or c.name)}.", after=c.new_signature or c.name,
                          certainty=0.8)

    if not hit.matches:
        return None
    if c.change == EntityChangeType.removed:
        if f.status.value == "removed" and hit.documents_file:
            return None  # covered by the file-level finding of the deleted file
        sev = _bump(Severity.critical if endpoint else Severity.high, private)
        return Classified(DriftType.referential, sev, "removed",
                          f"{where.capitalize()} describes {c.kind} {_code(c.name)}, "
                          "which the Pull Request removes.",
                          f"Remove the description of {_code(c.name)} or point to its replacement.",
                          before=c.old_signature or c.name)
    if c.change == EntityChangeType.renamed:
        sev = _bump(Severity.critical if endpoint else Severity.high, private)
        return Classified(DriftType.referential, sev, "renamed",
                          f"{where.capitalize()} names {_code(c.old_name)}, renamed to {_code(c.name)}.",
                          f"Replace {_code(c.old_name)} with {_code(c.name)}.",
                          before=c.old_name, after=c.name)
    if c.change == EntityChangeType.signature_changed:
        sev = Severity.high if endpoint else Severity.medium
        if hit.param_matches:
            sev = _bump(sev, 1)
        sev = _bump(sev, private)
        detail = "; ".join(c.details)
        named = ""
        if hit.param_matches:
            named = " It still names removed parameter(s) " + ", ".join(
                _code(m.term) for m in hit.param_matches) + "."
        return Classified(DriftType.signature, sev, "signature_changed",
                          f"Signature of {c.kind} {_code(c.name)} changed ({detail}).{named}",
                          f"Update the documented signature to {_code(c.new_signature)}.",
                          before=c.old_signature, after=c.new_signature)
    if c.change == EntityChangeType.behavior_changed:
        steps = (1 if "docstring changed" in c.details else 0) \
            + (1 if c.changed_lines >= BIG_CHANGE_LINES else 0) + private
        sev = _bump(Severity.low, steps, cap=Severity.high)
        return Classified(DriftType.semantic, sev, "behavior_changed",
                          f"Behaviour of {c.kind} {_code(c.name)} changed ({'; '.join(c.details)}); "
                          f"{where} may describe the old behaviour.",
                          f"Check the description of {_code(c.name)} against the new code.",
                          before=c.old_signature, after=c.new_signature, certainty=0.7)
    return None


def _confidence(hit: Hit, cl: Classified) -> Tuple[float, dict]:
    t = hit.target
    exact = [m for m in hit.matches if m.exact]
    if hit.param_matches or any(m.in_code for m in exact):
        match = 1.0
    elif exact:
        match = 0.8
    elif hit.matches:   # only a bare method name / file name
        match = 0.8 if hit.documents_file and any(m.in_code for m in hit.matches) else 0.65
    else:
        match = 0.9     # file-level / undocumented finding on the file's own section
    method = 0.8 if (t.change is not None and t.change.source == "patch") else 1.0
    location = 1.0 if hit.documents_file else 0.85
    score = round(match * method * location * cl.certainty, 2)
    return score, {"match": match, "method": method, "location": location,
                   "certainty": cl.certainty}


def _part(hit: Hit) -> AffectedDocument:
    """The affected document part, with only this finding's matches."""
    d: DocText = hit.doc
    reasons = []
    if hit.documents_file:
        reasons.append(f"documents changed file {hit.target.file.path}")
    reasons += list(dict.fromkeys(f"mentions `{m.target}`" for m in hit.matches))
    return AffectedDocument(source=d.source, path=d.path, document_id=d.document_id, title=d.title,
                            version=d.version, documents_file=d.documents_file, reasons=reasons,
                            matches=sorted(hit.matches + hit.param_matches, key=lambda m: m.line))


def detect(analysis: PullRequestAnalysis, hits: List[Hit]) -> List[DriftFinding]:
    findings: List[DriftFinding] = []
    for hit in hits:
        cl = classify(hit)
        if cl is None:
            continue
        score, factors = _confidence(hit, cl)
        c = hit.target.change
        findings.append(DriftFinding(
            id="", type=cl.type, severity=cl.severity, confidence=score,
            confidence_level=level_of(score).value,
            entity=c.name if c else None, entity_kind=c.kind if c else None,
            change=cl.change, file=hit.target.file.path, document=_part(hit), message=cl.message,
            before=cl.before, after=cl.after, suggestion=cl.suggestion,
            evidence=build_evidence(hit, analysis), factors=factors))
    findings.sort(key=lambda x: (-SEVERITY_ORDER.index(x.severity), -x.confidence,
                                 x.document.document_id or "", x.document.path, x.entity or ""))
    for n, x in enumerate(findings, start=1):
        x.id = f"F{n}"
    return findings


def summarize(analysis: PullRequestAnalysis, findings: List[DriftFinding],
              affected: List[AffectedDocument]) -> DriftSummary:
    by_type = Counter(x.type.value for x in findings)
    by_sev = Counter(x.severity.value for x in findings)
    highest = max((x.severity for x in findings), key=SEVERITY_ORDER.index, default=None)
    return DriftSummary(findings=len(findings),
                        by_type={t.value: by_type.get(t.value, 0) for t in DriftType},
                        by_severity={s.value: by_sev.get(s.value, 0) for s in SEVERITY_ORDER},
                        highest_severity=highest, affected_documents=len(affected),
                        changed_files=len(analysis.files), entity_changes=analysis.entity_changes)


# ---------- whole request ----------

def analyze(req: DriftAnalyzeRequest, store) -> DriftReport:
    analysis = analyze_pull_request(req.pull_request, req.files, req.repository)
    docs, warnings = collect_docs(store, req.document_ids, req.docs)
    affected, hits = find_affected(analysis, docs)
    findings = detect(analysis, hits)
    for f in analysis.files:
        warnings.extend(f.warnings)
    if not docs:
        warnings.append("No documentation to check: no saved document and no Markdown file in the request.")
    return DriftReport(id=uuid.uuid4().hex,
                       status=DriftStatus.drift_detected if findings else DriftStatus.no_drift,
                       repository=req.repository, pull_request=req.pull_request,
                       tickets=analysis.tickets, summary=summarize(analysis, findings, affected),
                       findings=findings, affected_documents=affected, analysis=analysis,
                       warnings=warnings, method=METHOD)


# ---------- report store (in memory; drift history with resolution is LD-167) ----------

class DriftReportStore:
    def __init__(self, limit: int = 500) -> None:
        self._lock = threading.Lock()
        self._reports: "OrderedDict[str, DriftReport]" = OrderedDict()
        self.limit = limit

    def add(self, report: DriftReport) -> DriftReport:
        with self._lock:
            self._reports[report.id] = report
            while len(self._reports) > self.limit:
                self._reports.popitem(last=False)   # oldest first
        return report

    def get(self, report_id: str) -> Optional[DriftReport]:
        return self._reports.get(report_id)

    def list(self, repository: Optional[str] = None,
             pull_request: Optional[int] = None) -> List[DriftReportSummary]:
        rows = []
        for r in reversed(list(self._reports.values())):
            if repository is not None and r.repository != repository:
                continue
            if pull_request is not None and r.pull_request.number != pull_request:
                continue
            rows.append(DriftReportSummary(id=r.id, status=r.status, repository=r.repository,
                                           pull_request_number=r.pull_request.number,
                                           pull_request_title=r.pull_request.title,
                                           head_sha=r.pull_request.head_sha, summary=r.summary,
                                           created_at=r.created_at))
        return rows


drift_reports = DriftReportStore()
