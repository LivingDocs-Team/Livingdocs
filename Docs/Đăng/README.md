# Functional Requirements — Tasks của Đăng (GitHub Integration Service)

Các chức năng do Lê Hiền Hải Đăng thực hiện, mỗi chức năng một file:

| File | Chức năng | Task Jira |
|---|---|---|
| [FR-GH-01](FR1.md) | Kết nối tài khoản GitHub (GitHub App, OAuth) | LD-53 (LD-54 – LD-57); LD-23 |
| [FR-GH-02](FR2.md) | Quản lý repository trong workspace | LD-58 (LD-59 – LD-62); LD-23 |
| [FR-GH-03](FR3.md) | Đồng bộ repository từ GitHub | LD-63: LD-64, LD-67 |
| [FR-GH-04](FR4.md) | Cung cấp dữ liệu mã nguồn cho Code Analyzer | LD-63; LD-23 (contract LD-395) |

Mỗi file gồm: mô tả, danh sách yêu cầu (FR-GH-xx.y), API, dữ liệu, luồng chính, luồng lỗi, quy tắc nghiệp vụ, tiêu chí chấp nhận và test liên quan. Các con số (giới hạn, thời gian, mã lỗi) là giá trị đang dùng trong code, để có thể dựng lại đúng hành vi.

## Thứ tự sử dụng

    FR-GH-01 kết nối GitHub → FR-GH-02 thêm repo vào workspace → FR-GH-03 đồng bộ repo
      → FR-GH-04 dữ liệu cho Code Analyzer → Code Analyzer (LD-328)
      → AI Service sinh tài liệu (FR-AI-01 – FR-AI-05 của Linh)

## Nền tảng chung của GitHub Integration Service

- Mã nguồn ở `services/github-integration-service`, package `com.livingdocs.github`: Java 21, Spring Boot 3.5, PostgreSQL 16 (bảng tạo bằng Flyway `V1__init_github_integration.sql`), chạy ở cổng 8082. Swagger UI: `/swagger-ui.html`; health check: `/actuator/health`.
- Trình duyệt không gọi thẳng service. Backend (BFF) chuyển tiếp `/api/github/**`, `/api/workspaces/**`, `/api/repositories/**`, `/api/documentation/**` sang service, gắn header `X-User-Id` (id người dùng đã đăng nhập) và `Authorization: Bearer <GITHUB_INTEGRATION_INTERNAL_SECRET>`. Request thiếu mã nội bộ bị từ chối `401 INTERNAL_SERVICE_AUTH_REQUIRED` (bộ lọc do Nhân thêm ở LD-396), trừ `GET /api/github/callback` và `/actuator/health`.
- Lỗi trả JSON `{"status", "code", "message", "timestamp"}`. Thiếu header hoặc tham số, body sai JSON: `400 BAD_REQUEST`; dữ liệu không qua validation: `400 VALIDATION_ERROR`; GitHub lỗi: `502 GITHUB_API_ERROR` với thông báo không chứa nội dung GitHub trả về.
- CORS cho `/api/**` theo `CORS_ALLOWED_ORIGINS` (mặc định `http://localhost:3000`, `http://localhost:5173`), cho phép đọc header `Retry-After`.
- Cấu hình bằng biến môi trường hoặc file `.env` đặt cạnh `pom.xml`: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_APP_SLUG`, `GITHUB_REDIRECT_URI`, `TOKEN_ENCRYPTION_KEY` (32 byte, Base64), `GITHUB_INTEGRATION_INTERNAL_SECRET`, `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`. Không commit file `.env`; `.env.example` chỉ chứa giá trị mẫu.

## Kiểm thử

Kiểm thử và CI không phải chức năng của sản phẩm nên không có file FR riêng:

- **LD-57, LD-62, LD-67:** test tự động của từng chức năng, liệt kê ở mục "Kiểm thử" cuối mỗi file FR. Chạy bằng `mvn verify` trong `services/github-integration-service` (database H2, GitHub giả lập).
- **LD-391 Test GitHub & CI/CD Integration:** job CI **GitHub Integration Service Test** trong `.github/workflows/ci.yml` (build và test, test với GitHub thật `GitHubRepositoryFetcherLiveTest`, lưu báo cáo test). Báo cáo kiểm thử: `services/github-integration-service/docs/github-test-report.md`.
- **LD-105 Test Documentation Preview & Editing** (thuộc LD-101 của Khôi): 14 test giao diện bằng Playwright cho màn hình Documentation Management (mở tài liệu vừa sinh, soạn thảo, xem trước, chặn HTML và script khi xem trước, lưu nháp, tạo và khôi phục phiên bản, so sánh, xuất Markdown) trong `tests/test_documentation_preview_editing.py`; chạy trong job CI **Frontend E2E Test**. Báo cáo: `frontend/docs/documentation-preview-editing-test-report.md`.

## Tài liệu liên quan

- `services/github-integration-service/README.md`: API, cách chạy service trên máy, chạy test, thử luồng kết nối thật.
- `services/github-integration-service/docs/repository-sync-contract.md`: contract của API đồng bộ.
- `services/github-integration-service/docs/frontend-api-guide.md`: hướng dẫn gọi API cho frontend.
- `services/github-integration-service/docs/samples/`: file JSON mẫu của kết quả đồng bộ, lỗi và dữ liệu cho phân tích.
