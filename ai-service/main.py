"""LivingDocs AI service - AI-assisted documentation generation (LD-90, LD-340) and versioned
documentation (LD-195, LD-128, LD-134, LD-189).

Run:  uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs
"""
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse

from app.generator import get_generator
from app.jobs import jobs, run_job
from app.models import (SECTION_KINDS, SECTION_NAMES, GenerateRequest, Job, JobReport, JobStatus,
                        Template, TemplateIn, TemplateSections)
from app.templates import TemplateNameTaken, templates
from app.version_models import (CompareResult, Document, DocumentCreate, DocumentUpdateRequest,
                                DocumentVersion, EditRequest, HistoryEvent, ReviewRequest,
                                RollbackRequest, UpdateResult, VersionSummary)
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


# ---------- Versioned documentation (LD-195, LD-128, LD-134, LD-189) ----------

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


@app.get("/documents/{doc_id}/compare", response_model=CompareResult)
def compare_versions(doc_id: str, from_version: Optional[int] = Query(None, alias="from", ge=1),
                     to_version: Optional[int] = Query(None, alias="to", ge=1)):
    """LD-134: differences between two versions (for review). Default: current version -> pending proposal."""
    return _call(documents.compare, doc_id, from_version, to_version)


@app.post("/documents/{doc_id}/updates", response_model=UpdateResult)
def update_document(doc_id: str, req: DocumentUpdateRequest, response: Response):
    """LD-128: regenerate the documentation of the files changed by a source change (LD-116).
    201 with a proposal to review, or 200 when nothing documented was affected (or the source
    change is already in the pending proposal)."""
    result, created = _call(documents.update, doc_id, req)
    response.status_code = 201 if created else 200
    return result


@app.post("/documents/{doc_id}/versions/{number}/accept", response_model=DocumentVersion)
def accept_version(doc_id: str, number: int, data: Optional[ReviewRequest] = None):
    data = data or ReviewRequest()
    return _call(documents.accept, doc_id, number, data.actor, data.note)


@app.post("/documents/{doc_id}/versions/{number}/dismiss", response_model=DocumentVersion)
def dismiss_version(doc_id: str, number: int, data: Optional[ReviewRequest] = None):
    data = data or ReviewRequest()
    return _call(documents.dismiss, doc_id, number, data.actor, data.note)


@app.post("/documents/{doc_id}/versions/{number}/regenerate", response_model=DocumentVersion,
          status_code=201)
def regenerate_version(doc_id: str, number: int, data: Optional[ReviewRequest] = None):
    data = data or ReviewRequest()
    return _call(documents.regenerate, doc_id, number, data.actor, data.note)


@app.post("/documents/{doc_id}/versions/{number}/edit", response_model=DocumentVersion,
          status_code=201)
def edit_version(doc_id: str, number: int, data: EditRequest):
    return _call(documents.edit, doc_id, number, data.content, data.accept, data.actor, data.note)


@app.post("/documents/{doc_id}/rollback", response_model=DocumentVersion, status_code=201)
def rollback_document(doc_id: str, data: RollbackRequest):
    """LD-189: restore an earlier accepted version as a new version (history is kept)."""
    return _call(documents.rollback, doc_id, data.version, data.actor, data.note)
