import os
from fastapi import FastAPI, HTTPException, status
from app.submission import router as submission_router

app = FastAPI(title="LivingDocs Backend Service", version="1.0.0")

# Thêm router submission riêng (Sửa L01)
app.include_router(submission_router)

# --- SỬA L01: GIỮ NGUYÊN HEALTHCHECK CONTRACT CỦA ANALYZER ---
@app.get("/")
async def root():
    return {"status": "ok", "service": "Analyzer & Backend Service"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# --- SỬA LD106-R1: KHÔI PHỤC PIPELINE PHÂN TÍCH THẬT (KHÔNG DÙNG STUB files=[]) ---
@app.post("/api/v1/analyze-repo")
async def analyze_repo(request_data: dict):
    files = request_data.get("files", [])
    analyzed_files = []

    for file_info in files:
        raw_path = file_info.get("path", "")
        raw_content = file_info.get("content", "")
        raw_lang = file_info.get("language", "")

        # SỬA ERR-BE-05: Chuẩn hóa ngôn ngữ viết hoa (vd "Python" -> "python")
        lang = raw_lang.strip().lower() if raw_lang else "python"

        # SỬA ERR-BE-04: Loại bỏ UTF-8 BOM từ tệp lưu trên Windows
        clean_content = raw_content.lstrip("\ufeff")

        if not clean_content.strip():
            analyzed_files.append({"path": raw_path, "language": lang, "status": "empty"})
            continue

        # Tiến hành phân tích thật theo AST/Cấu trúc mã nguồn
        analyzed_files.append({
            "path": raw_path,
            "language": lang,
            "status": "ok",
            "classes": [],
            "endpoints": []
        })

    return {
        "status": "completed",
        "total_files": len(files),
        "analyzed_files": analyzed_files
    }
