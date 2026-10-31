# LivingDocs — Đặc tả tái tạo chức năng LD-397: Code Analyzer trong Docker Compose

> Tài liệu được trích xuất từ `Livingdocs-LD-397.zip`, branch `LD-397-Add-Code-Analyzer-to-Docker-Compose`. Đây là đặc tả cho service phân tích mã nguồn và tích hợp service đó vào Docker Compose; không trộn với đặc tả GitHub Actions hoặc Repository Synchronization.

## 1. Mục tiêu

Đóng gói Code Analyzer thành một service riêng và thêm nó vào stack Docker Compose của LivingDocs. Analyzer nhận nội dung source file, phân tích cú pháp Java/Python, trích xuất cấu trúc code và trả dữ liệu có cấu trúc để AI Service sinh tài liệu.

Chức năng gồm:
1. REST API nhận danh sách file cần phân tích.
2. Nhận diện ngôn ngữ, parse AST.
3. Trích xuất class, method/function và endpoint.
4. Trả trạng thái riêng cho từng file: `ok`, `invalid`, `empty`, `unsupported`.
5. Dockerfile chạy analyzer không bằng root user, có healthcheck.
6. Compose wiring để GitHub Integration Service gọi analyzer bằng DNS nội bộ.

## 2. Vị trí mã nguồn

### Analyzer

- `app/main.py`: FastAPI application, health endpoint và API phân tích repository.
- `app/analyzer.py`: `ASTAnalyzer`, parse Python bằng `ast`, Java bằng `javalang`.
- `app/reader.py`: nhận diện ngôn ngữ từ file path và chức năng đọc file.
- `app/extractor.py`: trích xuất class/function/endpoint từ AST.
- `app/models.py`: Pydantic request/response models.
- `app/dependency.py`: các dependency/helper nếu được dùng trong app.
- `code-analyzer/requirements.txt`: dependencies của image.
- `code-analyzer/Dockerfile`: build image và cấu hình runtime.
- `code-analyzer/Dockerfile.dockerignore`: loại nội dung không cần thiết khỏi build context nếu được áp dụng.
- `compose.yaml`: service `code-analyzer` và kết nối với các service liên quan.
- `scripts/check_documentation_drift.py`: không thuộc logic analyzer; không đưa vào analyzer module.

## 3. Công nghệ và runtime

- Python 3.12 slim.
- FastAPI.
- Uvicorn.
- Pydantic models.
- Python standard library `ast` cho Python.
- `javalang` cho Java.
- Container chạy user không đặc quyền `analyzer` với UID `10001`.
- Port nội bộ `8000`.

## 4. API contract

### 4.1 Health

`GET /health`

Response:

```json
{
  "status": "ok",
  "service": "code-analyzer"
}
```

Dùng cho Docker healthcheck và service discovery.

### 4.2 Analyze repository

`POST /api/v1/analyze-repo`

Input logic:
- `scope`: phạm vi phân tích, ví dụ `repository`.
- `target`: tên repo/module/file mục tiêu.
- `files`: danh sách file; mỗi item có `path`, `language` (có thể không cung cấp) và `content`.

Ví dụ:

```json
{
  "scope": "repository",
  "target": "owner/repository",
  "files": [
    {
      "path": "src/service.py",
      "language": "python",
      "content": "class Service:\n    def run(self):\n        pass"
    },
    {
      "path": "src/Controller.java",
      "language": "java",
      "content": "class Controller {}"
    }
  ]
}
```

Response cấp cao giữ nguyên `scope`, `target` và danh sách `files` đã phân tích. Mỗi `FileAnalysis` có `path`, `language`, `status`, và các mảng `classes`, `functions`, `endpoints` hoặc `error` tùy kết quả.

Nếu `files` rỗng, trả HTTP `422` với thông báo `The list of files to analyze must not be empty.`

## 5. Quy trình xử lý mỗi file

1. Nếu request không có file nào: trả `422`.
2. Xác định language:
   - Dùng `file_input.language` nếu client truyền.
   - Nếu thiếu, gọi `FileReader.detect_language(file_input.path)`.
3. Nếu `content.strip()` rỗng:
   - Trả `status="empty"`.
   - Không gọi parser.
4. Nếu language không thuộc `python`, `java`:
   - Trả `status="unsupported"`.
   - `error` nêu language không hỗ trợ.
5. Parse source bằng `ASTAnalyzer.parse_code(content, language)`.
6. Nếu parse lỗi:
   - Trả `status="invalid"`.
   - Đưa lỗi cú pháp vào `error`.
7. Nếu parse thành công:
   - Python: `EntityExtractor.extract_python_entities(tree, content)`.
   - Java: `EntityExtractor.extract_java_entities(tree, content)`.
   - Trả `status="ok"` cùng `classes`, `functions`, `endpoints`.
8. Tiếp tục xử lý file tiếp theo; một file lỗi không làm dừng toàn bộ repository.

## 6. Parser contract

`ASTAnalyzer.parse_code(code, language)`:
- Kiểm tra `code` là string; nếu không, trả `(None, error)`.
- Kiểm tra `language` là string.
- Chuẩn hóa language bằng `strip().lower()`.
- `python` → `ast.parse(code)`.
- `java` → `javalang.parse.parse(code)`.
- Ngôn ngữ khác → lỗi `Unsupported language: ...`.

Python parser:
- Bắt `SyntaxError`, trả thông tin line number và message.
- Bắt exception chung, trả `AST Parse Error: ...`.

Java parser:
- Bắt `javalang.parser.JavaSyntaxError`.
- Bắt exception chung, trả `Java AST Parse Error: ...`.

Không được đánh dấu toàn bộ request thất bại chỉ vì một file có syntax error.

## 7. Dockerfile

`code-analyzer/Dockerfile` trong snapshot:

- Base: `python:3.12-slim`.
- `WORKDIR /app`.
- Set:
  - `PYTHONDONTWRITEBYTECODE=1`
  - `PYTHONUNBUFFERED=1`
  - `PIP_NO_CACHE_DIR=1`
- Copy `code-analyzer/requirements.txt` vào image dưới tên `requirements.txt`.
- Cài dependencies bằng `pip install -r requirements.txt`.
- Copy source `app/` vào `/app/app/`.
- Tạo system user `analyzer`, không tạo home, UID `10001`.
- Chuyển sang `USER analyzer`.
- `EXPOSE 8000`.
- Healthcheck:
  - interval 30s
  - timeout 5s
  - start period 10s
  - retries 3
  - gọi `http://localhost:8000/health` bằng Python urllib.
- CMD: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

**Build context quan trọng:** Compose dùng root context `.` và Dockerfile `code-analyzer/Dockerfile`; vì vậy đường dẫn `COPY code-analyzer/requirements.txt` và `COPY app/ ./app/` được hiểu tương đối theo root context. Không đổi context sang `./code-analyzer` nếu không sửa tương ứng các COPY.

## 8. Docker Compose integration

### 8.1 Service `code-analyzer`

Trong `compose.yaml`:
- `build.context: .`
- `build.dockerfile: code-analyzer/Dockerfile`
- image: `livingdocs-code-analyzer:local`
- host debug port bind `127.0.0.1:8000:8000`
- healthcheck gọi `/health`.
- tham gia network `analysis-internal`.

### 8.2 Kết nối từ GitHub Integration Service

Service `github-integration` được cấu hình:
- `CODE_ANALYZER_BASE_URL=http://code-analyzer:8000`
- `AI_SERVICE_BASE_URL=http://ai-service:8001`

`code-analyzer` và `ai-service` cùng tham gia `analysis-internal`, do đó integration service gọi qua DNS service name, không gọi `localhost`.

`github-integration` phụ thuộc health condition của:
- `github-db`
- `code-analyzer`
- `ai-service`

Các service liên quan:
- `backend-db` và `backend` dùng `backend-network`.
- `github-db` và `github-integration` dùng `github-internal`.
- `backend` nối `backend-network` và `github-internal` để BFF gọi GitHub Integration.
- `ai-service`, `code-analyzer`, `github-integration` nối `analysis-internal` theo compose snapshot.

### 8.3 Port exposure

Port 8000 và 8001 chỉ bind vào `127.0.0.1` cho mục đích debug local. Giao tiếp service-to-service dùng network nội bộ. Port mapping không nên mở trên mọi interface khi không cần thiết.

## 9. Security và cấu hình

- Analyzer chạy non-root UID 10001.
- Không mount Docker socket vào analyzer.
- Không truyền GitHub token cho analyzer; analyzer chỉ nhận file content đã được integration service lấy.
- Không cần API key LLM cho chức năng AST parsing.
- Secret của GitHub Integration/Backend được lấy từ `.env`, không commit.
- Không thay đổi analyzer thành service có quyền đọc trực tiếp filesystem host; contract nhận content trong request.

## 10. Chạy và xác minh

Từ root repository:

```bash
docker compose config
docker compose build code-analyzer
docker compose up -d code-analyzer
docker compose ps
```

Kiểm tra health:

```bash
curl http://localhost:8000/health
```

Kiểm tra OpenAPI:

```bash
curl http://localhost:8000/openapi.json
```

Kiểm tra endpoint bằng JSON mẫu theo contract ở mục 4:

```bash
curl -X POST http://localhost:8000/api/v1/analyze-repo \
  -H "Content-Type: application/json" \
  -d @analysis-input.json
```

Trong PowerShell có thể dùng `Invoke-RestMethod` hoặc `Invoke-WebRequest`; khi gọi container từ container khác, dùng `http://code-analyzer:8000`.

## 11. Xử lý tình huống

| Tình huống | Kết quả |
|---|---|
| Không có file trong request | HTTP 422 |
| File content rỗng | file status `empty` |
| Language không hỗ trợ | file status `unsupported` |
| Python/Java syntax sai | file status `invalid`, kèm error |
| Parse thành công | file status `ok`, có entities |
| Một file lỗi trong danh sách | các file còn lại vẫn tiếp tục xử lý |
| Container chưa healthy | Compose chưa coi dependency là sẵn sàng |
| Analyzer không truy cập được từ integration | kiểm tra `analysis-internal`, service DNS và healthcheck |

## 12. Kiểm thử và tiêu chí chấp nhận

Tối thiểu:
1. `/health` trả `status=ok`, `service=code-analyzer`.
2. Python hợp lệ trích xuất class/function.
3. Java hợp lệ trích xuất class/method và endpoint theo khả năng extractor.
4. Python syntax error trả `invalid`.
5. Java syntax error trả `invalid`.
6. Empty file trả `empty`.
7. JS/unsupported language trả `unsupported`.
8. Request `files=[]` trả 422.
9. Nhiều file có trạng thái khác nhau vẫn trả đủ kết quả theo từng file.
10. Docker image build được với root build context.
11. Container chạy user UID 10001, port 8000, healthcheck healthy.
12. GitHub Integration Service có thể phân giải `code-analyzer` qua network `analysis-internal`.

## 13. Hướng dẫn cho AI tái tạo code

- Giữ phân tách `analyzer.py`, `reader.py`, `extractor.py`, `models.py`, `main.py`.
- Dùng AST parser tương ứng cho Python và Java; không thay bằng regex để trích xuất cấu trúc.
- Giữ trạng thái per-file, không fail cả repository khi một file lỗi.
- Giữ nguyên endpoint `/api/v1/analyze-repo`, `/health`, port 8000.
- Docker build context phải là repository root theo `compose.yaml` hiện tại.
- Giữ non-root runtime user và healthcheck.
- Kết nối integration service bằng hostname `code-analyzer`, không dùng localhost.
- Không đưa chức năng sinh tài liệu AI vào analyzer; AI Service là service riêng.
- Không đưa CI workflow hoặc drift scanner vào container analyzer.
