import os
from fastapi import FastAPI, HTTPException, status
from app.models import RepoAnalysisRequest, RepoAnalysisResponse, FileAnalysis

app = FastAPI(title="Source Code Analysis & AI Service", version="1.0.0")

# --- HEALTH CHECK ROUTES DÀNH CHO CI WORKFLOW (PORT 8000 & 8001) ---
@app.get("/")
async def root():
    return {"status": "ok", "generator": "offline"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "online"}
