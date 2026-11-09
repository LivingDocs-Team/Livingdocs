"""LivingDocs AI service - AI-assisted documentation generation (LD-90, LD-340) and versioned
documentation (LD-195).

Run:  uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs
"""
from typing import List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.generator import get_generator
from app.jobs import jobs, run_job
from app.models import (SECTION_KINDS, SECTION_NAMES, GenerateRequest, Job, JobReport, JobStatus,
                        Template, TemplateIn, TemplateSections)
from app.templates import TemplateNameTaken, templates
from app.version_models import (Document, DocumentContentEdit, DocumentCreate, DocumentVersion,
                                HistoryEvent, InternalDocumentCreate, InternalVersionDecision,
                                VersionSummary)
from app.versions import VersionError, documents
from app.internal_auth import require_internal_service

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
    return documents.create_from_job(data.job_id, output, data.title, user_id, data.note,
                                     owner_user_id=user_id)


@app.get("/internal/documents/{doc_id}", response_model=Document,
         dependencies=[Depends(require_internal_service)])
def get_owned_document(doc_id: str):
    return _call(documents.get, doc_id)


@app.get("/internal/documents/{doc_id}/content", response_class=PlainTextResponse,
         dependencies=[Depends(require_internal_service)])
def get_internal_document_content(doc_id: str, version: Optional[int] = Query(None, ge=1)):
    v = _call(documents.version, doc_id, version)
    return PlainTextResponse(v.content, media_type="text/markdown")


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
                                           data.version, data.decision, user_id, data.note)
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


@app.get("/documents/{doc_id}/history", response_model=List[HistoryEvent])
def get_history(doc_id: str):
    """LD-195: who did what and when (created, proposed, accepted, edited, dismissed, ...)."""
    _call(documents.get_public, doc_id)
    return _call(documents.history, doc_id)
