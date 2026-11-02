from fastapi import FastAPI
from app.models import RepoAnalysisRequest, RepoAnalysisResponse
from app.submission import router as submission_router

app = FastAPI(title="Code Analyzer & Documentation Service")

app.include_router(submission_router)

@app.post("/api/v1/analyze-repo", response_model=RepoAnalysisResponse)
async def analyze_repo(request: RepoAnalysisRequest):
    return RepoAnalysisResponse(target=request.target, scope=request.scope, files=[])
