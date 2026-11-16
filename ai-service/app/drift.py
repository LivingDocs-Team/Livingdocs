"""LD-145 Documentation drift detection (LD-147 detect / classify / rate).

Pipeline for one Pull Request:

    LD-146  drift_changes.analyze_pull_request   changed files -> changed code entities
    LD-148  drift_affected.find_affected         -> documentation parts that refer to them
    LD-147  classify (this module)               -> findings: type + severity + confidence
    LD-149  drift_evidence.build_evidence        -> code diff, doc passage, commit, ticket

Classification (BR-49, LD-151): each finding has a `type`, a `kind` inside it (DRIFT_KINDS),
`breaking` and the `rules` that set its severity (Low < Medium < High < Critical):

    Referential  LD-152 app/drift_referential.py  the documentation names code that is gone:
                 removed / renamed entity, moved endpoint, deleted or moved file or module,
                 line references (`path:12-30`) that no longer point to the same code
    Signature    LD-153 app/drift_signature.py    the documented contract changed: parameters
                 (removed, renamed, added, type, default, order), return type, class fields,
                 HTTP method, request body / response; breaking or not
    Semantic     LD-154 app/drift_semantic.py     same signature, other behaviour: status codes,
                 exceptions, values, docstring, implementation; new code not documented

The documentation is also checked for what it still says (old parameter, type, default,
exception, status code, value, docstring sentence): such passages raise the severity by one level
and are listed as evidence.

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

from . import drift_referential, drift_semantic, drift_severity, drift_signature
from .confidence import level_of
from .drift_affected import DocText, Hit, collect_docs, find_affected
from .drift_changes import analyze_pull_request
from .drift_evidence import build_evidence
from .drift_models import (DRIFT_KINDS, SEVERITY_ORDER, AffectedDocument, DriftAnalyzeRequest,
                           DriftFinding, DriftReport, DriftReportSummary, DriftStatus, DriftSummary,
                           DriftType, EntityChangeType, PullRequestAnalysis)
from .drift_review import DriftReviewer, get_reviewer, resolve
from .drift_models import ResolutionUpdate
from .drift_rules import Classified

METHOD = ("Entity changes from the analyzer's before/after results (or the diff), matched against "
          "saved documents and repository Markdown. Referential: removed/renamed code, moved files "
          "or modules, stale line references; Signature: parameters, types, defaults, return type, "
          "HTTP method or contract changed (breaking or not); Semantic: status codes, exceptions, "
          "values, docstring or implementation changed, or new code undocumented. A passage that "
          "still states the old detail raises the severity. Confidence = match x method x location "
          "x certainty; levels: high >= 0.75, medium >= 0.50, low < 0.50.")



# ---------- LD-151: classify one hit (LD-152 / LD-153 / LD-154) ----------

def classify(hit: Hit) -> List[Classified]:
    """Findings for one hit: usually one; a signature change whose body also changed in a way
    the documentation may describe (status codes, exceptions, values, docstring) gets a second,
    semantic finding."""
    t, c = hit.target, hit.target.change
    if t.file_event is not None:
        out = [drift_referential.classify(hit)]
    elif c is None:
        out = []
    elif c.change == EntityChangeType.added:
        out = [drift_semantic.classify_added(hit)]
    elif not hit.matches:
        out = []
    elif c.change in (EntityChangeType.removed, EntityChangeType.renamed):
        out = [drift_referential.classify(hit)]
    elif c.change == EntityChangeType.signature_changed:
        out = [drift_signature.classify(hit)]
        if c.signals:
            out.append(drift_semantic.classify(hit))
    elif c.change == EntityChangeType.behavior_changed:
        out = [drift_semantic.classify(hit)]
    else:
        out = []
    return [x for x in out if x is not None]


def _confidence(hit: Hit, cl: Classified) -> Tuple[float, dict]:
    t = hit.target
    exact = [m for m in hit.matches if m.exact]
    if hit.param_matches or cl.details or any(m.in_code for m in exact):
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


def _part(hit: Hit, cl: Classified) -> AffectedDocument:
    """The affected document part, with only this finding's matches."""
    d: DocText = hit.doc
    reasons = []
    if hit.documents_file:
        reasons.append(f"documents changed file {hit.target.file.path}")
    reasons += list(dict.fromkeys(f"mentions `{m.target}`" for m in hit.matches))
    reasons += list(dict.fromkeys(f"still shows {m.kind} `{m.term}`"
                                  for m in hit.param_matches + cl.details))
    return AffectedDocument(source=d.source, path=d.path, document_id=d.document_id, title=d.title,
                            version=d.version, documents_file=d.documents_file, reasons=reasons,
                            matches=sorted(hit.matches + hit.param_matches + cl.details,
                                           key=lambda m: m.line))


def detect(analysis: PullRequestAnalysis, hits: List[Hit]) -> List[DriftFinding]:
    findings: List[DriftFinding] = []
    for hit, cl in ((h, x) for h in hits for x in classify(h)):
        score, factors = _confidence(hit, cl)
        c = hit.target.change
        evidence = build_evidence(hit, analysis, cl.details)
        # LD-156: the severity comes only from the rule table, with the evidence of each rule
        assessment = drift_severity.assess(cl.type, cl.base, cl.adjust, score, evidence)
        cl.severity = assessment.level
        part = _part(hit, cl)
        part.severity, part.findings = assessment.level, 1
        findings.append(DriftFinding(
            id="", type=cl.type, kind=cl.kind, breaking=cl.breaking,
            rules=drift_severity.rule_strings(assessment), severity_assessment=assessment,
            severity=assessment.level, confidence=score,
            confidence_level=level_of(score).value,
            entity=c.name if c else None, entity_kind=c.kind if c else None,
            change=cl.change, file=hit.target.file.path, document=part,
            message=cl.message, before=cl.before, after=cl.after, suggestion=cl.suggestion,
            evidence=evidence, factors=factors))
    findings.sort(key=lambda x: (-x.severity_assessment.score, not x.breaking, -x.confidence,
                                 x.document.document_id or "", x.document.path, x.entity or ""))
    for n, x in enumerate(findings, start=1):
        x.id = f"F{n}"
    return findings


def _rate_documents(affected: List[AffectedDocument], findings: List[DriftFinding]) -> None:
    """LD-158: each affected document part takes the level of its most severe finding;
    parts are listed most severe first."""
    for a in affected:
        mine = [f for f in findings if (f.document.source, f.document.document_id, f.document.path)
                == (a.source, a.document_id, a.path)]
        a.findings = len(mine)
        a.severity = drift_severity.highest([f.severity for f in mine])
    affected[:] = [a for a in affected if a.findings]   # LD-347: only parts that really drifted
    affected.sort(key=lambda a: (-(SEVERITY_ORDER.index(a.severity) if a.severity else -1),
                                 a.source.value, a.document_id or "", a.path))


def summarize(analysis: PullRequestAnalysis, findings: List[DriftFinding],
              affected: List[AffectedDocument]) -> DriftSummary:
    by_type = Counter(x.type.value for x in findings)
    by_sev = Counter(x.severity.value for x in findings)
    by_kind = Counter(x.kind for x in findings)
    order = [k for t in DriftType for k in DRIFT_KINDS[t.value]]
    highest = max((x.severity for x in findings), key=SEVERITY_ORDER.index, default=None)
    return DriftSummary(findings=len(findings),
                        by_type={t.value: by_type.get(t.value, 0) for t in DriftType},
                        by_severity={s.value: by_sev.get(s.value, 0) for s in SEVERITY_ORDER},
                        by_kind={k: by_kind[k] for k in order if by_kind.get(k)},
                        breaking=sum(1 for x in findings if x.breaking),
                        highest_severity=highest, affected_documents=len(affected),
                        severity_score=max((x.severity_assessment.score for x in findings), default=0),
                        recommendation=drift_severity.SEVERITY_LEVELS[highest.value]["action"]
                        if highest else None,
                        changed_files=len(analysis.files), entity_changes=analysis.entity_changes)


# ---------- whole request ----------

def analyze(req: DriftAnalyzeRequest, store, reviewer: Optional[DriftReviewer] = None) -> DriftReport:
    analysis = analyze_pull_request(req.pull_request, req.files, req.repository)
    docs, warnings = collect_docs(store, req.document_ids, req.docs)
    affected, hits = find_affected(analysis, docs)
    findings = detect(analysis, hits)
    _rate_documents(affected, findings)
    for f in analysis.files:
        warnings.extend(f.warnings)
    if not docs:
        warnings.append("No documentation to check: no saved document and no Markdown file in the request.")
    report = DriftReport(id=uuid.uuid4().hex,
                         status=DriftStatus.drift_detected if findings else DriftStatus.no_drift,
                         repository=req.repository, pull_request=req.pull_request,
                         tickets=analysis.tickets, summary=summarize(analysis, findings, affected),
                         findings=findings, affected_documents=affected, analysis=analysis,
                         warnings=warnings, method=METHOD)
    # LD-346: AI second opinion + explanation per finding (offline explanation without a key)
    if not req.ai_review:
        reviewer = DriftReviewer(None)
    return (reviewer or get_reviewer()).review(report)


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

    def resolve(self, report_id: str, finding_id: str, update: ResolutionUpdate):
        """LD-346: set the resolution of one finding (None when the report is unknown)."""
        with self._lock:
            report = self._reports.get(report_id)
            if report is None:
                return None
            return resolve(report, finding_id, update)

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
                                           review=r.review, created_at=r.created_at))
        return rows


drift_reports = DriftReportStore()
