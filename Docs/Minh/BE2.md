# LivingDocs — Đặc tả tái tạo chức năng CI và Documentation Drift Guard (snapshot LD-376)

> Tài liệu được tạo từ `LivingDocs-LD-376.zip`. Lưu ý: metadata Git trong ZIP cho thấy `HEAD` đang ở `main`, không phải branch `LD-376`; vì vậy tài liệu mô tả đúng những gì hiện diện trong snapshot, không khẳng định đây là toàn bộ thay đổi lịch sử của branch LD-376.

## 1. Mục tiêu

Snapshot này có pipeline GitHub Actions để tự động kiểm tra repository khi push/PR, đồng thời có chức năng **Documentation Drift Verification** kiểm tra các liên kết Markdown nội bộ bị hỏng. Pipeline kiểm tra nhiều thành phần độc lập: drift guard, backend, frontend, GitHub integration service, AI service, integration test và Docker Compose validation.

Hai phần cần được tái tạo:
1. Script Python kiểm tra link Markdown nội bộ.
2. Workflow GitHub Actions điều phối các job kiểm tra, tạo summary và lưu test artifacts.

## 2. Thành phần và vị trí file

- `.github/workflows/ci.yml`: workflow chính `LivingDocs CI`.
- `scripts/check_documentation_drift.py`: scanner tìm Markdown links và xác minh đích đến.
- `tests/test_documentation_drift.py`: unit tests cho scanner.
- `tests/`: các test backend/frontend/analyzer/AI/service khác được workflow gọi.
- `backend/pom.xml`, `frontend/package.json`, `ai-service/requirements.txt`, `services/github-integration-service/pom.xml`: cấu hình build/test của từng module.
- `compose.yaml`: file được job Docker Compose validation kiểm tra.

## 3. Documentation Drift Guard

### 3.1 Mục tiêu

Phát hiện liên kết local trong các file `.md` đang trỏ đến file/thư mục không tồn tại hoặc trỏ ra ngoài repository. External links như `https://...`, URI có scheme, protocol-relative URL và anchor-only links không bị kiểm tra như file local.

### 3.2 Cách tìm file Markdown

- Root dự án được xác định từ vị trí script: `Path(__file__).resolve().parents[1]`.
- Quét đệ quy `ROOT.rglob("*.md")`.
- Bỏ qua thư mục: `.git`, `node_modules`, `target`, `dist`, `.venv`, `venv`.

### 3.3 Cách nhận diện link

Script dùng hai regex:
- Inline Markdown link: `[...] (destination)`; không bắt image link (`![](...)`).
- Reference-style link definition: `[label]: destination`.

Destination có thể nằm trong dấu `<...>` hoặc dạng token không có khoảng trắng. Có thể có title sau destination.

### 3.4 Quy trình xác minh

Với từng file Markdown:
1. Đọc UTF-8, lỗi decode thay bằng ký tự thay thế.
2. Thu thập destination từ inline links và reference definitions.
3. URL-decode destination bằng `unquote`.
4. Parse bằng `urlsplit`.
5. Bỏ qua URL có scheme, protocol-relative URL (`//...`) và destination không có path (ví dụ anchor-only).
6. Resolve path tương đối từ thư mục chứa Markdown.
7. Kiểm tra path vẫn nằm trong repository root để chặn path traversal.
8. Báo lỗi nếu path resolve nằm ngoài root hoặc file/dir đích không tồn tại.

Thông báo lỗi:
- `link escapes repository: <raw destination>`
- `missing local link: <raw destination>`

Đường dẫn trong thông báo được hiển thị tương đối với repository root khi có thể.

### 3.5 CLI contract

Chạy tại root repository:

```bash
python scripts/check_documentation_drift.py
```

Kết quả:
- Không có lỗi: in `Documentation drift check passed: checked N Markdown files.` và exit code `0`.
- Có lỗi: in tiêu đề `Documentation drift detected: broken local Markdown links found.`, liệt kê từng lỗi và exit code `1`.

### 3.6 Test tối thiểu

`tests/test_documentation_drift.py` có hai test:
- `test_existing_local_markdown_link_passes`: link tới file tồn tại phải không có lỗi.
- `test_missing_local_markdown_link_is_reported`: link tới file không tồn tại phải có một lỗi chứa `missing local link`.

Khi tái tạo nên bổ sung kiểm thử path traversal, URL external, anchor-only, reference-style links, URL-encoded path và ignored directories mà không làm thay đổi contract hiện tại.

## 4. GitHub Actions workflow

### 4.1 Trigger

Workflow `LivingDocs CI` chạy khi:
- `push` lên `main` hoặc bất kỳ branch khớp `LD-*`.
- `pull_request` vào `main`.
- `workflow_dispatch` (chạy thủ công).

PR types trong snapshot: `opened`, `synchronize`, `reopened`, `ready_for_review`.

Permissions tối thiểu: `contents: read`.

Concurrency:
- Group theo `livingdocs-ci-${{ github.ref }}`.
- `cancel-in-progress: true`, hủy run cũ cùng ref khi có run mới.

### 4.2 Job Documentation Drift Verification

- Runner: `ubuntu-latest`.
- Timeout: 5 phút.
- Checkout bằng `actions/checkout@v4`.
- Setup Python 3.12 bằng `actions/setup-python@v5`.
- Chạy `python scripts/check_documentation_drift.py`.
- Cài `pytest`, `pytest-html`, chạy `python -m pytest -q tests/test_documentation_drift.py`.
- Dùng `GITHUB_STEP_SUMMARY` để ghi `Documentation drift: PASS` hoặc `FAIL`; khi fail hướng dẫn xem workflow logs.

### 4.3 Job Backend Build and Test

- Runner Ubuntu, timeout 15 phút.
- PostgreSQL service container:
  - DB `cnpm`
  - user/password `postgres`
  - port `5432`
  - healthcheck `pg_isready`.
- Setup Java Temurin 27, cache Maven theo `backend/pom.xml`.
- Kiểm tra các file README, pom và workflow tồn tại.
- Cấp quyền thực thi `backend/mvnw`.
- Chạy `./backend/mvnw --batch-mode --no-transfer-progress -f backend/pom.xml clean verify`.
- DB env: `jdbc:postgresql://localhost:5432/cnpm`, `postgres` / `postgres`.

### 4.4 Job Frontend Build

- Runner Ubuntu, timeout 10 phút.
- Setup Node.js 24 và npm cache theo `frontend/package-lock.json`.
- Trong `frontend/`: `npm ci`, `npm run lint`, `npm run build`.

### 4.5 Job GitHub Integration Service Test

Trong snapshot workflow:
- Setup Java 21.
- Build/test bằng Maven với H2 và GitHub mock.
- Chạy live test với GitHub API nếu có `GITHUB_LIVE_TEST=true`, `GITHUB_LIVE_REPO`, `GITHUB_TOKEN`.
- Upload `services/github-integration-service/target/surefire-reports/` bằng `actions/upload-artifact@v4`, `if: always()`.

### 4.6 Job AI Service Test

- Setup Python 3.12.
- Cài `ai-service/requirements.txt`.
- Chạy `python -m pytest -q` trong `ai-service`.

### 4.7 Job AI Service Integration

- Setup Python 3.12.
- Cài AI dependencies và analyzer dependency `javalang`.
- Khởi động analyzer trên port 8000 bằng Uvicorn.
- Khởi động AI service trên port 8001.
- Poll health/openapi để chờ cả hai service sẵn sàng.
- Chạy integration tests với `ANALYZER_URL=http://localhost:8000`, `AI_SERVICE_URL=http://localhost:8001`.
- Nếu fail, in log của hai service.

### 4.8 Docker Compose Validation

Workflow có job riêng để xác minh cấu hình Compose; giữ nguyên việc kiểm tra file Compose và cấu hình service ở workflow snapshot. Khi triển khai lại, dùng đúng các lệnh/steps trong `.github/workflows/ci.yml` của snapshot thay vì tự đổi sang deploy thật.

## 5. Những gì CI không làm

- Không tự deploy production.
- Không tự sửa link Markdown bị hỏng.
- Không commit thay đổi ngược về repository.
- Không thay thế unit/integration tests của từng module.
- Không nên đặt secret thật trực tiếp trong YAML; dùng GitHub Actions secrets.

## 6. Cấu trúc kết quả

Mỗi job có trạng thái pass/fail độc lập. Khi bất kỳ step bắt buộc nào thất bại, job tương ứng fail và workflow thể hiện trạng thái CI. Artifact test reports được upload theo `if: always()` ở job có cấu hình upload, để có thể xem báo cáo kể cả khi test fail.

## 7. Hướng dẫn tái tạo cho AI

1. Tạo `.github/workflows/ci.yml` với trigger, permission, concurrency như mục 4.
2. Viết scanner Python độc lập, không phụ thuộc framework web.
3. Dùng `pathlib`, `re`, `urllib.parse.unquote`, `urlsplit`, và `sys.exit` theo mô tả.
4. Đảm bảo scan inline links và reference links, không scan image links.
5. Ngăn path traversal bằng `resolve()` + `relative_to(ROOT)`.
6. Trả exit code `1` nếu có bất kỳ lỗi nào để GitHub Actions fail đúng.
7. Tạo unit tests và gọi chúng từ workflow.
8. Không biến drift guard thành công cụ crawl/kiểm tra URL internet; chỉ kiểm tra local file references.
9. Không tự thêm deployment, auto-fix hay quyền ghi repository.

## 8. Tiêu chí chấp nhận

- Push lên branch `LD-*` kích hoạt workflow.
- PR vào `main` kích hoạt workflow.
- Manual dispatch hoạt động.
- Markdown link local tồn tại được chấp nhận.
- Link local thiếu file bị báo lỗi và exit code khác 0.
- Link đi ra ngoài repository bị báo lỗi.
- External links và anchor-only links không bị coi là file thiếu.
- Thư mục cache/build được bỏ qua.
- Backend/frontend/service jobs chạy đúng runtime và lệnh đã mô tả.
- Báo cáo test được upload khi workflow job có cấu hình upload, kể cả khi test fail.
