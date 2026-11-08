"""LivingDocs AI service - AI-assisted documentation generation (LD-90, LD-340), versioned
documentation (LD-195) and documentation drift detection (LD-145).

Run:  uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs
"""
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.drift import analyze as analyze_drift
from app.drift import drift_reports
from app.drift_changes import analyze_pull_request
from app.drift_models import (DriftAnalyzeRequest, DriftReport, DriftReportSummary,
                              PullRequestAnalysis)
from app.generator import get_generator
from app.jobs import jobs, run_job
from app.models import (SECTION_KINDS, SECTION_NAMES, GenerateRequest, Job, JobReport, JobStatus,
                        Template, TemplateIn, TemplateSections)
from app.templates import TemplateNameTaken, templates
from app.version_models import (Document, DocumentCreate, DocumentVersion, HistoryEvent,
                                VersionSummary)
from app.versions import VersionError, documents

app = FastAPI(title="LivingDocs AI Service", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "generator": get_generator().mode}


# ---------- Documentation generation ----------

@app.post("/generate", response_model=Job, status_code=202)
def generate(req: GenerateRequest, background: BackgroundTasks):
    """Start generating docs for a file, module or repository. Returns a job to poll."""
    tpl = templates.get(req.template_id)
    if tpl is None:
        raise HTTPException(404, f"Template '{req.template_id}' not found")
    job = jobs.create(req, tpl)
    # the job keeps the template as it was now: editing or deleting it later does not change this job
    background.add_task(run_job, job.id, req, None, tpl)
    return job


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
    return documents.create_from_job(data.job_id, output, data.title, data.actor, data.note)


@app.get("/documents", response_model=List[Document])
def list_documents():
    return documents.list()


@app.get("/documents/{doc_id}", response_model=Document)
def get_document(doc_id: str):
    return _call(documents.get, doc_id)


@app.get("/documents/{doc_id}/content", response_class=PlainTextResponse)
def get_document_content(doc_id: str, version: Optional[int] = Query(None, ge=1)):
    """Markdown of the current version, or of `?version=N`."""
    v = _call(documents.version, doc_id, version)
    return PlainTextResponse(v.content, media_type="text/markdown")


@app.get("/documents/{doc_id}/versions", response_model=List[VersionSummary])
def list_versions(doc_id: str):
    """LD-195: version history, newest first."""
    return _call(documents.versions, doc_id)


@app.get("/documents/{doc_id}/versions/{number}", response_model=DocumentVersion)
def get_version(doc_id: str, number: int):
    return _call(documents.version, doc_id, number)


@app.get("/documents/{doc_id}/history", response_model=List[HistoryEvent])
def get_history(doc_id: str):
    """LD-195: who did what and when (created, proposed, accepted, edited, dismissed, ...)."""
    return _call(documents.history, doc_id)


# ---------- Documentation drift detection (LD-145) ----------

@app.post("/drift/changes", response_model=PullRequestAnalysis)
def drift_changes(req: DriftAnalyzeRequest):
    """LD-146: changed code entities of a Pull Request (no documentation is checked, nothing
    is stored). Same body as /drift/analyze; `docs` and `document_ids` are ignored."""
    return analyze_pull_request(req.pull_request, req.files, req.repository)


@app.post("/drift/analyze", response_model=DriftReport, status_code=201)
def drift_analyze(req: DriftAnalyzeRequest):
    """LD-147/148/149: findings (Referential / Signature / Semantic, severity, confidence) for
    every saved document section and repository Markdown file that describes changed code,
    each with its evidence (code diff, documentation passage, commit, ticket). The report is
    kept and can be read again from /drift/reports/{id}."""
    return drift_reports.add(analyze_drift(req, documents))


@app.get("/drift/reports", response_model=List[DriftReportSummary])
def list_drift_reports(repository: Optional[str] = Query(None, max_length=300),
                       pull_request: Optional[int] = Query(None, ge=1)):
    """Drift reports, newest first; filter by `repository` ("owner/name") and Pull Request number."""
    return drift_reports.list(repository, pull_request)


@app.get("/drift/reports/{report_id}", response_model=DriftReport)
def get_drift_report(report_id: str):
    report = drift_reports.get(report_id)
    if report is None:
        raise HTTPException(404, "Drift report not found")
    return report
