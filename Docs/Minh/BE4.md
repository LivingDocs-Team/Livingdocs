# BE4 — LD-397 Code Analyzer trong Docker Compose

| Mục | Nội dung |
|---|---|
| Story Jira | LD-397 Code Analyzer trong Docker Compose |
| Task đã làm | — |
| Người thực hiện | — |
| Thành phần | `app/main.py`, `app/analyzer.py`, `app/reader.py`, `app/extractor.py`, `app/models.py`, `app/dependency.py`, `code-analyzer/requirements.txt`, `code-analyzer/Dockerfile`, `code-analyzer/Dockerfile.dockerignore`, `compose.yaml` |
| Tác nhân | GitHub Integration Service (gọi), AI Service (nhận kết quả) |

## 1. Mô tả

Đóng gói Code Analyzer thành service riêng và thêm vào stack Docker Compose. Analyzer nhận nội dung source file, phân tích cú pháp Java/Python, trích xuất cấu trúc code và trả dữ liệu có cấu trúc để AI Service sinh tài liệu. Chức năng gồm REST API nhận danh sách file, nhận diện ngôn ngữ, parse AST, trích xuất class/method/function/endpoint, trả trạng thái riêng cho từng file (`ok`/`invalid`/`empty`/`unsupported`), Dockerfile non-root có healthcheck và Compose wiring để GitHub Integration Service gọi analyzer qua DNS nội bộ.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| LD-397.1 | Cung cấp `GET /health` trả `{"status": "ok", "service": "code-analyzer"}`. |
| LD-397.2 | Cung cấp `POST /api/v1/analyze-repo` nhận `{scope, target, files}`; mỗi file có `path`, `language` (có thể thiếu) và `content`. |
| LD-397.3 | Nếu `files` rỗng, trả HTTP `422` với `The list of files to analyze must not be empty.` |
| LD-397.4 | Xác định language: dùng `file_input.language` nếu có, ngược lại gọi `FileReader.detect_language(path)`. |
| LD-397.5 | Nếu `content.strip()` rỗng → `status="empty"`, không gọi parser. |
| LD-397.6 | Nếu language không thuộc `python`/`java` → `status="unsupported"`, `error` nêu language không hỗ trợ. |
| LD-397.7 | Parse bằng `ASTAnalyzer.parse_code(content, language)`; parse lỗi → `status="invalid"`, đưa lỗi cú pháp vào `error`. |
| LD-397.8 | Parse thành công: Python → `EntityExtractor.extract_python_entities(tree, content)`; Java → `EntityExtractor.extract_java_entities(tree, content)`; trả `status="ok"` cùng `classes`, `functions`, `endpoints`. |
| LD-397.9 | Một file lỗi không làm dừng toàn bộ repository; tiếp tục xử lý file tiếp theo. |
| LD-397.10 | `ASTAnalyzer.parse_code(code, language)`: kiểm tra `code`/`language` là string; chuẩn hóa `strip().lower()`; `python` → `ast.parse`; `java` → `javalang.parse.parse`; khác → `Unsupported language: ...`. Python bắt `SyntaxError` (line + message) và exception chung (`AST Parse Error: ...`); Java bắt `javalang.parser.JavaSyntaxError` và exception chung (`Java AST Parse Error: ...`). |
| LD-397.11 | Response cấp cao giữ nguyên `scope`, `target`, danh sách `files`; mỗi `FileAnalysis` có `path`, `language`, `status`, các mảng `classes`/`functions`/`endpoints`/`error` tùy kết quả. |
| LD-397.12 | `code-analyzer/Dockerfile`: base `python:3.12-slim`, `WORKDIR /app`, set `PYTHONDONTWRITEBYTECODE=1`/`PYTHONUNBUFFERED=1`/`PIP_NO_CACHE_DIR=1`, copy `code-analyzer/requirements.txt` → `requirements.txt`, `pip install`, copy `app/` → `/app/app/`, tạo system user `analyzer` (UID `10001`, no home), `USER analyzer`, `EXPOSE 8000`, healthcheck (interval 30s/timeout 5s/start 10s/retries 3) gọi `/health` bằng urllib, CMD `uvicorn app.main:app --host 0.0.0.0 --port 8000`. |
| LD-397.13 | Compose service `code-analyzer`: `build.context: .`, `build.dockerfile: code-analyzer/Dockerfile`, image `livingdocs-code-analyzer:local`, host bind `127.0.0.1:8000:8000`, healthcheck `/health`, network `analysis-internal`. Giữ root build context (không đổi sang `./code-analyzer`). |
| LD-397.14 | `github-integration` cấu hình `CODE_ANALYZER_BASE_URL=http://code-analyzer:8000`, `AI_SERVICE_BASE_URL=http://ai-service:8001`; `github-integration` depends on healthy của `github-db`, `code-analyzer`, `ai-service`. |
| LD-397.15 | Network Compose: `backend-db`+`backend` dùng `backend-network`; `github-db`+`github-integration` dùng `github-internal`; `backend` nối `backend-network` + `github-internal`; `ai-service`+`code-analyzer`+`github-integration` nối `analysis-internal`. Port 8000/8001 chỉ bind `127.0.0.1` cho debug local. |
| LD-397.16 | Analyzer chạy non-root UID `10001`, không mount Docker socket, không nhận GitHub token, không cần API key LLM, không đọc filesystem host; chỉ nhận content trong request. |

## 3. API

| Method | Endpoint | Kết quả | Yêu cầu |
|---|---|---|---|
| GET | `/health` | `{"status": "ok", "service": "code-analyzer"}` | LD-397.1 |
| POST | `/api/v1/analyze-repo` | Response giữ `scope`, `target`, `files` với per-file analysis | LD-397.2 – LD-397.11 |
| GET | `/openapi.json` | OpenAPI schema (dùng để test/warmup) | LD-397.2 |
| POST | `/api/v1/analyze-repo` với `files=[]` | HTTP 422, `The list of files to analyze must not be empty.` | LD-397.3 |

Ví dụ body `/api/v1/analyze-repo`:

```json
{
  "scope": "repository",
  "target": "owner/repository",
  "files": [
    {"path": "src/service.py", "language": "python", "content": "class Service:\n    def run(self):\n        pass"},
    {"path": "src/Controller.java", "language": "java", "content": "class Controller {}"}
  ]
}