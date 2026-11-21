# Functional Requirements — Tasks của Đăng (GitHub Integration Service)

Các chức năng do Lê Hiền Hải Đăng thực hiện, mỗi chức năng một file:

| File | Chức năng | Task Jira |
|---|---|---|
| [FR-GH-01](FR1.md) | Kết nối tài khoản GitHub (GitHub App, OAuth) | LD-53 (LD-54 – LD-57); LD-23 |
| [FR-GH-02](FR2.md) | Quản lý repository trong workspace | LD-58 (LD-59 – LD-62); LD-23 |
| [FR-GH-03](FR3.md) | Đồng bộ repository từ GitHub | LD-63: LD-64, LD-67 |
| [FR-GH-04](FR4.md) | Cung cấp dữ liệu mã nguồn cho Code Analyzer | LD-63; LD-23 (contract LD-395) |
<<<<<<< HEAD
=======
| [FR-GH-05](FR5.md) | Nhận Pull Request và commit từ GitHub (webhook, lấy bù khi đồng bộ) | LD-68 (LD-69 – LD-73) |
| [FR-GH-06](FR6.md) | Phát hiện thay đổi mã nguồn (file và code entity thay đổi) | LD-116 (LD-117 – LD-121) |
| [FR-GH-07](FR7.md) | Tìm tài liệu bị ảnh hưởng bởi thay đổi mã nguồn | LD-122 (LD-123 – LD-127) |
| [FR-USR-01](FR8.md) | Hồ sơ người dùng và tùy chọn thông báo (Backend) | LD-48 (LD-49 – LD-52) |
| [FR-DR-01](FR9.md) | Review drift: chấp nhận hoặc sửa gợi ý của AI khi xử lý finding | LD-161 (LD-162 – LD-166) |
| [FR-DR-02](FR10.md) | Lịch sử phân tích drift (lưu báo cáo và lịch sử xử lý qua các lần khởi động lại) | LD-167 (LD-168 – LD-172) |
>>>>>>> origin/main

Mỗi file gồm: mô tả, danh sách yêu cầu (FR-GH-xx.y, FR-USR-xx.y, FR-DR-xx.y), API, dữ liệu, luồng chính, luồng lỗi, quy tắc nghiệp vụ, tiêu chí chấp nhận và test liên quan. Các con số (giới hạn, thời gian, mã lỗi) là giá trị đang dùng trong code, để có thể dựng lại đúng hành vi.

<<<<<<< HEAD
=======
Trạng thái (20/11/2026): FR-GH-01 – FR-GH-07 và FR-USR-01 đã vào `main` (FR-GH-07: PR #116, FR-USR-01: PR #123). FR-DR-01 và FR-DR-02 (PR #151) đã xong, đang chờ review. Hai chức năng này chỉ có ở mức API: từ 17/11/2026 trang Documentation Drift đã bị gỡ khỏi web cho mọi role (dòng #16 của ma trận phân quyền, [Docs/rbac-screen-flow.md](../rbac-screen-flow.md)), nên phần giao diện của PR #151 đã được bỏ.

>>>>>>> origin/main
## Thứ tự sử dụng

    FR-GH-01 kết nối GitHub → FR-GH-02 thêm repo vào workspace → FR-GH-03 đồng bộ repo
      → FR-GH-04 dữ liệu cho Code Analyzer → Code Analyzer (LD-328)
      → AI Service sinh tài liệu (FR-AI-01 – FR-AI-05 của Linh)

<<<<<<< HEAD
=======
    Khi mã nguồn thay đổi:
    GitHub webhook push / pull_request → FR-GH-05 lưu commit, Pull Request
      → FR-GH-06 phát hiện file và code entity thay đổi (source change)
      → FR-GH-07 tìm tài liệu bị ảnh hưởng → cập nhật tài liệu (LD-128 của Linh)

    Khi kiểm tra drift của một Pull Request (chỉ qua API, xem trạng thái ở trên):
    FR-AI-05 – FR-AI-08 của Huy phát hiện, phân loại, đánh giá drift và AI review
      → FR-DR-01 người review chấp nhận hoặc sửa gợi ý của AI khi resolve finding
      → FR-DR-02 báo cáo và lịch sử xử lý được lưu, xem lại được sau khi AI Service khởi động lại

>>>>>>> origin/main
## Nền tảng chung của GitHub Integration Service

- Mã nguồn ở `services/github-integration-service`, package `com.livingdocs.github`: Java 21, Spring Boot 3.5, PostgreSQL 16 (bảng tạo bằng Flyway `V1__init_github_integration.sql`), chạy ở cổng 8082. Swagger UI: `/swagger-ui.html`; health check: `/actuator/health`.
- Trình duyệt không gọi thẳng service. Backend (BFF) chuyển tiếp `/api/github/**`, `/api/workspaces/**`, `/api/repositories/**`, `/api/documentation/**` sang service, gắn header `X-User-Id` (id người dùng đã đăng nhập) và `Authorization: Bearer <GITHUB_INTEGRATION_INTERNAL_SECRET>`. Request thiếu mã nội bộ bị từ chối `401 INTERNAL_SERVICE_AUTH_REQUIRED` (bộ lọc do Nhân thêm ở LD-396), trừ `GET /api/github/callback` và `/actuator/health`.
- Lỗi trả JSON `{"status", "code", "message", "timestamp"}`. Thiếu header hoặc tham số, body sai JSON: `400 BAD_REQUEST`; dữ liệu không qua validation: `400 VALIDATION_ERROR`; GitHub lỗi: `502 GITHUB_API_ERROR` với thông báo không chứa nội dung GitHub trả về.
- CORS cho `/api/**` theo `CORS_ALLOWED_ORIGINS` (mặc định `http://localhost:3000`, `http://localhost:5173`), cho phép đọc header `Retry-After`.
- Cấu hình bằng biến môi trường hoặc file `.env` đặt cạnh `pom.xml`: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_APP_SLUG`, `GITHUB_REDIRECT_URI`, `TOKEN_ENCRYPTION_KEY` (32 byte, Base64), `GITHUB_INTEGRATION_INTERNAL_SECRET`, `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`. Không commit file `.env`; `.env.example` chỉ chứa giá trị mẫu.

## Kiểm thử

Kiểm thử và CI không phải chức năng của sản phẩm nên không có file FR riêng:

<<<<<<< HEAD
- **LD-57, LD-62, LD-67:** test tự động của từng chức năng, liệt kê ở mục "Kiểm thử" cuối mỗi file FR. Chạy bằng `mvn verify` trong `services/github-integration-service` (database H2, GitHub giả lập).
- **LD-391 Test GitHub & CI/CD Integration:** job CI **GitHub Integration Service Test** trong `.github/workflows/ci.yml` (build và test, test với GitHub thật `GitHubRepositoryFetcherLiveTest`, lưu báo cáo test). Báo cáo kiểm thử: `services/github-integration-service/docs/github-test-report.md`.
- **LD-105 Test Documentation Preview & Editing** (thuộc LD-101 của Khôi): 14 test giao diện bằng Playwright cho màn hình Documentation Management (mở tài liệu vừa sinh, soạn thảo, xem trước, chặn HTML và script khi xem trước, lưu nháp, tạo và khôi phục phiên bản, so sánh, xuất Markdown) trong `tests/test_documentation_preview_editing.py`; chạy trong job CI **Frontend E2E Test**. Báo cáo: `frontend/docs/documentation-preview-editing-test-report.md`.

## Tài liệu liên quan

- `services/github-integration-service/README.md`: API, cách chạy service trên máy, chạy test, thử luồng kết nối thật.
=======
- **LD-57, LD-62, LD-67, LD-73, LD-121, LD-127, LD-52:** test tự động của từng chức năng, liệt kê ở mục "Kiểm thử" cuối mỗi file FR. Chạy bằng `mvn verify` trong `services/github-integration-service` (database H2, GitHub giả lập); phần AI Service của LD-127 chạy bằng `python -m pytest` trong `ai-service`; LD-52 chạy bằng `./backend/mvnw -f backend/pom.xml verify` (CI dùng PostgreSQL 18). Test giao diện bằng Playwright: `tests/test_repository_activity.py` (LD-73, LD-127), `tests/test_profile_preferences.py` (LD-52).
- **LD-166, LD-172:** `ai-service/tests/test_drift_review_history.py` (6 test, chạy bằng `python -m pytest` trong `ai-service`) và `DriftAnalysisServiceTest.acceptedSuggestionIsForwardedOnlyWhenResolving` (chạy bằng `mvn verify` trong `services/github-integration-service`). Hai test Playwright của PR #151 đã bị bỏ cùng trang Documentation Drift (FR-DR-01, FR-DR-02).
- **LD-391 Test GitHub & CI/CD Integration:** job CI **GitHub Integration Service Test** trong `.github/workflows/ci.yml` (build và test, test với GitHub thật `GitHubRepositoryFetcherLiveTest`, lưu báo cáo test). Báo cáo kiểm thử: `services/github-integration-service/docs/github-test-report.md`.
- **LD-105 Test Documentation Preview & Editing** (thuộc LD-101 của Khôi): 14 test giao diện bằng Playwright cho màn hình Documentation Management (mở tài liệu vừa sinh, soạn thảo, xem trước, chặn HTML và script khi xem trước, lưu nháp, tạo và khôi phục phiên bản, so sánh, xuất Markdown) trong `tests/test_documentation_preview_editing.py`; chạy trong job CI **Frontend E2E Test**. Báo cáo: `frontend/docs/documentation-preview-editing-test-report.md`.

## Tích hợp và sửa lỗi

Không phải chức năng mới nên không có file FR riêng:

- **LD-401 Resolve GitHub PR Ingestion Conflicts — PR #86** (Sprint 7, Done 12/11/2026): gộp `main` vào nhánh `LD-68-PR-Commit-Ingestion` để PR #86 (FR-GH-05, FR-GH-06) vào được `main` với CI xanh.
  - Đổi số migration của nhánh thành `V5`, `V6`, vì `main` đã có `V4` của LD-251.
  - Gộp hai bản `client/GitHubPullRequest` (của LD-146 và LD-68).
  - Đổi tên method lấy file Pull Request của nhánh thành `listPullRequestChangedFiles`, để không trùng `listPullRequestFiles` của LD-146.
  - Lấy bản LD-267 của `RepositoryManagement.jsx` làm gốc, gắn lại nút **PRs & commits**.
  - Sửa lỗi webhook có chữ ký đúng nhưng JSON hỏng trả `500`, nay trả `400`.
  - Thêm test theo tiêu chí nghiệm thu: chưa cấu hình webhook secret và JSON hỏng (xem FR-GH-05).
- **Sửa trùng migration V5 trên `main` — PR #122** (12/11/2026): PR #86 và PR #102 (LD-211 của Khôi) cùng vào `main` với migration `V5`, nên service không khởi động được (`Found more than one migration with version 5`) và job CI **GitHub Integration Service Test** đỏ trên `main`. Cách sửa: đổi `V5__documentation_code_relationships.sql` (vào sau) thành `V7__documentation_code_relationships.sql`, không sửa SQL vì các bảng của nó chỉ phụ thuộc `repositories` (`V1`). Máy nào đã chạy `V5` cũ của LD-211 cần xoá database `github-db` rồi chạy lại.
- **Gộp `main` vào PR #151** (20/11/2026): PR #153 (ma trận phân quyền) đã xoá `frontend/src/DocumentationDrift.jsx` và `tests/test_frontend_drift.py`, trong khi PR #151 sửa hai file này, nên PR bị conflict. Cách gộp: giữ việc xoá theo `main`, lấy `ci.yml` của `main`, bỏ các chỗ trong `ai-service/README.md` còn nhắc tới trang đã xoá. Sau khi gộp: AI Service 468 test pass (23 skipped), GitHub Integration Service 302 test pass (3 skipped).

## Tài liệu liên quan

- `services/github-integration-service/README.md`: API, cách chạy service trên máy, chạy test, thử luồng kết nối thật, cấu hình webhook cho GitHub App (FR-GH-05).
- `ai-service/README.md`: endpoint `POST /internal/affected-documents` (FR-GH-07); mục drift "Accept or edit the AI suggestion (LD-161)" và "Drift history (LD-167)" (FR-DR-01, FR-DR-02).
- `Docs/Huy/FR05.md` – `FR08.md`: phát hiện, phân loại, mức độ drift và AI review mà FR-DR-01, FR-DR-02 dựa vào.
>>>>>>> origin/main
- `services/github-integration-service/docs/repository-sync-contract.md`: contract của API đồng bộ.
- `services/github-integration-service/docs/frontend-api-guide.md`: hướng dẫn gọi API cho frontend.
- `services/github-integration-service/docs/samples/`: file JSON mẫu của kết quả đồng bộ, lỗi và dữ liệu cho phân tích.
