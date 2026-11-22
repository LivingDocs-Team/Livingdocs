"""LivingDocs AI service - AI-assisted documentation generation (LD-90, LD-340), versioned
documentation (LD-195), documentation drift detection (LD-145) and AI-based drift analysis
with review and resolution (LD-346).

Run:  uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs
"""
from typing import List, Literal, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import AwareDatetime, BaseModel

from app.change_context import ChangeContextReport, ChangeContextRequest, change_context
from app.drift import analyze as analyze_drift
from app.drift import drift_reports
from app.drift_changes import analyze_pull_request
from app.drift_markdown import at_least, render as render_drift_markdown
from app.drift_models import (DriftAnalyzeRequest, DriftFinding, DriftReport, DriftReportSummary,
                              PullRequestAnalysis, ResolutionUpdate, Severity)
from app.drift_review import ResolutionError
from app.drift_models import (DriftAnalyzeRequest, DriftReport, DriftReportSummary,
                              PullRequestAnalysis, Severity)
from app.suggestion_api import router as suggestion_router
from app.drift_severity import CAPS, SCORE_BANDS, SEVERITY_LEVELS, rules_table
from app.generator import get_generator
from app.jobs import jobs, run_job
from app.models import (SECTION_KINDS, SECTION_NAMES, FileRetrieval, GenerateRequest, IndexSummary,
                        Job, JobReport, RetrievalHit, RetrievalPreview,
                        JobStatus, Template, TemplateIn,
                        TemplateSections, TemplateVersion)
from app.normalize import normalize
from app.retrieval import build_index, retrieve
from app.templates import TemplateNameTaken, templates
from app.version_models import (Document, DocumentContentEdit, DocumentCreate, DocumentDiff, DocumentVersion,
                                FileSection, HistoryEvent, InternalDocumentCreate, InternalVersionDecision,
                                PreparedRevision, RevisionDraftCommit, RevisionDraftRequest, RevisionReviewEvidence,
                                InternalRollbackRequest, VersionComparison,
                                VersionSummary)
from app.versions import VersionError, documents
from app.internal_auth import require_internal_service, require_service_credential_when_configured
from app.source_change_impact import (AffectedDocumentsRequest, AffectedDocumentsResult,
                                      find_for_source_change)

app = FastAPI(title="LivingDocs AI Service", version="0.1.0",
              dependencies=[Depends(require_service_credential_when_configured)])


@app.get("/health")
def health():
    return {"status": "ok", "generator": get_generator().mode}


@app.get("/internal/system-analytics", dependencies=[Depends(require_internal_service)])
def system_analytics(start: AwareDatetime = Query(alias="from"),
                     end: AwareDatetime = Query(alias="to")):
    if start >= end:
        raise HTTPException(400, "from must be earlier than to")
    created, audit = documents.count_activity(start, end)
    completed, failed = jobs.count_outcomes(start, end)
    return {
        "documentsCreated": created,
        "documentVersionAuditEvents": audit,
        "aiJobs": {
            "completed": completed,
            "failed": failed,
            "observedSince": jobs.observed_since,
            "scope": "CURRENT_AI_PROCESS",
        },
    }


# ---------- Documentation generation ----------

@app.post("/generate", response_model=Job, status_code=202)
def generate(req: GenerateRequest, background: BackgroundTasks):
    """Start generating docs for a file, module or repository. Returns a job to poll."""
    tpl = templates.at_version(req.template_id, req.template_version)
    if tpl is None:
        what = f"Template '{req.template_id}'" + (f" version {req.template_version}" if req.template_version else "")
        raise HTTPException(404, f"{what} not found")
    job = jobs.create(req, tpl)
    # the job keeps the template as it was now: editing or deleting it later does not change this job
    background.add_task(run_job, job.id, req, None, tpl)
    return job


@app.post("/retrieval/preview", response_model=RetrievalPreview)
def retrieval_preview(req: GenerateRequest):
    """LD-335: show what the retrieval index holds and which related code (C) and documentation
    passages (D) each file would receive in its prompt. Nothing is generated or stored."""
    files = [f.model_copy(deep=True) for f in req.files]
    for f in files:
        normalize(f)
    req = req.model_copy(update={"files": files})
    index = build_index(req)
    st = index.stats()

    def hit(c) -> RetrievalHit:
        return RetrievalHit(ref=c.ref, kind=c.kind, entity=c.entity, path=c.path, name=c.name,
                            section=c.section or None, line_start=c.line_start, line_end=c.line_end,
                            score=c.score, excerpt=c.excerpt)

    out = []
    for f in files:
        if f.status.value != "ok":
            continue
        got = retrieve(index, f)
        out.append(FileRetrieval(path=f.path, code=[hit(c) for c in got.code],
                                 docs=[hit(c) for c in got.docs]))
    return RetrievalPreview(index=IndexSummary(files=st.files, documents=st.documents,
                                               chunks=st.chunks, vocabulary=st.vocabulary),
                            files=out)


@app.get("/jobs", response_model=List[Job])
def list_jobs():
    return jobs.list()


@app.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/jobs/{job_id}/result", response_class=PlainTextResponse)
def get_result(job_id: str):
    """Generated documentation as raw Markdown."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}")
    return PlainTextResponse(job.result, media_type="text/markdown")


@app.get("/jobs/{job_id}/report", response_model=JobReport)
def get_report(job_id: str):
    """Evidence and confidence for every documented entity (for review / the frontend)."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}")
    report = jobs.get_report(job_id)
    if report is None:
        raise HTTPException(404, "Report not found")
    return report


# ---------- Template management ----------

@app.get("/templates", response_model=List[Template])
def list_templates():
    """All templates users can choose: built-in ones first, then custom ones by name."""
    return templates.list()


@app.get("/templates/sections", response_model=TemplateSections)
def template_sections():
    """Sections a template may contain, in the spelling the API accepts."""
    return TemplateSections(sections=SECTION_NAMES,
                            documents={k: sorted(v) for k, v in SECTION_KINDS.items()})


@app.get("/templates/{template_id}", response_model=Template)
def get_template(template_id: str):
    tpl = templates.get(template_id)
    if tpl is None:
        raise HTTPException(404, "Template not found")
    return tpl


@app.post("/templates", response_model=Template, status_code=201)
def create_template(data: TemplateIn):
    try:
        return templates.create(data)
    except TemplateNameTaken as e:
        raise HTTPException(409, str(e))


@app.put("/templates/{template_id}", response_model=Template)
def update_template(template_id: str, data: TemplateIn):
    try:
        return templates.update(template_id, data)
    except KeyError:
        raise HTTPException(404, "Template not found")
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except TemplateNameTaken as e:
        raise HTTPException(409, str(e))


@app.get("/templates/{template_id}/versions", response_model=List[TemplateVersion])
def list_template_versions(template_id: str):
    """LD-227: every saved version of a template, newest first (built-in templates have one)."""
    try:
        return templates.versions(template_id)
    except KeyError:
        raise HTTPException(404, "Template not found")


@app.get("/templates/{template_id}/versions/{number}", response_model=TemplateVersion)
def get_template_version(template_id: str, number: int):
    try:
        return templates.version(template_id, number)
    except KeyError:
        raise HTTPException(404, "Template version not found")


@app.post("/templates/{template_id}/versions/{number}/restore", response_model=Template)
def restore_template_version(template_id: str, number: int):
    """LD-227: make an older version current again; its content is saved as a new version."""
    try:
        return templates.restore(template_id, number)
    except KeyError:
        raise HTTPException(404, "Template or version not found")
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except TemplateNameTaken as e:
        raise HTTPException(409, str(e))


@app.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: str):
    try:
        templates.delete(template_id)
    except KeyError:
        raise HTTPException(404, "Template not found")
    except PermissionError as e:
        raise HTTPException(403, str(e))


# ---------- Versioned documentation (LD-195) ----------

def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except VersionError as e:
        raise HTTPException(e.status, e.message)


@app.post("/documents", response_model=Document, status_code=201)
def create_document(data: DocumentCreate):
    """Save a completed job's result as version 1 of a new document."""
    job = jobs.get(data.job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}")
    output = jobs.get_output(data.job_id)
    if output is None:
        raise HTTPException(409, "Job result is no longer available")
    return documents.create_from_job(
              data.job_id,
              output,
              data.title,
              data.actor,
              data.note,
              report=jobs.get_report(data.job_id),
)


@app.post("/internal/documents/from-job", response_model=Document, status_code=201,
          dependencies=[Depends(require_internal_service)])
def create_owned_document(data: InternalDocumentCreate,
                          user_id: str = Header(alias="X-User-Id")):
    """Trusted integration endpoint. Ownership is sourced only from the authenticated header."""
    if not user_id.isdigit() or int(user_id) < 1:
        raise HTTPException(400, "A valid authenticated LivingDocs user id is required")
    job = jobs.get(data.job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}")
    output = jobs.get_output(data.job_id)
    if output is None:
        raise HTTPException(409, "Job result is no longer available")
    return documents.create_from_job(
    data.job_id,
    output,
    data.title,
    user_id,
    data.note,
    owner_user_id=user_id,
    report=jobs.get_report(data.job_id),
)


@app.get("/internal/revision-draft-candidates/{repository_id}", response_model=List[Document],
         dependencies=[Depends(require_internal_service)])
def revision_draft_candidates(repository_id: str):
    return documents.revision_candidates(repository_id)


@app.post("/internal/documents/{doc_id}/revision-drafts/prepare", response_model=Optional[PreparedRevision],
          dependencies=[Depends(require_internal_service)])
def prepare_revision_draft(doc_id: str, data: RevisionDraftRequest,
                           user_id: str = Header(alias="X-User-Id")):
    return _generate_revision(doc_id, data, user_id)


@app.post("/internal/documents/{doc_id}/revision-drafts/commit", response_model=Optional[DocumentVersion],
          dependencies=[Depends(require_internal_service)])
def commit_revision_draft(doc_id: str, data: RevisionDraftCommit,
                          user_id: str = Header(alias="X-User-Id")):
    return _call(documents.commit_revision, doc_id, user_id, data, data.prepared, data.lease_expires_at)


def _generate_revision(doc_id: str, data: RevisionDraftRequest, user_id: str):
    def generate(doc, files):
        from app.confidence import METHOD, average, level_of
        from app.models import FileResultStatus

        tpl = templates.at_version(doc.template_id, doc.template_version)
        if tpl is None:
            raise VersionError(409, "The original documentation template is unavailable")
        replacements, reports = {}, []
        if files:
            generator = get_generator()
            request = GenerateRequest(
                scope=doc.scope, target=doc.target, files=data.files, template_id=tpl.id,
                template_version=tpl.version, output_language=doc.output_language,
                source_snapshot=data.source_snapshot,
            )
            for file in request.files:
                normalize(file)
            index = build_index(request)
        for file in files:
            if file.status.value != "ok":
                raise VersionError(503, "The source file could not be analyzed")
            result = generator.document_file(file, tpl, doc.output_language, retrieve(index, file))
            if result.status != FileResultStatus.generated:
                raise VersionError(503, "Grounded AI generation is currently unavailable")
            replacements[file.path] = FileSection(
                path=file.path, markdown=result.markdown,
                status=result.status.value, confidence=result.confidence,
            )
            reports.append(result.report)
        score = average([entity.confidence for report in reports for entity in report.entities])
        return replacements, JobReport(
            job_id=data.source_change_id, template_id=tpl.id, template_name=tpl.name,
            template_version=tpl.version, template_instructions=tpl.instructions,
            template_sections=list(tpl.sections), confidence=score, level=level_of(score),
            method=METHOD, files=reports,
        )

    return _call(documents.prepare_revision, doc_id, user_id, data, generate)


@app.get("/internal/documents/{doc_id}", response_model=Document,
         dependencies=[Depends(require_internal_service)])
def get_owned_document(doc_id: str):
    return _call(documents.get, doc_id)


@app.get("/internal/documents/{doc_id}/versions", response_model=List[VersionSummary],
         dependencies=[Depends(require_internal_service)])
def list_internal_document_versions(doc_id: str):
    """LD-184: every version of a document, newest first (to choose two for a comparison)."""
    return _call(documents.versions, doc_id)


@app.get("/internal/documents/{doc_id}/compare", response_model=DocumentDiff,
         dependencies=[Depends(require_internal_service)])
def compare_internal_document_versions(doc_id: str, from_version: Optional[int] = Query(None, alias="from", ge=1),
                                       to_version: Optional[int] = Query(None, alias="to", ge=1)):
    """LD-183: added, removed and modified lines between any two versions (UC-30, BR-44);
    without `from` / `to` the current version is compared with the previous one."""
    return _call(documents.compare, doc_id, from_version, to_version)


@app.get("/internal/documents/{doc_id}/content", response_class=PlainTextResponse,
         dependencies=[Depends(require_internal_service)])
def get_internal_document_content(doc_id: str, version: Optional[int] = Query(None, ge=1)):
    v = _call(documents.version, doc_id, version)
    return PlainTextResponse(v.content, media_type="text/markdown")


@app.get("/internal/documents/{doc_id}/versions/{number}", response_model=DocumentVersion,
         dependencies=[Depends(require_internal_service)])
def get_internal_document_version(doc_id: str, number: int):
    """Exact version for callers that enforce document workflow access."""
    return _call(documents.version, doc_id, number)
@app.get(
    "/internal/documents/{doc_id}/review-evidence",
    response_model=RevisionReviewEvidence,
    dependencies=[Depends(require_internal_service)],
)
def get_internal_document_review_evidence(
    doc_id: str,
    version: Optional[int] = Query(None, ge=1),
):
    """Return AI evidence and source snapshot for a specific document version."""
    v = _call(documents.version, doc_id, version)

    if v.review_report is None:
        raise HTTPException(
            status_code=404,
            detail="Review evidence is not available for this document version",
        )

    return RevisionReviewEvidence(
        **v.review_report.model_dump(),
        source_snapshot=v.source_snapshot,
        revision_files=v.revision_files,
    )


@app.get(
    "/internal/documents/{doc_id}/review-comparison",
    response_model=VersionComparison,
    dependencies=[Depends(require_internal_service)],
)
def get_internal_document_review_comparison(doc_id: str):
    """Compare the pending version with the latest approved version."""
    return _call(documents.review_comparison, doc_id)


@app.get(
    "/internal/documents/{doc_id}/evidence",
    response_model=JobReport,
    dependencies=[Depends(require_internal_service)],
)
def get_internal_document_evidence(
    doc_id: str,
    version: int = Query(..., ge=1),
):
    """Return grounding evidence for an exact owned-document version."""
    document_version = _call(documents.version, doc_id, version)

    if document_version.evidence_report is None:
        raise HTTPException(
            status_code=404,
            detail="Grounding evidence not found for this document version",
        )

    return document_version.evidence_report

@app.put("/internal/documents/{doc_id}/content", response_model=DocumentVersion,
         dependencies=[Depends(require_internal_service)])
def edit_owned_document(doc_id: str, data: DocumentContentEdit,
                        user_id: str = Header(alias="X-User-Id")):
    try:
        return documents.edit_owned(doc_id, user_id, data.expected_version, data.content, data.note)
    except VersionError as e:
        raise HTTPException(e.status, e.message)


@app.post("/internal/documents/{doc_id}/review-decision", status_code=204,
          dependencies=[Depends(require_internal_service)])
def resolve_owned_document_version(doc_id: str, data: InternalVersionDecision,
                                   user_id: str = Header(alias="X-User-Id"),
                                   owner_id: str = Header(alias="X-Document-Owner-Id")):
    try:
        documents.resolve_workflow_version(doc_id, owner_id,
                                           data.version, data.decision, user_id, data.note,
                                           replay=data.replay)
    except VersionError as e:
        raise HTTPException(e.status, e.message)


@app.put("/internal/documents/{doc_id}/staff-draft", response_model=DocumentVersion,
         dependencies=[Depends(require_internal_service)])
def edit_staff_draft(doc_id: str, data: DocumentContentEdit,
                     actor: str = Header(alias="X-User-Id"),
                     owner: str = Header(alias="X-Document-Owner-Id")):
    if not data.note or not data.note.strip():
        raise HTTPException(422, "A reason is required for a Staff edit")
    return _call(documents.edit_staff_draft, doc_id, owner, data.expected_version,
                 actor, data.content, data.note.strip())

@app.post(
    "/internal/documents/{doc_id}/rollback",
    response_model=DocumentVersion,
    status_code=201,
    dependencies=[Depends(require_internal_service)],
)
def rollback_owned_document(
    doc_id: str,
    data: InternalRollbackRequest,
    user_id: str = Header(alias="X-User-Id"),
    owner_id: str = Header(alias="X-Document-Owner-Id"),
):
    try:
        return documents.rollback_owned(
            doc_id,
            owner_id,
            data.source_version,
            user_id,
            data.note,
        )
    except VersionError as e:
        raise HTTPException(e.status, e.message)
@app.get("/documents", response_model=List[Document], response_model_exclude={"owner_user_id"})
def list_documents():
    return documents.list_public()


@app.get("/documents/{doc_id}", response_model=Document, response_model_exclude={"owner_user_id"})
def get_document(doc_id: str):
    return _call(documents.get_public, doc_id)


@app.get("/documents/{doc_id}/content", response_class=PlainTextResponse)
def get_document_content(doc_id: str, version: Optional[int] = Query(None, ge=1)):
    """Markdown of the current version, or of `?version=N`."""
    _call(documents.get_public, doc_id)
    v = _call(documents.version, doc_id, version)
    return PlainTextResponse(v.content, media_type="text/markdown")


@app.get("/documents/{doc_id}/versions", response_model=List[VersionSummary])
def list_versions(doc_id: str):
    """LD-195: version history, newest first."""
    _call(documents.get_public, doc_id)
    return _call(documents.versions, doc_id)


@app.get("/documents/{doc_id}/versions/{number}", response_model=DocumentVersion)
def get_version(doc_id: str, number: int):
    _call(documents.get_public, doc_id)
    return _call(documents.version, doc_id, number)


@app.get("/documents/{doc_id}/compare", response_model=DocumentDiff)
def compare_versions(doc_id: str, from_version: Optional[int] = Query(None, alias="from", ge=1),
                     to_version: Optional[int] = Query(None, alias="to", ge=1)):
    """LD-183: difference between two versions of a (legacy, ownerless) document."""
    _call(documents.get_public, doc_id)
    return _call(documents.compare, doc_id, from_version, to_version)


@app.get("/documents/{doc_id}/history", response_model=List[HistoryEvent])
def get_history(doc_id: str):
    """LD-195: who did what and when (created, proposed, accepted, edited, dismissed, ...)."""
    _call(documents.get_public, doc_id)
    return _call(documents.history, doc_id)


# ---------- Documentation drift detection (LD-145) ----------

@app.post("/drift/changes", response_model=PullRequestAnalysis)
def drift_changes(req: DriftAnalyzeRequest):
    """LD-146: changed code entities of a Pull Request (no documentation is checked, nothing
    is stored). Same body as /drift/analyze; `docs` and `document_ids` are ignored."""
    return analyze_pull_request(req.pull_request, req.files, req.repository)


@app.post("/drift/context", response_model=ChangeContextReport)
def drift_context(req: ChangeContextRequest):
    """LD-338: for every code entity the Pull Request changes, the context needed to update its
    documentation: the diff (X1), related code at the head commit (C: callers, callees, similar)
    and documentation (D: passages naming the entity first, then related ones), plus a prompt
    text citing them. Nothing is stored and no AI is called."""
    return change_context(req, documents)


app.include_router(suggestion_router)   # LD-353 documentation update suggestions


@app.post("/drift/analyze", response_model=DriftReport, status_code=201)
def drift_analyze(req: DriftAnalyzeRequest):
    """LD-147/148/149: findings (Referential / Signature / Semantic, severity, confidence) for
    every saved document section and repository Markdown file that describes changed code,
    each with its evidence (code diff, documentation passage, commit, ticket). The report is
    kept and can be read again from /drift/reports/{id}.

    LD-346: every finding also gets `ai_review` (AI verdict, explanation citing its evidence ids,
    suggested documentation update; offline explanation without an API key; `ai_review: false`
    skips the AI) and `resolution` (open until a reviewer handles it)."""
    return drift_reports.add(analyze_drift(req, documents))


@app.get("/drift/reports", response_model=List[DriftReportSummary])
def list_drift_reports(repository: Optional[str] = Query(None, max_length=300),
                       pull_request: Optional[int] = Query(None, ge=1)):
    """Drift reports, newest first; filter by `repository` ("owner/name") and Pull Request number."""
    return drift_reports.list(repository, pull_request)


def _drift_report(report_id: str) -> DriftReport:
    report = drift_reports.get(report_id)
    if report is None:
        raise HTTPException(404, "Drift report not found")
    return report


@app.get("/drift/reports/{report_id}", response_model=DriftReport)
def get_drift_report(report_id: str, min_severity: Optional[Severity] = None):
    """One report; `?min_severity=high` keeps only High and Critical findings (LD-158)."""
    report = _drift_report(report_id)
    if min_severity is None:
        return report
    return report.model_copy(update={"findings": at_least(report.findings, min_severity)})


@app.get("/drift/reports/{report_id}/markdown", response_class=PlainTextResponse)
def get_drift_report_markdown(report_id: str, min_severity: Optional[Severity] = None):
    """LD-159: the report as Markdown grouped by severity, e.g. for a Pull Request comment."""
    return PlainTextResponse(render_drift_markdown(_drift_report(report_id), min_severity),
                             media_type="text/markdown")


@app.put("/drift/reports/{report_id}/findings/{finding_id}/resolution", response_model=DriftFinding)
def resolve_drift_finding(report_id: str, finding_id: str, update: ResolutionUpdate):
    """LD-346: review and resolution of one finding: open, acknowledged, resolved or dismissed
    (dismissing needs a `note` with the reason). Every change is kept in `resolution.history`."""
    try:
        finding = drift_reports.resolve(report_id, finding_id, update)
    except ResolutionError as e:
        raise HTTPException(e.status, e.message)
    if finding is None:
        raise HTTPException(404, "Drift report not found")
    return finding


@app.put("/internal/repositories/{repository_id}/drift/reports/{report_id}/findings/{finding_id}/resolution",
         response_model=DriftFinding, dependencies=[Depends(require_internal_service)])
def submit_drift_resolution(repository_id: str, report_id: str, finding_id: str,
                            update: ResolutionUpdate, user_id: str = Header(alias="X-User-Id")):
    update = update.model_copy(update={"actor": user_id})
    try:
        draft = None
        if update.decision in ("accept", "edit"):
            def draft(report, finding):
                return documents.propose_drift(user_id, repository_id, report, finding)
        finding = drift_reports.resolve(report_id, finding_id, update, draft=draft)
    except (ResolutionError, VersionError) as error:
        raise HTTPException(error.status, error.message)
    if finding is None:
        raise HTTPException(404, "Drift report not found")
    return finding


class DriftWorkflowDecision(BaseModel):
    document_id: str
    owner_user_id: Optional[str] = None
    version: int
    decision: Literal["APPROVED", "REJECTED"]
    actor: str
    note: Optional[str] = None


@app.put("/internal/drift/reports/{report_id}/findings/{finding_id}/workflow-decision",
         status_code=204, dependencies=[Depends(require_internal_service)])
def apply_drift_workflow_decision(report_id: str, finding_id: str, update: DriftWorkflowDecision):
    version = _call(documents.version, update.document_id, update.version)
    link = version.drift_finding or {}
    if link.get("report_id") != report_id or link.get("finding_id") != finding_id:
        raise HTTPException(409, "Workflow decision does not match the linked drift draft")
    if update.owner_user_id is not None:
        _call(documents.resolve_workflow_version, update.document_id, update.owner_user_id,
              update.version, update.decision, update.actor, update.note, replay=True)
    else:
        _call(documents.require_workflow_decision, update.document_id, update.version,
              update.decision, update.actor, update.note)
    try:
        drift_reports.apply_workflow_decision(report_id, finding_id, update.document_id, update.version,
                                            update.decision, update.actor, update.note)
    except ResolutionError as error:
        raise HTTPException(error.status, error.message)


@app.post("/internal/affected-documents", response_model=AffectedDocumentsResult,
          dependencies=[Depends(require_internal_service)])
def affected_documents(req: AffectedDocumentsRequest):
    """LD-122: parts of the given saved documents that a source change (LD-116) may have made
    outdated, each `direct` (documents a changed file) or `dependent` (refers to changed code)."""
    return find_for_source_change(req, documents)


@app.get("/drift/severity-rules")
def drift_severity_rules():
    """LD-157 / LD-158: severity levels (score bands, meaning, action) and every rule."""
    return {"levels": [{"level": level.value, "min_score": SCORE_BANDS[level][0],
                        "max_score": SCORE_BANDS[level][1], **SEVERITY_LEVELS[level.value]}
                       for level in reversed(list(SCORE_BANDS))],
            "rules": rules_table(),
            "caps": {t: level.value for t, level in CAPS.items()}}
