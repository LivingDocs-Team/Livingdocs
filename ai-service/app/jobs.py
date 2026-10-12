"""Generation jobs: run in the background, expose status, progress, warnings and result."""
import threading
import uuid
from typing import Dict, List, Optional

from .generator import DocGenerator, get_generator
from .models import (FileResult, FileResultStatus, GenerateRequest, Job, JobStatus,
                     Scope, now)
from .renderer import render_overview
from .templates import templates


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}

    def create(self, req: GenerateRequest) -> Job:
        job = Job(id=uuid.uuid4().hex, scope=req.scope, target=req.target,
                  template_id=req.template_id, files_total=len(req.files))
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


def run_job(job_id: str, req: GenerateRequest, generator: Optional[DocGenerator] = None) -> None:
    """Executed by FastAPI BackgroundTasks. One bad file never stops the whole job."""
    warnings: List[str] = []
    results: List[FileResult] = []
    try:
        tpl = templates.get(req.template_id)
        if tpl is None:
            raise ValueError(f"Template '{req.template_id}' not found")
        gen = generator or get_generator()
        total = len(req.files)
        jobs.update(job_id, status=JobStatus.running, message="Generating documentation")

        docs, documented, skipped = [], [], []
        for i, f in enumerate(req.files, start=1):
            jobs.update(job_id, message=f"Documenting {f.path}")
            if f.status.value != "ok":
                reason = f.error or f"analyzer status '{f.status.value}'"
                skipped.append((f.path, reason))
                results.append(FileResult(path=f.path, status=FileResultStatus.skipped,
                                          message=reason))
                warnings.append(f"{f.path}: skipped ({reason}).")
            else:
                try:
                    r = gen.document_file(f, tpl, req.output_language)
                    docs.append(r.markdown)
                    documented.append((f.path, r.status.value))
                    warnings.extend(r.warnings)
                    results.append(FileResult(path=f.path, status=r.status,
                                              message="; ".join(r.warnings) or None))
                except Exception as exc:  # unexpected bug for this file only
                    skipped.append((f.path, f"error: {exc}"))
                    results.append(FileResult(path=f.path, status=FileResultStatus.failed,
                                              message=str(exc)))
                    warnings.append(f"{f.path}: generation failed: {exc}")
            jobs.update(job_id, files_done=i, progress=round(i / total * 0.95, 3),
                        file_results=list(results), warnings=list(warnings))

        if not docs:
            raise ValueError("No documentation could be generated for any file")

        if req.scope == Scope.file and len(docs) == 1 and not skipped:
            result = docs[0]
        else:
            overview = render_overview(req.target, documented, skipped, req.output_language)
            result = "\n\n---\n\n".join([overview, *docs])

        msg = "Completed" if not warnings else f"Completed with {len(warnings)} warning(s)"
        jobs.update(job_id, status=JobStatus.completed, progress=1.0, message=msg,
                    result=result, file_results=results, warnings=warnings)
    except Exception as exc:
        jobs.update(job_id, status=JobStatus.failed, message="Failed", error=str(exc),
                    file_results=results, warnings=warnings)
