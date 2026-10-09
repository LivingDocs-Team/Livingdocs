"""Generation jobs: run in the background, expose status, progress and result."""
import threading
import uuid
from typing import Dict, List, Optional

from .generator import get_generator
from .models import GenerateRequest, Job, JobStatus, Scope, now
from .templates import templates


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}

    def create(self, req: GenerateRequest) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            scope=req.scope,
            target=req.target,
            template_id=req.template_id,
            files_total=len(req.files),
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self) -> List[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def update(self, job_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for k, v in changes.items():
                setattr(job, k, v)
            job.updated_at = now()


jobs = JobStore()


def run_job(job_id: str, req: GenerateRequest) -> None:
    """Executed by FastAPI BackgroundTasks."""
    try:
        tpl = templates.get(req.template_id)
        if tpl is None:
            raise ValueError(f"Template '{req.template_id}' not found")

        gen = get_generator()
        steps = len(req.files) + (1 if req.scope != Scope.file else 0)
        jobs.update(job_id, status=JobStatus.running, message="Generating documentation")

        docs = []
        for i, f in enumerate(req.files, start=1):
            jobs.update(job_id, message=f"Documenting {f.path}")
            docs.append(gen.document_file(f, tpl, req.output_language))
            jobs.update(job_id, files_done=i, progress=round(i / steps, 3))

        if req.scope == Scope.file:
            result = docs[0] if len(docs) == 1 else "\n\n---\n\n".join(docs)
        else:
            jobs.update(job_id, message="Writing overview")
            overview = gen.summarize(req.target, docs, tpl, req.output_language)
            result = "\n\n---\n\n".join([overview, *docs])

        jobs.update(
            job_id, status=JobStatus.completed, progress=1.0,
            message="Completed", result=result,
        )
    except Exception as exc:  # report the failure on the job instead of crashing
        jobs.update(job_id, status=JobStatus.failed, message="Failed", error=str(exc))
