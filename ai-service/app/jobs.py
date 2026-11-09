"""Generation jobs: run in the background, expose status, progress, warnings and result."""
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .confidence import METHOD, level_of
from .generator import DocGenerator, get_generator
from .normalize import normalize
from .models import (
    FileReport,
    FileResult,
    FileResultStatus,
    GenerateRequest,
    Job,
    JobReport,
    JobStatus,
    Scope,
    SourceSnapshot,
    Template,
    now,
)
from .renderer import render_overview
from .retrieval import build_index, retrieve
from .templates import templates


@dataclass
class JobOutput:
    """What a completed job produced, kept per file so the result can be saved as a versioned
    document (LD-189) and later updated file by file (LD-128)."""
    scope: Scope
    target: str
    template_id: str
    template_name: Optional[str]
    output_language: str
    sections: List[Tuple[str, str, str, Optional[float]]] = field(default_factory=list)
    """(path, markdown, status, confidence) for every documented file, in request order."""
    skipped: List[Tuple[str, str]] = field(default_factory=list)   # (path, reason)
    confidence: Optional[float] = None
    source_snapshot: Optional[SourceSnapshot] = None
    evidence_report: Optional[JobReport] = None


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}
        self._reports: Dict[str, JobReport] = {}
        self._outputs: Dict[str, JobOutput] = {}

    def create(self, req: GenerateRequest, tpl: Optional[Template] = None) -> Job:
        job = Job(id=uuid.uuid4().hex, scope=req.scope, target=req.target,
                  template_id=req.template_id, files_total=len(req.files),
                  template_name=tpl.name if tpl else None,
                  template_sections=list(tpl.sections) if tpl else [])
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def set_report(self, report: JobReport) -> None:
        with self._lock:
            self._reports[report.job_id] = report

    def get_report(self, job_id: str) -> Optional[JobReport]:
        return self._reports.get(job_id)

    def set_output(self, job_id: str, output: JobOutput) -> None:
        with self._lock:
            self._outputs[job_id] = output

    def get_output(self, job_id: str) -> Optional[JobOutput]:
        return self._outputs.get(job_id)

    def list(self) -> List[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def update(self, job_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for k, v in changes.items():
                setattr(job, k, v)
            job.updated_at = now()


jobs = JobStore()


def skip_reason(error: Optional[str], status: str) -> str:
    """Analyzer message for a skipped file. Some parsers return only a label such as
    'JavaSyntaxError: ' with no detail; say so instead of showing an empty reason."""
    text = (error or "").strip()
    if not text:
        return f"analyzer status '{status}'"
    if text.endswith(":"):
        return f"{text.rstrip(':').strip()} (analyzer status '{status}', no details)"
    return text


def run_job(job_id: str, req: GenerateRequest, generator: Optional[DocGenerator] = None,
            template: Optional[Template] = None) -> None:
    """Executed by FastAPI BackgroundTasks. One bad file never stops the whole job.

    `template` is the snapshot taken when the job was created; without it the template is
    looked up now."""
    warnings: List[str] = []
    results: List[FileResult] = []
    file_reports: List[FileReport] = []
    try:
        tpl = template or templates.get(req.template_id)
        if tpl is None:
            raise ValueError(f"Template '{req.template_id}' not found")
        gen = generator or get_generator()
        for f in req.files:
            normalize(f)                  # unique entity names, module from path
        index = build_index(req)          # related code + documentation context for retrieval
        total = len(req.files)
        jobs.update(job_id, status=JobStatus.running, message="Generating documentation",
                    template_name=tpl.name, template_sections=list(tpl.sections))

        docs, documented, skipped, sections = [], [], [], []
        for i, f in enumerate(req.files, start=1):
            jobs.update(job_id, message=f"Documenting {f.path}")
            if f.status.value != "ok":
                reason = skip_reason(f.error, f.status.value)
                skipped.append((f.path, reason))
                results.append(FileResult(path=f.path, status=FileResultStatus.skipped,
                                          message=reason))
                file_reports.append(FileReport(path=f.path, status=FileResultStatus.skipped))
                warnings.append(f"{f.path}: skipped ({reason}).")
            else:
                try:
                    r = gen.document_file(f, tpl, req.output_language, retrieve(index, f))
                    docs.append(r.markdown)
                    documented.append((f.path, r.status.value, r.confidence))
                    sections.append((f.path, r.markdown, r.status.value, r.confidence))
                    warnings.extend(r.warnings)
                    results.append(FileResult(path=f.path, status=r.status,
                                              message="; ".join(r.warnings) or None,
                                              confidence=r.confidence))
                    if r.report:
                        file_reports.append(r.report)
                except Exception as exc:  # unexpected bug for this file only
                    skipped.append((f.path, f"error: {exc}"))
                    results.append(FileResult(path=f.path, status=FileResultStatus.failed,
                                              message=str(exc)))
                    file_reports.append(FileReport(path=f.path, status=FileResultStatus.failed))
                    warnings.append(f"{f.path}: generation failed: {exc}")
            jobs.update(job_id, files_done=i, progress=round(i / total * 0.95, 3),
                        file_results=list(results), warnings=list(warnings))

        if not docs:
            raise ValueError("No documentation could be generated for any file")

        # job confidence = mean over every documented entity (files weighted by size)
        scores = [e.confidence for fr in file_reports for e in fr.entities]
        overall = round(sum(scores) / len(scores), 2) if scores else None
        report = JobReport(
            job_id=job_id,
            template_id=tpl.id,
            template_name=tpl.name,
            template_instructions=tpl.instructions,
            template_sections=list(tpl.sections),
            confidence=overall,
            level=level_of(overall),
            method=METHOD,
            files=file_reports,
        )
        jobs.set_report(report)

        if req.scope == Scope.file and len(docs) == 1 and not skipped:
            result = docs[0]
        else:
            overview = render_overview(req.target, documented, skipped, req.output_language, overall,
                                       template_name=tpl.name)
            result = "\n\n---\n\n".join([overview, *docs])
        jobs.set_output(job_id, JobOutput(
            scope=req.scope,
            target=req.target,
            template_id=tpl.id,
            template_name=tpl.name,
            output_language=req.output_language,
            sections=sections,
            skipped=list(skipped),
            confidence=overall,
            source_snapshot=req.source_snapshot,
            evidence_report=report,
        ))
        msg = "Completed" if not warnings else f"Completed with {len(warnings)} warning(s)"
        jobs.update(job_id, status=JobStatus.completed, progress=1.0, message=msg,
                    result=result, file_results=results, warnings=warnings,
                    confidence=overall, confidence_level=level_of(overall))
    except Exception as exc:
        jobs.update(job_id, status=JobStatus.failed, message="Failed", error=str(exc),
                    file_results=results, warnings=warnings)
