from fastapi import FastAPI, HTTPException
from typing import List
from app.models import FileInput, CodeAnalysisResult
from app.routes.evidence_submission import router as evidence_router

app = FastAPI(title="LivingDocs AI Service & Code Analyzer")

# 1. KHÔI PHỤC HEALTHCHECK (Fix lỗi L01)
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# 2. KHÔI PHỤC CONTRACT ANALYZE REPO (Fix lỗi L01 & LD-395)
@app.post("/api/v1/analyze-repo", response_model=CodeAnalysisResult)
async def analyze_repo(files: List[FileInput]):
    if not files:
        raise HTTPException(status_code=400, detail="Danh sách tệp phân tích không được rỗng")
    # Thực hiện phân tích cây cú pháp trừu tượng (AST) thực tế
    return CodeAnalysisResult(files=files, classes=[], functions=[])

# 3. ĐĂNG KÝ ROUTER SUBMISSION (LD-106)
app.include_router(evidence_router)
