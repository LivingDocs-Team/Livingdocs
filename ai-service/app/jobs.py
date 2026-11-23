"""Generation jobs: run in the background, expose status, progress, warnings and result."""
import json
import logging
import os
import pathlib
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .confidence import METHOD, average, level_of
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

logger = logging.getLogger("uvicorn.error.jobs")


@dataclass
class JobOutput:
    """What a completed job produced, kept per file so the result can be saved as a versioned
    document (LD-189) and later updated file by file (LD-128)."""
    scope: Scope
    target: str
    template_id: str
    template_name: Optional[str]
    output_language: str
    template_version: Optional[int] = None   # LD-227
    sections: List[Tuple[str, str, str, Optional[float]]] = field(default_factory=list)
    """(path, markdown, status, confidence) for every documented file, in request order."""
    skipped: List[Tuple[str, str]] = field(default_factory=list)   # (path, reason)
    confidence: Optional[float] = None
    source_snapshot: Optional[SourceSnapshot] = None
    evidence_report: Optional[JobReport] = None


class JobStore:
    """Jobs, their reports and outputs. With a directory (JOBS_DIR) a job is written to <dir>/<id>.json when it
    is created, changes status, or gets its report or output, and read back at startup, so a restart does not
    lose a result that was not saved yet. A job that was still running when the process stopped is marked failed
    because its work is gone."""

    def __init__(self, directory: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self.observed_since = now()
        self._jobs: Dict[str, Job] = {}
        self._reports: Dict[str, JobReport] = {}
        self._outputs: Dict[str, JobOutput] = {}
        self._dir = pathlib.Path(directory) if directory else None
        if self._dir:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._load()

    # ----- persistence -----
    def _persist(self, job_id: str) -> None:
        if not self._dir or job_id not in self._jobs:
            return
        output = self._outputs.get(job_id)
        report = self._reports.get(job_id)
        payload = {
            "job": self._jobs[job_id].model_dump(mode="json"),
            "report": report.model_dump(mode="json") if report else None,
            "output": None if output is None else {
                "scope": output.scope.value, "target": output.target, "template_id": output.template_id,
                "template_name": output.template_name, "output_language": output.output_language,
                "template_version": output.template_version, "sections": [list(item) for item in output.sections],
                "skipped": [list(item) for item in output.skipped], "confidence": output.confidence,
                "source_snapshot": output.source_snapshot.model_dump(mode="json") if output.source_snapshot else None,
                "evidence_report": output.evidence_report.model_dump(mode="json") if output.evidence_report else None,
            },
        }
        target = self._dir / f"{job_id}.json"
        temporary = target.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            os.replace(temporary, target)
        except OSError:
            logger.warning("Could not save documentation job %s", job_id, exc_info=True)

    def _load(self) -> None:
        for file in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                job = Job.model_validate(data["job"])
                if job.status in (JobStatus.pending, JobStatus.running):
                    job.status = JobStatus.failed
                    job.message = "Interrupted"
                    job.error = "The service restarted while this job was running. Generate the documentation again."
                    job.updated_at = now()
                self._jobs[job.id] = job
                if data.get("report"):
                    self._reports[job.id] = JobReport.model_validate(data["report"])
                out = data.get("output")
                if out:
                    snapshot = out.get("source_snapshot")
                    evidence = out.get("evidence_report")
                    self._outputs[job.id] = JobOutput(
                        scope=Scope(out["scope"]), target=out["target"], template_id=out["template_id"],
                        template_name=out.get("template_name"), output_language=out["output_language"],
                        template_version=out.get("template_version"),
                        sections=[tuple(item) for item in out.get("sections", [])],
                        skipped=[tuple(item) for item in out.get("skipped", [])], confidence=out.get("confidence"),
                        source_snapshot=SourceSnapshot.model_validate(snapshot) if snapshot else None,
                        evidence_report=JobReport.model_validate(evidence) if evidence else None)
            except Exception:  # one unreadable file must not stop the service from starting
                logger.warning("Ignoring unreadable job file %s", file, exc_info=True)

    def create(self, req: GenerateRequest, tpl: Optional[Template] = None) -> Job:
        job = Job(id=uuid.uuid4().hex, scope=req.scope, target=req.target,
                  template_id=req.template_id, files_total=len(req.files),
                  template_name=tpl.name if tpl else None,
                  template_version=tpl.version if tpl else None,
                  template_sections=list(tpl.sections) if tpl else [])
        with self._lock:
            self._jobs[job.id] = job
            self._persist(job.id)
        logger.info("Documentation job %s: %s", job.id, JobStatus.pending.value)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def set_report(self, report: JobReport) -> None:
        with self._lock:
            self._reports[report.job_id] = report
            self._persist(report.job_id)

    def get_report(self, job_id: str) -> Optional[JobReport]:
        return self._reports.get(job_id)

    def set_output(self, job_id: str, output: JobOutput) -> None:
        with self._lock:
            self._outputs[job_id] = output
            self._persist(job_id)

    def get_output(self, job_id: str) -> Optional[JobOutput]:
        return self._outputs.get(job_id)

    def list(self) -> List[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def count_outcomes(self, start: datetime, end: datetime) -> tuple[int, int]:
        counts = {JobStatus.completed: 0, JobStatus.failed: 0}
        with self._lock:
            for job in self._jobs.values():
                if job.status in counts and start <= job.updated_at < end:
                    counts[job.status] += 1
        return counts[JobStatus.completed], counts[JobStatus.failed]

    def update(self, job_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs[job_id]
            previous_status = job.status
            for k, v in changes.items():
                setattr(job, k, v)
            job.updated_at = now()
            if job.status != previous_status:
                log = logger.warning if job.status == JobStatus.failed else logger.info
                log("Documentation job %s: %s", job_id, job.status.value)
                self._persist(job_id)


jobs = JobStore(os.getenv("JOBS_DIR") or None)


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
        tpl = template or templates.at_version(req.template_id, req.template_version)
        if tpl is None:
            raise ValueError(f"Template '{req.template_id}'"
                             + (f" version {req.template_version}" if req.template_version else "")
                             + " not found")
        gen = generator or get_generator()
        for f in req.files:
            normalize(f)                  # unique entity names, module from path
        index = build_index(req)          # related code + documentation context for retrieval
        total = len(req.files)
        jobs.update(job_id, status=JobStatus.running, message="Generating documentation",
                    template_name=tpl.name, template_version=tpl.version,
                    template_sections=list(tpl.sections))

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
        overall = average(scores)
        report = JobReport(
            job_id=job_id,
            template_id=tpl.id,
            template_name=tpl.name,
            template_version=tpl.version,
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
            template_version=tpl.version,
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
