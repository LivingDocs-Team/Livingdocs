from app.submission import EvidenceDisplayService, StatusTracker, SubmissionWorkflow
from app.models import GroundingEvidence, GenerationStatus, DocumentationSubmission

@app.get("/api/v1/documents/{id}/evidence", response_model=List[GroundingEvidence])
def get_document_evidence(id: str):
    """LD-107/LD-108: Collect & Display Grounding Evidence."""
    return EvidenceDisplayService.get_document_evidence(id)


@app.get("/api/v1/documents/{id}/status", response_model=GenerationStatus)
def get_generation_status(id: str):
    """LD-109: Display Generation Status."""
    return StatusTracker.get_status(id)


@app.post("/api/v1/documents/{id}/submit", response_model=DocumentationSubmission)
def submit_documentation(id: str, submitted_by: str = "developer"):
    """LD-110: Implement Documentation Submission."""
    return SubmissionWorkflow.submit_documentation(id, submitted_by)
