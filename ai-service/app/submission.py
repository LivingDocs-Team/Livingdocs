class GenerationStatus(BaseModel):
    document_id: str
    status: str = Field(..., description="pending | running | completed | failed")
    progress_percentage: float = Field(0.0, ge=0.0, le=100.0)
    message: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class StatusTracker:
    """LD-109: Display Generation Status."""

    @staticmethod
    def get_status(job_id: str) -> GenerationStatus:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return GenerationStatus(
            document_id=job.id,
            status=job.status.value,
            progress_percentage=round(job.progress * 100, 2),
            message=job.message,
            warnings=job.warnings,
        )
class DocumentationSubmission(BaseModel):
    submission_id: str
    document_id: str
    submitted_by: str
    status: str = Field("submitted", description="submitted | approved | rejected")
    submitted_at: datetime = Field(default_factory=now)
    evidence_snapshot: List[GroundingEvidence] = Field(default_factory=list)


class SubmissionWorkflow:
    """LD-110: Implement Documentation Submission."""

    _submissions: Dict[str, DocumentationSubmission] = {}

    @classmethod
    def submit_documentation(cls, document_id: str, submitted_by: str) -> DocumentationSubmission:
        job = jobs.get(document_id)
        if not job:
            raise HTTPException(status_code=404, detail="Document not found")

        if job.status != JobStatus.completed or job.progress < 1.0:
            raise HTTPException(
                status_code=400,
                detail="Cannot submit document while generation is in progress or incomplete",
            )

        if document_id in cls._submissions:
            raise HTTPException(
                status_code=409, detail="Document is locked and already submitted"
            )

        evidence_list = EvidenceCollector.collect_from_job(document_id)
        if not evidence_list:
            raise HTTPException(
                status_code=422, detail="Missing grounding evidence for required sections"
            )

        submission = DocumentationSubmission(
            submission_id=f"sub-{uuid.uuid4().hex[:8]}",
            document_id=document_id,
            submitted_by=submitted_by,
            status="submitted",
            evidence_snapshot=evidence_list,
        )

        cls._submissions[document_id] = submission
        return submission

    @classmethod
    def get_submission(cls, document_id: str) -> Optional[DocumentationSubmission]:
        return cls._submissions.get(document_id)
