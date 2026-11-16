# CLAUDE.md — LivingDocs

Chỉ chứa thông tin đã xác minh từ repository (2026-11-13). Trạng thái chi tiết/dễ thay đổi: [Docs/PROJECT_STATUS.md](Docs/PROJECT_STATUS.md).
Lưu ý: thư mục tài liệu là `Docs/` (Windows không phân biệt hoa/thường, đừng tạo thêm `docs/`).

## 1. Project Overview
LivingDocs: hệ thống tài liệu tự cập nhật có AI hỗ trợ cho nhóm kỹ sư. Kết nối GitHub repo → phân tích code → AI sinh tài liệu → phát hiện documentation drift → review (Staff) & approval (Manager).
Đây là dự án đang phát triển dở (nhiều branch `LD-xxx`, task Jira project `LD`). Không phải greenfield.

## 2. Technology Stack
- Frontend: React 19 + Vite 8, JavaScript (JSX, không TypeScript), ESLint 10, không dùng router/state lib (điều hướng bằng `page` state trong `App.jsx`).
- Backend/BFF: Spring Boot 4.1.1, Java 21, JPA + PostgreSQL, Spring Security (session + CSRF cookie + OAuth2 GitHub). `ddl-auto=update` (KHÔNG có Flyway ở backend).
- GitHub Integration Service: Spring Boot, Java 21, Flyway, JPA `ddl-auto=validate`, H2 cho test.
- AI Service: Python 3.12, FastAPI, Pydantic 2, `anthropic` SDK (dependencies pin trong `requirements.txt`, sinh từ `requirements.in`).
- Code Analyzer: Python FastAPI + tree-sitter (`app/`, deps `code-analyzer/requirements.txt`).
- E2E: pytest + Playwright (Python) trong `tests/`. CI: `.github/workflows/ci.yml`.

## 3. Repository Structure
- `frontend/` — React SPA (`src/*.jsx`), nginx.conf proxy `/api`, `/oauth2`, `/login/oauth2` → backend.
- `backend/` — package `com.cnpm.backend` (auth, admin, workspace, BFF proxy).
- `services/github-integration-service/` — package `com.livingdocs.github` (GitHub OAuth/App, repo sync, doc generation, drift, search, document workflow). Docs riêng ở `docs/`.
- `ai-service/` — `main.py` + `app/` (generator, drift_*, versions, templates). Hợp đồng: `ai-service/CONTRACT.md`.
- `code-analyzer/` Dockerfile + requirements; mã nguồn nằm ở thư mục gốc `app/` (`app/main.py`, `/api/v1/analyze-repo`).
- `tests/` — E2E Playwright + unit Python; `scripts/` — drift check, compose verify; `Docs/<member>/FR*.md` — functional requirements.

## 4. Architecture & Service Responsibilities
Browser → nginx(:3000) → **Backend**(:8080) → **GitHub Integration**(:8082) → **Code Analyzer**(:8000) / **AI Service**(:8001).
- Backend là BFF duy nhất browser được gọi. `GitHubIntegrationBffController` proxy `/api/github|workspaces|repositories|documentation|document-workflows/**`, thay Authorization bằng internal secret, gắn `X-User-Id`, `X-User-Authorities`, `X-Verified-Workspace-*`. Kiểm tra workspace membership ở backend.
- GitHub Integration: sở hữu `github-db` (repositories, connections, `document_workflows`, audit…), gọi GitHub API, Analyzer, AI Service. Chỉ nhận request có internal secret.
- AI Service: sinh tài liệu (jobs), templates, versioned documents (`/internal/documents/*`), drift (`/drift/*`). Lưu bằng file JSON (volume `ai-templates`).
- Mạng compose: `backend-network`, `github-internal`, `analysis-internal`. DB: `backend-db` (cnpm, host 5434), `github-db` (github_integration, host 5433).
- Workflow tài liệu: `DRAFT → PENDING_STAFF_REVIEW → STAFF_REVIEWING → PENDING_MANAGER_APPROVAL → APPROVED | REJECTED | CHANGES_REQUESTED` (`DocumentWorkflowStatus`, `DocumentWorkflowService`).

## 5. Development Environment
- Cần: JDK 21, Node (CI dùng 24), Python 3.12, Docker Desktop, PostgreSQL 16 (qua compose).
- Secrets nằm trong `.env` (gitignored). Mẫu: `.env.example`. KHÔNG đọc/in/commit giá trị trong `.env`.
- Backend env: `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`, `GITHUB_INTEGRATION_BASE_URL`, `GITHUB_INTEGRATION_INTERNAL_SECRET`, `FRONTEND_URL`, OAuth client id/secret.
- `mvn` có thể không có trên PATH máy dev; backend có `backend/mvnw`, GitHub service thì không có wrapper.

## 6. Build, Run & Test Commands (lấy từ CI / compose)
- Backend: `./backend/mvnw --batch-mode -f backend/pom.xml clean verify` (cần Postgres `cnpm`).
- GitHub Integration: `mvn -f services/github-integration-service/pom.xml verify` (H2, GitHub mock).
- Frontend: `cd frontend && npm ci && npm run lint && npm run build` (dev: `npm run dev`).
- AI Service: `cd ai-service && python -m pytest -q`.
- Analyzer tests: `python -m pytest -q -o addopts="" tests/test_analysis.py`.
- Frontend E2E: build frontend, `npx vite preview --port 3000 --strictPort`, rồi `python -m pytest -v tests/<file>.py` (cần `pytest-playwright`, `pytest-html`; `pytest.ini` ghi `test-report.html`, `test-results.xml`).
- Docker: `docker compose up --build` (chỉ chạy khi được yêu cầu — xem mục 12).

## 7. Coding Conventions
- Java: package theo lớp `controller/service/repository/entity/dto/config`; DTO riêng; method security bằng `@PreAuthorize("hasAuthority(...)")` ở backend.
- Frontend: mỗi tính năng một file `*.jsx` phẳng trong `frontend/src`, gọi API qua `githubApi.js` (`githubApi`, `githubApiText`), CSRF qua `csrf.js`, lỗi qua `errorMessages.js`.
- Commit message dạng `feat|fix(LD-xxx): ...`. Theo style code xung quanh, không refactor ngoài phạm vi.

## 8. API & Integration Rules
- Browser chỉ gọi Backend cùng origin `/api`. Không gọi trực tiếp :8082/:8001/:8000 từ frontend.
- Không dùng `X-User-Id` do client gửi làm bằng chứng danh tính; Backend tự suy ra.
- Có API thật → không mock/giả trong code production. Mock chỉ trong test (Playwright intercept).
- Thêm route mới ở GitHub Integration dưới prefix chưa được BFF proxy ⇒ phải cập nhật `GitHubIntegrationBffController` (hiện chỉ proxy GET/POST/PUT/DELETE; không có PATCH).
- Hợp đồng chi tiết: `services/github-integration-service/docs/*.md`, `ai-service/CONTRACT.md`.

## 9. Authentication & Authorization
- Login: form `/api/auth/login` (session) hoặc OAuth2 GitHub; CSRF cookie `XSRF-TOKEN` (`/api/auth/csrf`, header `X-XSRF-TOKEN`). `/api/**` chưa đăng nhập → 401. `/api/admin/**` yêu cầu role ADMIN/ADMINISTRATOR.
- Roles: DEVELOPER, STAFF, MANAGER, TECHNICAL_LEAD, ADMINISTRATOR (+ legacy ADMIN) và permissions `DOCUMENT_*` trong `RoleCatalogInitializer`. Workflow permission được enforce tại `DocumentWorkflowService` (authorities + role STAFF/MANAGER).
- `TECHNICAL_LEAD`/`DOCUMENT_TECHNICAL_REVIEW` mới chỉ có trong catalog, chưa có endpoint.
- Không sửa `SecurityConfig`, CORS, filter, role/permission khi chưa được duyệt.

## 10. Git & Branch Safety Rules
- Nhánh hiện tại khi onboarding: `LD-310-Implement-Review-&-Approval-Interface` (tên chứa `&` — luôn đặt trong dấu nháy). Có nhiều thay đổi chưa commit (xem `git status`) và 6 stash — thuộc về người dùng.
- Không tự commit/push/merge/rebase/checkout/reset/stash/clean. Không xóa hay ghi đè thay đổi chưa commit. Không `--force`, `--no-verify`.
- Chỉ stage đúng file thuộc task khi được yêu cầu commit.

## 11. Testing & Verification Requirements
- Không nói "test passed" nếu chưa chạy; ghi rõ lệnh và kết quả thực tế. Nếu không chạy được, nói rõ.
- Thay đổi backend/security → chạy test liên quan (`BackendSecurityFilterChainTest`, `GitHubIntegrationBffControllerTest`, `DocumentWorkflowServiceTest`…).
- Thay đổi UI → lint + build + E2E file tương ứng trong `tests/`.
- Migration GitHub service: xem `FlywayMigrationLineageSelector` (nhiều thư mục `db/migration-*`); sửa migration phải cập nhật các lineage và chạy `FlywayMigrationLineageSelectorTest`.

## 12. Rules for AI-Assisted Development
- Trước khi sửa code: phân tích tác động + đề xuất kế hoạch, chờ duyệt; hỏi trước khi làm ngoài phạm vi.
- Không tự: đổi DB schema/migration, cài dependency/plugin/MCP, chạy Docker Compose, đổi auth/security config, refactor module không liên quan.
- Không hardcode dữ liệu để che lỗi; không đọc/ghi secrets (`.env`, token, key) vào tài liệu hay log.
- Không coi tính năng là xong chỉ vì có component/API — cần test/bằng chứng.
- Tệp rác chưa theo dõi (`debug.log`, `ld233-github-search.txt`) không phải mã nguồn; đừng sửa/commit.

## 13. Links to Additional Docs
- [Docs/PROJECT_STATUS.md](Docs/PROJECT_STATUS.md) — trạng thái triển khai & rủi ro
- [services/github-integration-service/README.md](services/github-integration-service/README.md), `docs/backend-bff-authentication.md`, `docs/frontend-api-guide.md`, `docs/repository-sync-contract.md`, `docs/documentation-generation-contract.md`
- [ai-service/README.md](ai-service/README.md), [ai-service/CONTRACT.md](ai-service/CONTRACT.md), [frontend/README.md](frontend/README.md)
- `Docs/<member>/FR*.md` — functional requirements; Jira/SRS: liên kết trong [README.md](README.md)
