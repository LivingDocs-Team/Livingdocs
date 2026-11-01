from fastapi import FastAPI, HTTPException
from typing import List
from app.models import RepoAnalysisRequest, RepoAnalysisResponse
from app.evidence_models import GroundingEvidence, GenerationStatus, DocumentationSubmission
from app.submission import EvidenceCollector, StatusTracker, SubmissionWorkflow

app = FastAPI(title="Code Analyzer & Documentation Service")

@app.post("/api/v1/analyze-repo", response_model=RepoAnalysisResponse)
async def analyze_repo(request: RepoAnalysisRequest):
    return RepoAnalysisResponse(target=request.target, scope=request.scope, files=[])

@app.get("/api/v1/documents/{document_id}/status", response_model=GenerationStatus)
async def get_document_status(document_id: str):
    status = StatusTracker.get_status(document_id)
    if not status:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return status

@app.get("/api/v1/documents/{document_id}/evidences", response_model=List[GroundingEvidence])
async def get_document_evidences(document_id: str):
    return EvidenceCollector.get_evidences(document_id)

@app.post("/api/v1/documents/{document_id}/submit", response_model=DocumentationSubmission)
async def submit_document(document_id: str, submitted_by: str):
    try:
        return SubmissionWorkflow.submit_documentation(document_id, submitted_by)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/v1/documents/{document_id}/submission", response_model=DocumentationSubmission)
async def get_submission(document_id: str):
    submission = SubmissionWorkflow.get_submission(document_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission record not found")
    return submission
