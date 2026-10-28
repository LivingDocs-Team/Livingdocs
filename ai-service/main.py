"""LivingDocs AI service - AI-assisted documentation generation (LD-90, LD-340).

Run:  uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs
"""
from typing import List

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from app.generator import get_generator
from app.jobs import jobs, run_job
from app.models import (SECTION_KINDS, SECTION_NAMES, GenerateRequest, Job, JobReport, JobStatus,
                        Template, TemplateIn, TemplateSections)
from app.templates import TemplateNameTaken, templates

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
