# FR-BE—04 Add Code Analyzer to Docker Compose

| Mục | Nội dung |
|---|---|
| Story Jira | LD-397 Add Code Analyzer to Docker Compose (blocks `LD-396 Repository-to-Documentation Orchestration`) |
| Task đã làm | — |
| Người thực hiện | Nguyễn Lê Minh |
| Thành phần | `app/main.py`, `app/analyzer.py`, `app/reader.py`, `app/extractor.py`, `app/models.py`, `app/dependency.py`, `code-analyzer/requirements.txt`, `code-analyzer/Dockerfile`, `code-analyzer/Dockerfile.dockerignore`, `compose.yaml`, `scripts/verify-compose.sh`, `Docs/Docker-Compose-Code-Analyzer.md`, `.github/workflows/ci.yml`, `tests/test_api.py`, `tests/test_analysis.py` |
| Tác nhân | GitHub Integration Service (gọi phân tích code qua HTTP nội bộ); AI Service (nhận kết quả phân tích để sinh tài liệu); Developers / DevOps (vận hành & kiểm thử local Docker Compose); GitHub Actions (`docker-compose-validation`) |

## 1. Mô tả

Chức năng đóng gói dịch vụ **Code Analyzer** (`code-analyzer/`, FastAPI, mã nguồn đặt tại `app/`) thành container độc lập và tích hợp vào môi trường Docker Compose MVP (`compose.yaml`). Code Analyzer tiếp nhận danh sách nội dung file mã nguồn qua REST API, nhận diện ngôn ngữ lập trình (Python/Java), phân tích cú pháp AST (`ast` / `javalang`), trích xuất cấu trúc mã nguồn (class, method, function, tham số, kiểu trả về, docstring, mã nguồn trích đoạn, số dòng, HTTP endpoint) và trả về kết quả phân tích theo từng file (`ok`, `empty`, `invalid`, `unsupported`). Hệ thống cấu hình mạng nội bộ (`analysis-internal`), healthcheck `/health`, ràng buộc `depends_on` (`condition: service_healthy`), biến môi trường `CODE_ANALYZER_BASE_URL=http://code-analyzer:8000` cho `github-integration`, kèm script xác minh tự động (`scripts/verify-compose.sh`) và tài liệu hướng dẫn local (`Docs/Docker-Compose-Code-Analyzer.md`).

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-BE—04.1 | Cung cấp endpoint `GET /health` trả về HTTP `200` với JSON `{"status": "ok", "service": "code-analyzer"}` phục vụ Docker Compose healthcheck và kiểm tra kết nối nội bộ. |
| FR-BE—04.2 | Cung cấp endpoint `POST /api/v1/analyze-repo` nhận payload `RepoAnalysisRequest` gồm `target`, `scope` (mặc định `"repository"`), `files` (`List[FileInput]`) và `options`; mỗi `FileInput` gồm `path`, `content` và `language` (tùy chọn). |
| FR-BE—04.3 | Khi danh sách `files` rỗng, trả về HTTP `422 Unprocessable Entity` với chi tiết `The list of files to analyze must not be empty.`. |
| FR-BE—04.4 | Xác định ngôn ngữ cho từng file: ưu tiên sử dụng `file_input.language` nếu client truyền vào; nếu không có thì gọi `FileReader.detect_language(path)` (`.py` → `python`, `.java` → `java`, `.rb` → `ruby`, còn lại → `unknown`). |
| FR-BE—04.5 | Nếu `file_input.content.strip()` rỗng, đánh dấu file có `status="empty"` và bỏ qua bước phân tích cú pháp AST. |
| FR-BE—04.6 | Nếu ngôn ngữ không thuộc `("python", "java")`, đánh dấu file có `status="unsupported"` kèm thông báo `error="Language '<lang>' is not supported."`. |
| FR-BE—04.7 | Phân tích cú pháp bằng `ASTAnalyzer.parse_code(content, lang)`: chuẩn hóa `language.strip().lower()`; Python dùng `ast.parse`, Java dùng `javalang.parse.parse`; nếu có lỗi cú pháp (`SyntaxError` kèm số dòng hoặc `JavaSyntaxError`), đánh dấu file có `status="invalid"` và đưa thông báo lỗi vào `error`. |
| FR-BE—04.8 | Khi parse thành công, trích xuất thực thể bằng `EntityExtractor.extract_python_entities` hoặc `EntityExtractor.extract_java_entities` gồm `classes` (`name`, `bases`, `docstring`, `methods`), `functions` (`name`, `signature`, `parameters`, `return_type`, `docstring`, `source` tối đa 1500 ký tự, `lineno`, `end_lineno`) và `endpoints` (route decorator FastAPI/Flask: `http_method`, `path`, `handler`, `parameters`), trả về `status="ok"`. |
| FR-BE—04.9 | Cô lập lỗi theo từng file: một file gặp trạng thái `empty`, `unsupported` hoặc `invalid` không làm dừng quá trình phân tích các file còn lại trong cùng request; response `RepoAnalysisResponse` giữ nguyên `scope` và `target`. |
| FR-BE—04.10 | `code-analyzer/Dockerfile`: sử dụng base image `python:3.12-slim`, `WORKDIR /app`, thiết lập `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, `PIP_NO_CACHE_DIR=1`, cài đặt dependencies từ `code-analyzer/requirements.txt` (`fastapi>=0.110`, `uvicorn[standard]>=0.29`, `pydantic>=2.6`, `javalang>=0.13.0`) và copy thư mục `app/` vào `/app/app/`. |
| FR-BE—04.11 | Bảo mật & healthcheck container trong `code-analyzer/Dockerfile` và `code-analyzer/Dockerfile.dockerignore`: tạo system user không đặc quyền `analyzer` (`useradd --system --no-create-home --uid 10001 analyzer`), chạy dưới `USER analyzer`, mở cổng `8000`, cấu hình `HEALTHCHECK` (`interval=30s`, `timeout=5s`, `start-period=10s`, `retries=3`) gọi `http://localhost:8000/health` qua `urllib.request`, chạy `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`; `.dockerignore` chỉ cho phép đưa `app/` và `code-analyzer/requirements.txt` vào build context. |
| FR-BE—04.12 | Cấu hình service `code-analyzer` trong `compose.yaml`: đặt `build.context: .` (root repository), `build.dockerfile: code-analyzer/Dockerfile`, `image: livingdocs-code-analyzer:local`, publish cổng debug cục bộ `127.0.0.1:8000:8000`, khai báo healthcheck `/health` và kết nối vào network `analysis-internal`. |
| FR-BE—04.13 | Kết nối `github-integration` với `code-analyzer` và `ai-service` trong `compose.yaml`: cấu hình biến môi trường `CODE_ANALYZER_BASE_URL: http://code-analyzer:8000` và `AI_SERVICE_BASE_URL: http://ai-service:8001` cho `github-integration`, đồng thời đặt `depends_on` tới `github-db`, `code-analyzer` và `ai-service` với `condition: service_healthy`. |
| FR-BE—04.14 | Phân tách mạng nội bộ Docker Compose (`networks`): `backend-network` (`backend-db`, `backend`, `frontend`), `github-internal` (`github-db`, `github-integration`, `backend`), và `analysis-internal` (`code-analyzer`, `ai-service`, `github-integration`); giới hạn bind cổng host về `127.0.0.1` cho các service nội bộ (`backend-db` `5434`, `github-db` `5433`, `backend` `8080`, `code-analyzer` `8000`, `ai-service` `8001`, `frontend` `3000`). |
| FR-BE—04.15 | Đảm bảo toàn bộ các service MVP hiện có (`backend-db`, `github-db`, `backend`, `ai-service`, `github-integration`, `frontend`) duy trì trạng thái `healthy`/`running` khi tích hợp thêm `code-analyzer`. |
| FR-BE—04.16 | Cung cấp script kiểm tra tự động `scripts/verify-compose.sh` (hỗ trợ tùy chọn `--no-up`) và tài liệu hướng dẫn `Docs/Docker-Compose-Code-Analyzer.md` để xác minh cấu hình Compose, chạy `docker compose up --build -d`, kiểm tra healthcheck toàn bộ stack và kiểm thử gọi API từ container `github-integration` tới `http://code-analyzer:8000` qua DNS service name. |
| FR-BE—04.17 | Cập nhật job `Docker Compose Validation` trong `.github/workflows/ci.yml` để build kiểm tra đồng thời 5 images: `backend`, `ai-service`, `code-analyzer`, `github-integration`, `frontend`. |

## 3. API / Giao diện

| Loại | Method / Endpoint / Lệnh | Kết quả | Yêu cầu |
|---|---|---|---|
| HTTP | `GET /health` | Trả về `{"status": "ok", "service": "code-analyzer"}` (HTTP 200) | FR-BE—04.1 |
| HTTP | `POST /api/v1/analyze-repo` | Phân tích danh sách file Python/Java, trả về `RepoAnalysisResponse` gồm `scope`, `target`, `files` (HTTP 200) | FR-BE—04.2, FR-BE—04.4 – FR-BE—04.9 |
| HTTP | `POST /api/v1/analyze-repo` (`files=[]`) | Trả về HTTP 422 với `detail: "The list of files to analyze must not be empty."` | FR-BE—04.3 |
| HTTP | `GET /openapi.json` | Trả về OpenAPI schema của dịch vụ Code Analyzer (HTTP 200) | FR-BE—04.2 |
| CLI | `docker compose -f compose.yaml up --build -d` | Build image `livingdocs-code-analyzer:local` cùng toàn bộ stack MVP và khởi chạy ở chế độ nền | FR-BE—04.12 – FR-BE—04.15 |
| CLI | `./scripts/verify-compose.sh` (`--no-up`) | Tự động kiểm tra `compose.yaml`, chờ healthcheck toàn bộ 7 services và test gọi `http://code-analyzer:8000` từ `github-integration` | FR-BE—04.16 |

Ví dụ request `POST /api/v1/analyze-repo`:

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