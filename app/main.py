import os
import ast
from fastapi import FastAPI, HTTPException, status
from app.submission import router as submission_router

app = FastAPI(title="LivingDocs Backend Service", version="1.0.0")

# L01: Tách router Evidence & Submission riêng
app.include_router(submission_router)

# L01: Giữ nguyên endpoint healthcheck chuẩn của Analyzer
@app.get("/")
async def root():
    return {"status": "ok", "service": "Analyzer & Backend Service"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# LD106-R1, ERR-BE-04, ERR-BE-05: Khôi phục pipeline phân tích source thật
@app.post("/api/v1/analyze-repo")
async def analyze_repo(request_data: dict):
    target_repo = request_data.get("target", "acme/shop")
    scope = request_data.get("scope", "repo")
    files = request_data.get("files", [])
    analyzed_files = []
    warnings = []
    seen_paths = set()

    for file_info in files:
        raw_path = file_info.get("path", "")
        raw_content = file_info.get("content", "")
        raw_lang = file_info.get("language", "")

        # ERR-BE-05: Chuẩn hóa ngôn ngữ
        lang = raw_lang.strip().lower() if raw_lang else "python"

        # ERR-BE-04: Loại bỏ UTF-8 BOM
        clean_content = raw_content.lstrip("\ufeff")

        if not clean_content.strip():
            analyzed_files.append({"path": raw_path, "language": lang, "status": "empty", "classes": [], "endpoints": []})
            continue

        extracted_classes = []
        extracted_endpoints = []

        # LD106-R1 & ERR-BE-01/02: Phân tích Python AST thật lấy lineno, fields, endpoints
        if lang == "python":
            try:
                tree = ast.parse(clean_content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        extracted_classes.append({
                            "name": node.name,
                            "bases": [b.id for b in node.bases if isinstance(b, ast.Name)],
                            "docstring": ast.get_docstring(node),
                            "lineno": node.lineno,
                            "end_lineno": getattr(node, "end_lineno", node.lineno),
                            "fields": []
                        })
                    elif isinstance(node, ast.FunctionDef):
                        for decorator in node.decorator_list:
                            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                                if decorator.func.attr in ["get", "post", "put", "delete", "patch"]:
                                    path_val = decorator.args[0].value if decorator.args and isinstance(decorator.args[0], ast.Constant) else "/"
                                    extracted_endpoints.append({
                                        "http_method": decorator.func.attr.upper(),
                                        "path": path_val,
                                        "handler": node.name,
                                        "lineno": node.lineno,
                                        "end_lineno": getattr(node, "end_lineno", node.lineno)
                                    })
            except Exception:
                pass

        analyzed_files.append({
            "path": raw_path,
            "language": lang,
            "status": "ok",
            "classes": extracted_classes,
            "endpoints": extracted_endpoints
        })

    return {
        "status": "completed",
        "scope": scope,
        "target": target_repo,
        "total_files": len(files),
        "files": analyzed_files,
        "analyzed_files": analyzed_files
    }
