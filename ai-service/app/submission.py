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
