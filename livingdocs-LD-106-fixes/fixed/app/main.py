from fastapi import FastAPI

from app.analyzer import ASTAnalyzer
from app.extractor import EntityExtractor
from app.models import AnalyzeRequest, AnalyzeResponse, FileAnalysis
from app.reader import FileReader
from app.submission import router as submission_router

app = FastAPI(title="LivingDocs Backend Service", version="1.0.0")

# Router submission riêng (Sửa L01 - không ảnh hưởng healthcheck gốc)
app.include_router(submission_router)


# --- SỬA L01: GIỮ NGUYÊN HEALTHCHECK CONTRACT CỦA ANALYZER ---
@app.get("/")
async def root():
    return {"status": "ok", "service": "Analyzer & Backend Service"}


@app.get("/health")
async def health_check():
    # Khớp tests/test_api.py::test_health_endpoint và Docker Compose healthcheck (LD-397)
    return {"status": "ok", "service": "code-analyzer"}


def analyze_file(path: str, content: str, language: str | None) -> FileAnalysis:
    """LD-395: phân tích một file từ nội dung inline bằng AST thật.

    FileReader (kiểm tra ngôn ngữ/rỗng/BOM) -> ASTAnalyzer (parse) -> EntityExtractor (trích xuất).
    Mọi lỗi của từng file chỉ làm file đó có status != ok, không làm hỏng cả request.
    """
    result, code = FileReader.read_inline_content(path, content, language)
    if result.status != "ok":
        return result

    tree, error = ASTAnalyzer.parse_code(code, result.language)
    if error:
        result.status = "invalid"
        result.error = error
        return result

    try:
        if result.language == "python":
            classes, functions, endpoints = EntityExtractor.extract_python_entities(tree, code)
        else:  # java
            classes, functions, endpoints = EntityExtractor.extract_java_entities(tree, code)
    except Exception as exc:  # parser bên thứ ba có thể lỗi trên cú pháp lạ
        result.status = "invalid"
        result.error = f"Lỗi trích xuất thực thể: {exc}"
        return result

    result.classes = classes
    result.functions = functions
    result.endpoints = endpoints
    return result


@app.post("/api/v1/analyze-repo", response_model=AnalyzeResponse)
async def analyze_repo(request: AnalyzeRequest):
    """Nhận {scope, target, files[{path, content, language?}]}, trả {scope, target, files[...]}
    đúng contract ai-service (CONTRACT.md). `files` rỗng -> 422."""
    files = [analyze_file(f.path, f.content, f.language) for f in request.files]
    return AnalyzeResponse(scope=request.scope, target=request.target, files=files)
