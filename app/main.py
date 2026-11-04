"""Main application entry point."""
from fastapi import FastAPI
from app.analyzer import CodeAnalyzer
from app.models import AnalysisRequest, AnalysisResponse

app = FastAPI(title="Code Analyzer API", version="1.0.0")
analyzer = CodeAnalyzer()

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_code(request: AnalysisRequest):
    return analyzer.analyze(request)
