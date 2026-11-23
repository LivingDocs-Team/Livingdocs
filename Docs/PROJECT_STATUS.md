# LivingDocs — Project Status (snapshot 2026-11-13)

Snapshot từ phân tích read-only; **không chạy lại test** trong lần onboarding này. Cập nhật khi trạng thái đổi.
Branch: `LD-310-Implement-Review-&-Approval-Interface` (HEAD `37f84e6`). 15 file đã sửa + 4 file untracked chưa commit.

## Jira (đọc qua Atlassian MCP)
LD-310 (Task, To Do, thuộc epic LD-286 Frontend Implementation); LD-311 Drift Review UI, LD-312 AI Suggestion Review UI, LD-313 Staff Review UI, LD-314 Manager Approval UI — đều **In Progress**. Commit LD-310 chỉ có 1 feat + 4 fix.

## 1. Implemented and verified (có test tự động; kết quả lần chạy gần nhất chưa tái xác nhận)
| Chức năng | Bằng chứng |
|---|---|
| Auth/admin backend (login, register, roles, users, workspace) | `backend/src/test/...` (AdminRole/AdminUser/UserLoginLogout/WorkspaceService…) |
| Staff Review Queue UI (LD-313) | `frontend/src/StaffReviewQueue.jsx`, `tests/test_staff_review_queue.py` (12 test). `test-results.xml` (19:34 13/11, không phải do onboarding): 26 tests, 0 fail |
| Manager Approval UI (LD-314) | `ManagerApprovalQueue.jsx`, `tests/test_manager_approval.py` (14 test) |
| AI Suggestion Review UI (LD-312) | `DocumentationSuggestionReview.jsx` (nhúng trong `DocumentationManagement.jsx:884`), `tests/test_documentation_suggestion_review.py` (8 test) |
| Drift severity UI | `DocumentationDrift.jsx`, `tests/test_frontend_drift.py` (13 test) |
| Document workflow API (submit/claim/release/reassign/staff-review/approve/reject/rollback/history) | `DocumentWorkflowController`, `DocumentWorkflowService`, `DocumentWorkflowServiceTest`, `DocumentWorkflowControllerTest` |
| Drift detection/classification/severity (AI service) | `ai-service/app/drift*.py`, `ai-service/tests/test_drift*.py` |

Lưu ý: UI test dùng **API bị mock (Playwright intercept)** → chưa chứng minh tích hợp thật FE↔BFF↔service.

## 2. Implemented but not tested (không thấy test tương ứng)
- `NotificationPreferences.jsx`, `Profile.jsx` (không thấy test riêng).
- `DocumentationSearch` có `DocumentationSearchHttpIntegrationTest` ở service nhưng không có E2E frontend riêng.

## 3. Partially implemented
- **LD-310 tổng thể**: 4 subtask đã có UI + test nhưng Jira vẫn In Progress; PR review fix đang diễn ra (commit `5164be6`).
- **Drift Review UI (LD-311)**: `DocumentationDrift.jsx` được mở rộng trong `f1c423f` (+202 dòng) nhưng chưa có bằng chứng nào cho "review/approve drift" riêng ngoài hiển thị/lọc báo cáo — cần đối chiếu acceptance criteria Jira.
- **Code–Documentation Relationship (LD-211)**: bảng `documentation_artifacts`, `code_entities`, `documentation_code_relationships`, `source_changes*`, `github_pull_requests`, `github_commits` chỉ có trong **migration SQL**. Không có JPA entity/service/controller tương ứng trong `services/github-integration-service/src/main` (grep: chỉ `FlywayMigrationLineageSelector`). Branch `LD-211-…` tồn tại riêng.
- **Technical review (TECHNICAL_LEAD)**: chỉ có permission trong `RoleCatalogInitializer` (comment ghi "not yet present").
- Documentation Management (LD-304): UI lớn (`DocumentationManagement.jsx` 1374 dòng); chưa đủ bằng chứng hoàn thành.

## 4. Missing / not found
- Không có `CLAUDE.md`, tài liệu kiến trúc/dev guide trước đây (README gốc chỉ chứa link).
- Không có backend E2E thật (Docker compose end-to-end) trong CI; chỉ có `scripts/Test-ServiceE2E.ps1`, `scripts/verify-compose.sh` (chưa đọc/chạy).
- Không có frontend unit test (chỉ lint/build + Playwright).

## 5. Currently broken / failing
Chưa xác nhận lỗi nào bằng cách chạy. Chưa chạy test trong onboarding.

## 6. Rủi ro kỹ thuật đã xác nhận (đọc code)
1. **Flyway lineage phức tạp**: 6 thư mục `db/migration-*` với thứ tự V5/V6/V7 khác nhau; `FlywayMigrationLineageSelector` dựa checksum cứng. Sai sót khi thêm migration dễ làm hỏng DB hiện có. Gần đây có 2 commit fix (`1ba57e6`, `37f84e6`).
2. **Backend dùng `ddl-auto=update`** (không migration) — schema backend thay đổi theo entity.
3. **Uncommitted change chạm auth/OAuth/compose**: `OAuth2SuccessController` (redirect theo `FRONTEND_URL`), `compose.yaml` (OAuth client id bắt buộc, bỏ placeholder → `docker compose` fail nếu thiếu `.env`), `nginx.conf`, `GitHubClient.java` (−60 dòng). Cần chủ sở hữu xác nhận trước khi commit; không thuộc LD-310.
4. **Tài liệu BFF lỗi thời**: `backend-bff-authentication.md` ghi GET/POST/DELETE & thiếu `/api/document-workflows`, nhưng code proxy cả PUT và document-workflows. BFF không proxy PATCH.
5. **CORS backend hard-code** origin dev (localhost:5173/5174/3000).
6. **6 stash cũ + tệp rác** (`debug.log` lỗi Chromium/ANGLE, `ld233-github-search.txt` 77KB, `test-report.html`) — dễ nhầm là công việc dở.
7. AI Service lưu documents/templates bằng file JSON (không DB) — rủi ro mất/đồng bộ dữ liệu.
8. Máy dev: `mvn` không trên PATH (chỉ có JDK 21, node, python, docker).

## 7. Cần xác minh thêm
- Acceptance criteria LD-311…314 trong Jira (chưa đọc description).
- Kết quả thật của backend + github-integration test suite hiện tại.
- Branch `LD-211` đã merge vào `main` chưa; quan hệ code–doc dùng ở đâu.
- Các route/permission còn lại của `DocumentWorkflowController` (PUT document, rollback) khớp UI.

## 8. Bước tiếp theo đề xuất
1. Chủ dự án quyết định xử lý 15 file uncommitted (commit riêng / branch riêng) — không do AI tự làm.
2. Chạy baseline test từng module và ghi kết quả vào mục 5.
3. Đối chiếu Jira LD-311…314 với code, chốt phần còn thiếu của LD-310.
4. Chỉ sau đó mới lập kế hoạch cho feature mới.

---

# Đối chiếu với yêu cầu giảng viên (cập nhật 2026-11-13)
Chi tiết từng yêu cầu: [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md). Phương pháp: đọc/grep code, **chưa chạy test**.

## Đã hoàn thành (có code + test)
Auth/RBAC/admin user-role, workspace & repository, kết nối GitHub (OAuth/App), sync repo, sinh tài liệu + template, drift detection/classification/severity, workflow review (claim/review/approve/reject/rollback/audit), Staff Queue UI, Manager Approval UI, AI Suggestion Review UI, mã hóa token.

## Đang triển khai / một phần
Documentation Management UI, search, version history & diff UI, GitHub OAuth login (thay đổi chưa commit), notification preferences, relationship code↔doc (chỉ SQL), liệt kê PR/commit đã ingest (chỉ client + bảng), queue filter/sort, Drift Review (LD-311).

## Chưa triển khai (không thấy trong code)
Tự động cập nhật doc khi PR/commit đổi (webhook, GitHub Actions); thông báo token/webhook hỏng; coverage gaps; merge policy; cấu hình loại doc cần approval; manager delegate; health dashboard/metrics/dependency graph/export; Technical review; cấu hình AI/retention/notification; Jira/Slack/GitLab; Kafka/DLQ/Redis; publish/commit tài liệu lên repo.

## Chưa đủ bằng chứng
NFR hiệu năng/availability/HTTPS; responsive & "≤3 thao tác"; comment theo section; clone/version template; "dismiss" suggestion; resolution status của drift; tamper-evident log; audit thao tác admin; UML/Detail Design.

## Nhận định
Lõi **review & approval + drift + generation** khá đầy đủ; phần **tự động hóa (auto-update, GitHub Actions, event-driven)** và **governance/dashboard cho Technical Lead/Admin** là khoảng trống lớn nhất so với đề cương. Mâu thuẫn cần quyết định: xem mục D trong PROJECT_REQUIREMENTS.md.

## Bổ sung sau khi đọc sâu (2026-11-13, đợt 1)
Đã đọc toàn bộ: `DocumentWorkflowService/Controller/Entity/Repository/Dtos`, `DocumentationGenerationService`, `DriftAnalysisService`, `StaffReviewQueue.jsx`, `ManagerApprovalQueue.jsx`, `DocumentationSuggestionReview.jsx`. Phát hiện đã xác nhận bằng code:
1. `REJECTED` là trạng thái cuối — không thể sửa và nộp lại (`submit` chỉ nhận `DRAFT`/`CHANGES_REQUESTED`).
2. `reassign` chỉ dành cho ADMINISTRATOR (đổi reviewer giữa các Staff), frontend không có UI cho thao tác này. (Đính chính: bản trước ghi "chỉ dành cho staff" là sai.)
3. `jobOwners` (generation) và `reportOwners` (drift) là `ConcurrentHashMap` trong bộ nhớ → mất quyền truy cập job/report sau khi service khởi động lại (`DocumentationGenerationService`, `DriftAnalysisService`); báo cáo drift ở AI service cũng lưu trong bộ nhớ theo comment trong code.
4. Drift chỉ chạy thủ công cho một PR (`POST /api/repositories/{id}/drift/analyze`); báo cáo drift **không gắn với workflow** (Manager UI ghi rõ điều này).
5. Queue Staff/Manager chỉ phân trang; danh sách ghi "Repository: Not included in workflow response" — chưa có filter/sort theo repo/template/severity/date.
6. Rollback: Manager chọn `sourceVersion` + lý do → AI service tạo version mới → workflow về `PENDING_STAFF_REVIEW` (phải review lại). Không có UI so sánh 2 version tùy ý.
7. Staff không sửa được nội dung khi review; Suggestion Review UI không có accept/dismiss (UI tự ghi chú điều này).
8. Backend kiểm tra: Manager không được tự quyết định nếu từng là staff reviewer của workflow đó.

Còn chưa đọc: ~16k dòng production (AI service `app/*.py`, analyzer, phần còn lại của GitHub service/backend/frontend) và toàn bộ test.

## Bổ sung sau khi đọc toàn bộ frontend (2026-11-13, đợt 2)
Đã đọc toàn bộ `frontend/src/*.jsx|js` (trừ `App.css`), `eslint.config.js`, `vite.config.js`, `nginx.conf`. Phát hiện đã xác nhận:
1. **Thiếu khâu nối UI → workflow (quan trọng nhất)**: không có chỗ nào trong frontend lưu tài liệu đã sinh (`POST …/documentation/jobs/{id}/document`), tạo workflow (`POST /api/document-workflows`) hay submit (`…/submit`). Staff Queue/Manager Queue/Suggestion Review (LD-312..314) chỉ hiển thị workflow tạo qua API; trong luồng UI hiện tại không ai tạo được workflow. Cần xác nhận với Jira xem việc này thuộc task nào.
2. `DocumentationManagement`: Save draft / Create version / Compare / Restore chỉ là state React (UI tự ghi chú "disappear when reloaded"); không dùng version API của AI service. Generate gửi cứng `outputLanguage: 'vi'`.
3. `Profile.jsx`, `NotificationPreferences.jsx` là **demo** (không gọi API); trang login có link "View demo profile".
4. Documentation / Search / Drift luôn dùng workspace cá nhân `ws-${userId}`; chỉ `RepositoryManagement` biết tới workspace quản lý (`/api/managed-workspaces`). Repo nằm trong workspace khác không dùng được ở các màn đó. Không có UI tạo workspace/quản lý member, không có UI admin (user/role).
5. `StaffReviewQueue` hiển thị cho mọi người dùng (không gate theo role) → user không phải Staff sẽ thấy lỗi 403; `ManagerApprovalQueue` thì gate theo `userRole === 'MANAGER'`.
6. Template: `useTemplates` dùng `FALLBACK_TEMPLATES` hardcode khi API lỗi (có thông báo cho người dùng); mọi user đều thấy `TemplateManager` (tạo/sửa/xóa custom template) — "chia sẻ cho cả installation", không phân quyền Technical Lead ở UI (quyền thực tế ở backend chưa đọc).
7. Điều hướng bằng state `page`, không router: reload trang luôn về `github` nếu còn session; không deep-link.
8. `githubApi` nhận `userId` nhưng không dùng (không gửi header) — vô hại.
9. Preview Markdown tự viết: escape HTML trước khi chèn, chỉ cho phép link http/https → không thấy lỗ hổng XSS rõ ràng.
Chưa đọc: `App.css` (4.5k dòng CSS), toàn bộ test frontend (`tests/*.py`).

## Bổ sung sau khi đọc `frontend/src/App.css` (2026-11-13, đợt 3)
`App.css` (4.494 dòng) là một file CSS toàn cục duy nhất, import ở `App.jsx` và `DocumentationManagement.jsx`. Đã xác nhận:
1. **Khối lặp/ghi đè nhau** (do nhiều task nối thêm vào cuối file): "Global styles" (mục 1–11) xuất hiện 2 lần (dòng ~1 và ~1881); style Repository Management nằm ở 5 khối (dòng ~581, 2279, 2553, 2708, 2803); style Documentation ở 3 khối (dòng ~1130, 2954, 3138). Selector trùng ≥3 lần: `.page`, `.login-card`, `.switch-page`, `.repository-*`, `.documentation-hint`, `.documentation-preview`. CSS đến sau thắng, nên giá trị "thực tế" khác với khối đọc đầu tiên (vd `.login-card` cuối cùng là max-width 420px, `.documentation-page` max-width 850px). Sửa giao diện phải kiểm tra khối cuối cùng của selector.
2. **Selector toàn cục ảnh hưởng mọi màn hình**: `[role="status"]` (khung xanh lá cho mọi thông báo/loading), `input { width:100%; margin-bottom:10px }`, `form button` (nền xanh). Các component mới dễ bị style ngoài ý muốn.
3. **Class CSS không còn được JSX dùng** (14): `github-account-info`, `github-avatar`, `github-demo-note`, `github-security-note`, `markdown-spacer`, `repository-demo-badge`, `repository-eyebrow`, `repository-header`, `repository-icon`, `repository-item-actions`, `repository-remove-button`, `repository-select-all`, `repository-visibility`, `repository-workspace-status`.
4. **Class dùng trong JSX nhưng không có rule riêng** (chỉ là hook/container, vô hại): `documentation-approval-history`, `documentation-progress`, `drift-loading`, `staff-review-history`, `staff-review-queue`, `manager-approval`, `suggestion-review`. Nút `documentation-primary-button` chỉ có rule riêng trong `.suggestion-edit`; còn lại nhận style từ `.documentation-page button`.
5. Có responsive breakpoints (480/600/640/700/760/900px) và `!important` ở vài chỗ (`.documentation-panel > label`, `.severity-border-*`). Không có dark mode, không CSS variables/design tokens.
Gợi ý (chưa thực hiện, cần duyệt): không dọn CSS trong phạm vi task review/approval; nếu dọn thì làm riêng và chạy lại E2E.

## Bổ sung sau khi đọc backend, GitHub service, AI service (2026-11-13, đợt 4)
Đã đọc: toàn bộ `backend/src/main` (controller/service/config), GitHub service: `GitHubConnectionService`, `RepositoryManagementService`, `RepositorySyncService`, `DocumentationSearchService`, `DocumentationTemplateService`, các controller chính, `InternalServiceAuthenticationFilter`, `TokenEncryptor`, `OAuthStateStore`; AI service: `main.py`, `versions.py`, `jobs.py`, `templates.py`, `internal_auth.py`. Phát hiện đã xác nhận bằng code:
1. **Workflow có ngõ cụt**: `REJECTED` là trạng thái cuối. Nếu Manager reject một bản **rollback**, document vẫn giữ version đã duyệt cũ nhưng workflow thành `REJECTED`; `rollback` yêu cầu `APPROVED` và `submit` chỉ nhận `DRAFT/CHANGES_REQUESTED` ⇒ không rollback/nộp lại được nữa.
2. **Workflow không gắn workspace**: `/api/document-workflows/**` không qua kiểm tra workspace ở BFF; Staff/Manager thấy workflow của mọi người dùng (theo permission), không phân tách theo workspace/repo.
3. **Template không phân quyền**: `DocumentationTemplateController`/`TemplateService` không kiểm tra quyền; mọi user đăng nhập tạo/sửa/xóa template (kho template của AI service dùng chung toàn hệ thống).
4. **Dữ liệu trong bộ nhớ, mất khi restart**: snapshot repo (`latestResults`), cache phân tích tìm kiếm, `jobOwners`, `reportOwners`, `OAuthStateStore` (comment code: "chuyển sang Redis khi nhiều instance"), và ở AI service: jobs/reports/outputs (`JobStore`), drift reports. Chỉ documents và custom templates của AI service được ghi ra file JSON (`DOCUMENTS_FILE`, `TEMPLATES_FILE`). Không scale ngang được.
5. **AI service chỉ bảo vệ `/internal/*` bằng secret**; `/generate`, `/jobs/*`, `/templates` (ghi), `/drift/*` không cần xác thực (cổng 8001 chỉ bind 127.0.0.1 trong compose). `/internal/documents/{id}` không kiểm tra owner (việc kiểm tra owner làm ở GitHub service).
6. **Tìm kiếm** chỉ quét docstring/signature từ Code Analyzer của snapshot repo — không tìm trong tài liệu đã sinh/đã lưu hay file Markdown.
7. **Workspace member chỉ đọc**: mọi thao tác sync/search/generate/drift đòi `OWNER` và kết nối GitHub của chính người gọi (`findOwned`), nên member của workspace quản lý chỉ xem danh sách repo.
8. **Backend auth**: `UserLoginController.login` tự đặt `SecurityContext` vào session mà không đổi session id (không thấy `changeSessionId`) ⇒ rủi ro session fixation, cần xác nhận bằng test; đăng ký/OAuth luôn tạo role `DEVELOPER`; không có cơ chế seed tài khoản ADMINISTRATOR đầu tiên (phải gán trong DB); `ddl-auto=update` cho backend DB.
9. `GitHubConnectionService`: refresh token có khóa theo user (in-memory lock) — đúng cho 1 instance; token mã hóa AES-GCM (`TokenEncryptor`), đổi `TOKEN_ENCRYPTION_KEY` làm kết nối thành INVALID.
10. Backend: thông báo lỗi và Javadoc của GitHub service trộn tiếng Việt/Anh (UI chuyển sang tiếng Anh qua `errorMessages.js`).
Chưa đọc: `ai-service/app/drift*.py`, `generator.py`, `retrieval.py`, `renderer.py`, … (~4.5k dòng); Code Analyzer `app/*.py`; `GitHubRepositoryFetcher`, `GitHubClient`, `sync/*`; entity/repository/dto còn lại; toàn bộ test Playwright và test backend/service/ai-service (~15k dòng).
