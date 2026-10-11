"""LivingDocs AI service - AI-assisted documentation generation (LD-90).

Run:  uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs
"""
from typing import List

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from app.generator import get_generator
from app.jobs import jobs, run_job
from app.models import GenerateRequest, Job, JobStatus, Template, TemplateIn
from app.templates import templates

app = FastAPI(title="LivingDocs AI Service", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "generator": type(get_generator()).__name__}


# ---------- Documentation generation ----------

@app.post("/generate", response_model=Job, status_code=202)
def generate(req: GenerateRequest, background: BackgroundTasks):
    """Start generating docs for a file, module or repository. Returns a job to poll."""
    if templates.get(req.template_id) is None:
        raise HTTPException(404, f"Template '{req.template_id}' not found")
    job = jobs.create(req)
    background.add_task(run_job, job.id, req)
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


# ---------- Template management ----------

@app.get("/templates", response_model=List[Template])
def list_templates():
    return templates.list()


@app.get("/templates/{template_id}", response_model=Template)
def get_template(template_id: str):
    tpl = templates.get(template_id)
    if tpl is None:
        raise HTTPException(404, "Template not found")
    return tpl


@app.post("/templates", response_model=Template, status_code=201)
def create_template(data: TemplateIn):
    return templates.create(data)


@app.put("/templates/{template_id}", response_model=Template)
def update_template(template_id: str, data: TemplateIn):
    try:
        return templates.update(template_id, data)
    except KeyError:
        raise HTTPException(404, "Template not found")
    except PermissionError as e:
        raise HTTPException(403, str(e))


@app.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: str):
    try:
        templates.delete(template_id)
    except KeyError:
        raise HTTPException(404, "Template not found")
    except PermissionError as e:
        raise HTTPException(403, str(e))
