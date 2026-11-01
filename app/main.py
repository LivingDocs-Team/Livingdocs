from fastapi import FastAPI, HTTPException, Status
from typing import List
from app.models import RepoAnalysisRequest, RepoAnalysisResponse
from app.evidence_models import GroundingEvidence, GenerationStatus, DocumentationSubmission
from app.submission import EvidenceCollector, StatusTracker, SubmissionWorkflow

app = FastAPI(title="Code Analyzer & Documentation Service")

@app.post("/api/v1/analyze-repo", response_model=RepoAnalysisResponse)
async def analyze_repo(request: RepoAnalysisRequest):
    # Logic phân tích repo hiện tại...
    return RepoAnalysisResponse(target=request.target, scope=request.scope, files=[])

# 🟢 Bổ sung các API cho LD-106 theo đúng yêu cầu của Leader
@app.get("/api/v1/documents/{document_id}/status", response_model=GenerationStatus)
async def get_document_status(document_id: str):
    status = StatusTracker.get_status(document_id)
    if not status:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return status

@app.get("/api/v1/documents/{document_id}/evidences", response_model=List[GroundingEvidence])
async def get_document_evidences(document_id: str):
    evidences = EvidenceCollector.get_evidences(document_id)
    return evidences

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
