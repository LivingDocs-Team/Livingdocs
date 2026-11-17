# LivingDocs — Functional Requirements & Project Overview

Tài liệu tổng quan các chức năng được tổng hợp từ 6 đặc tả nền (`BE1.md` – `BE6.md`) và 3 đặc tả bổ sung (`LD-177.md`, `LD-404.md`, `LD-405.md`) của dự án LivingDocs. Mỗi chức năng có tài liệu riêng mô tả mục tiêu, vị trí mã nguồn, API/hợp đồng dữ liệu (nếu có), luồng xử lý, quy tắc nghiệp vụ, kiểm thử, tiêu chí chấp nhận và các giới hạn đã xác định.

## Functional Requirements

Các chức năng được chia theo các đặc tả Jira/snapshot tương ứng:

| File | Chức năng | Story / task Jira |
|---|---|---|
| [BE1.md](BE1.md) | Đồng bộ repository GitHub, tạo snapshot và cung cấp dữ liệu đầu vào cho bước phân tích | LD-63 |
| [BE2.md](BE2.md) | GitHub Actions CI và kiểm tra Documentation Drift đối với liên kết Markdown nội bộ | LD-376 |
| [BE3.md](BE3.md) | Container hóa các service và điều phối môi trường chạy bằng Docker Compose | LD-382 |
| [BE4.md](BE4.md) | Phân tích mã nguồn Java/Python bằng AST và tích hợp Code Analyzer vào Docker Compose | LD-397 |
| [BE5.md](BE5.md) | Cấu hình hệ thống tập trung (GitHub, Actions/Webhooks, ngôn ngữ, sinh tài liệu, auto-update, retention, AI và retrieval) | LD-273 |
| [BE6.md](BE6.md) | Giao diện quản trị & bảng điều khiển hệ thống (quản lý user/role/permission, workspace/repo, cấu hình, monitoring, audit/analytics, notification) | LD-316 (LD-317 – LD-321) |
| [BE7.md](BE7.md) | Documentation Change Log: ghi nhận actor, role, thời điểm, nguồn kích hoạt và trạng thái của từng thay đổi tài liệu; cung cấp API timeline | LD-177 |
| [BE8.md](BE8.md) | Kiểm tra triển khai sạch và xác minh luồng E2E/smoke test cho các service của LivingDocs | LD-404 |
| [BE9.md](BE9.md) | Xác minh migration Code–Documentation Relationship trên database mới/cũ, lựa chọn Flyway lineage và bảo toàn API/ràng buộc dữ liệu | LD-405 |

Mỗi file đặc tả chứa các thông tin cần thiết để triển khai hoặc tái tạo chức năng tương ứng. Các giá trị mặc định, giới hạn, mã lỗi, trạng thái và tiêu chí kiểm thử được quy định trong file chi tiết.

## Thứ tự sử dụng và quan hệ giữa các chức năng

### 1. Luồng dữ liệu phân tích mã nguồn

1. **Repository Synchronization (`BE1.md` / LD-63)**  
   Người dùng chọn repository và yêu cầu đồng bộ. GitHub Integration Service xác minh quyền truy cập, lấy snapshot theo commit của nhánh được chọn, lọc file Java/Python và tạo dữ liệu `AnalysisInput`.

2. **Code Analyzer (`BE4.md` / LD-397)**  
   GitHub Integration Service chuyển danh sách file có nội dung đến `POST /api/v1/analyze-repo`. Code Analyzer phân tích AST, trích xuất class, function/method và endpoint; kết quả được trả riêng cho từng file.

3. **AI Service**  
   Kết quả phân tích cấu trúc code là dữ liệu đầu vào cho bước sinh tài liệu của AI Service. Logic sinh tài liệu thuộc AI Service, không thuộc Code Analyzer.

### 2. Luồng quản trị và cấu hình hệ thống

4. **System Configuration (`BE5.md` / LD-273)**  
   Backend cung cấp catalog cấu hình tập trung qua `/api/admin/system-configuration` cho 8 nhóm thiết lập (GitHub App & OAuth, GitHub Actions & Webhooks, ngôn ngữ hỗ trợ, sinh tài liệu, chính sách tự động cập nhật, thời hạn lưu log, AI model/confidence/token budget và indexing/retrieval). Hệ thống chỉ lưu các giá trị được administrator override trong bảng `system_settings` và tự trả về giá trị mặc định khi chưa có override.

5. **Administration & Dashboard Interface (`BE6.md` / LD-316)**  
   Giao diện quản trị SPA (`frontend/src/AdminDashboard.jsx`) cung cấp 6 phân mục nghiệp vụ (`Users & roles`, `Workspaces & repositories`, `System configuration`, `Health & monitoring`, `Audit & analytics`, `Notifications`), giao tiếp thông qua các endpoint `/api/admin/**` của Backend.

### 3. Quan hệ tài liệu–code và lịch sử thay đổi tài liệu

6. **Code–Documentation Relationship (`BE9.md` / LD-405)**  
   GitHub Integration Service lưu tài liệu (`documentation_artifacts`), code entity (`code_entities`) và liên kết giữa chúng (`documentation_code_relationships`). Các entity code được nhận diện bằng `stable_key`; khi entity biến mất khỏi snapshot phù hợp, hệ thống đánh dấu inactive thay vì xóa liên kết, và có thể kích hoạt lại entity cũ khi nó xuất hiện trở lại. Migration lineage được chọn dựa trên lịch sử Flyway hiện có để tránh xung đột version/checksum.

7. **Documentation Change Log (`BE6.md` / LD-177)**  
   Các luồng AI generation, chỉnh sửa thủ công, review workflow, rollback và GitHub webhook có thể ghi nhận event qua `DocumentationChangeLogService`. Client truy xuất timeline theo document ID, có thể lọc theo status và trigger source. Snapshot xác nhận API backend; chưa xác nhận component timeline frontend hoàn chỉnh.

### 4. Vận hành hạ tầng, CI/CD và xác minh triển khai

- **Docker & Deployment (`BE3.md` / LD-382):** đóng gói và khởi chạy các service hiện có bằng Docker Compose, quản lý phụ thuộc, healthcheck và dữ liệu PostgreSQL bằng named volumes.
- **GitHub Actions CI & Documentation Drift Guard (`BE2.md` / LD-376):** tự động kiểm tra khi push/PR hoặc chạy thủ công; kiểm tra liên kết Markdown nội bộ và chạy các job build/test của các module.
- **Deployment Verification (`BE8.md` / LD-404):** bổ sung quy trình kiểm tra triển khai sạch và smoke test/E2E để xác minh các service sau khi khởi chạy, bao gồm các luồng chính như sinh tài liệu, review, restart và persistence. Đây là bước xác minh triển khai; không đồng nghĩa với một cơ chế production deployment tự động.

### Sơ đồ luồng Code–Documentation Relationship và Change Log

```text
Repository Snapshot / Code Analyzer
              |
              v
   Code Entities (stable_key)
              |
              v
Documentation Artifacts <----> Documentation Code Relationships
              |
              v
     Documentation Change Log
              |
              v
 GET /api/documentation/{docId}/change-log
```

Sơ đồ thể hiện quan hệ logic giữa các chức năng. Change Log ghi nhận sự kiện thay đổi tài liệu; nó không thay thế nội dung tài liệu, bảng version hoặc bảng quan hệ tài liệu–code.

### Sơ đồ luồng dữ liệu phân tích

```text
Người dùng
    |
    v
Frontend
    |
    v
GitHub Integration Service
    |
    v
Repository Synchronization (BE1 / LD-63)
    |
    | Snapshot / AnalysisInput
    v
Code Analyzer (BE4 / LD-397)
    |
    | Kết quả phân tích AST
    v
AI Service
    |
    v
Sinh tài liệu
```

### Sơ đồ luồng quản trị và cấu hình hệ thống

```text
Administrator (Browser)
    |
    v
AdminDashboard (BE6 / LD-316)
    |  (Session Cookie + CSRF Token)
    v
Backend BFF (/api/admin/**)
    |
    +--> Users, Roles & Permissions (/api/admin/users, /api/admin/roles, /api/admin/permissions)
    +--> Notification Policies (/api/admin/notification-policies)
    +--> Audit & Analytics (/api/document-workflows/history-accessible, /api/admin/system-analytics)
    +--> System Configuration Catalog & Overrides (BE5 / LD-273: /api/admin/system-configuration)
              |
              v
         PostgreSQL (system_settings, users, roles, permissions, admin_user_audits)
```

### Sơ đồ luồng CI và triển khai

```text
Push / Pull Request / Manual Dispatch
    |
    v
GitHub Actions (BE2 / LD-376)
    |
    +--> Documentation Drift Verification
    +--> Backend Build and Test
    +--> Frontend Build
    +--> GitHub Integration Service Test
    +--> AI Service Test
    +--> AI Service Integration
    +--> Docker Compose Validation
    +--> Migration / Flyway lineage tests (LD-405)

Docker Compose (BE3 / LD-382, mở rộng tại BE4 / LD-397)
    |
    +--> PostgreSQL databases
    +--> Backend
    +--> Frontend
    +--> GitHub Integration Service
    +--> AI Service
    +--> Code Analyzer

Deployment Verification (LD-404)
    |
    +--> Clean deployment / service startup checks
    +--> E2E smoke test
    +--> Generation and review flow checks
    +--> Restart / persistence checks
```


## Quy ước chung

### Công nghệ chính

| Thành phần | Công nghệ / runtime |
|---|---|
| Backend | Java 21, Spring Boot (3.5 / 4.x), Spring Security, Spring Data JPA |
| Frontend | React (19), Vite, Node.js 24, Nginx |
| GitHub Integration Service | Java 21, Spring Boot |
| AI Service | Python 3.12, FastAPI, Uvicorn |
| Code Analyzer | Python 3.12, FastAPI, AST, `javalang` |
| Database | PostgreSQL 16; H2 dùng trong một số test |
| Container orchestration | Docker, Docker Compose |
| CI | GitHub Actions |
| Documentation Drift Guard | Python, `pathlib`, `re`, `urllib.parse` |
| Migration management | Flyway, migration lineage selector, PostgreSQL |

### API và dữ liệu giữa các service

- **Repository Sync (`BE1.md`):**
  - `POST /api/repositories/{id}/sync`
  - `GET /api/repositories/{id}/sync/latest`
  - `GET /api/repositories/{id}/sync/latest/analysis-input`
  - Yêu cầu header `X-User-Id` theo snapshot LD-63; trả metadata snapshot cho frontend và cung cấp source content riêng qua `analysis-input`.
- **Code Analyzer (`BE4.md`):**
  - `GET /health`
  - `POST /api/v1/analyze-repo`
  - Nhận payload `scope`, `target`, `files` (`path`, `language`, `content`); hỗ trợ phân tích AST cho `python` và `java`; trả trạng thái từng file: `ok`, `invalid`, `empty`, `unsupported`.
- **System Configuration (`BE5.md`):**
  - `GET /api/admin/system-configuration` và `GET /api/admin/system-configuration/{group}` (yêu cầu authority `SYSTEM_CONFIG_VIEW`).
  - `PATCH /api/admin/system-configuration/{group}` và `DELETE /api/admin/system-configuration/{group}` (yêu cầu authority `SYSTEM_CONFIG_UPDATE`).
  - Lưu trữ các giá trị administrator override trong bảng `system_settings`; giá trị chưa override dùng default khai báo trong `SystemConfigurationService`.
- **Administration & Dashboard (`BE6.md`):**
  - Quản lý user: `GET /api/admin/users`, `GET /api/admin/users/{id}`, `PATCH /api/admin/users/{id}`, `PATCH /api/admin/users/{id}/role`, `PATCH /api/admin/users/{id}/status`, `GET /api/admin/users/audit`.
  - Quản lý role & permission: `GET /api/admin/roles`, `GET /api/admin/permissions`, `PUT /api/admin/roles/{roleName}/permissions`.
  - Chính sách thông báo & phân tích: `GET/PUT/DELETE /api/admin/notification-policies`, `GET /api/admin/system-analytics`, `GET /api/document-workflows/history-accessible`.
- **Documentation Change Log (`BE7.md`):**
  - `GET /api/documentation/{docId}/change-log`: lấy timeline thay đổi của một tài liệu.
  - Query filter tùy chọn: `status`, `triggerSource`; kết quả sắp xếp `createdAt` giảm dần. `triggerSource` không hợp lệ trả HTTP `400`.
  - Response gồm document/repository/version, action, summary, actor ID/name/role, trigger source, status, reference ID và `createdAt`.
- **Code–Documentation Relationship (`BE9.md`):**
  - GitHub Integration Service cung cấp controller và service quản lý liên kết tài liệu với code entity; hợp đồng chi tiết nằm tại `services/github-integration-service/docs/documentation-code-relationship-contract.md`.
  - Schema gồm `documentation_artifacts`, `code_entities`, `documentation_code_relationships`; các unique/FK constraints bảo đảm không tạo liên kết trùng và cascade theo repository/tài liệu/code entity.
  - Việc chọn migration location do `FlywayMigrationLineageSelector` thực hiện dựa trên `flyway_schema_history`; đây là logic khởi động/migration, không phải REST API riêng.


### Docker và cổng dịch vụ

Các cổng được mô tả trong các snapshot:

| Service | Cổng |
|---|---:|
| Frontend (Nginx) | 3000 |
| Backend | 8080 |
| GitHub Integration Service | 8082 |
| AI Service | 8001 |
| Code Analyzer | 8000 |
| Backend PostgreSQL (host) | 5434 |
| GitHub Integration PostgreSQL (host) | 5433 |

- Các service giao tiếp nội bộ bằng hostname của service trong Docker Compose, không dùng `localhost` giữa các container.
- Database sử dụng named volumes để giữ dữ liệu khi container được recreate.
- Code Analyzer và AI Service được kết nối với GitHub Integration Service qua network nội bộ theo snapshot LD-397.
- Port debug của Code Analyzer và AI Service được bind vào `127.0.0.1` theo cấu hình LD-397.

### Cấu hình và bảo mật

- Không commit secret hoặc file `.env` chứa credential thật.
- Các secret như `TOKEN_ENCRYPTION_KEY`, GitHub client secret, webhook secret và `ANTHROPIC_API_KEY` phải cấu hình qua biến môi trường; không lưu các secret này trong bảng `system_settings` và không expose qua API cấu hình.
- Token GitHub không được trả về frontend hoặc truyền trực tiếp cho Code Analyzer.
- Code Analyzer nhận source content qua API và chạy bằng user không đặc quyền `analyzer` (UID `10001`).
- Các API quản trị `/api/admin/**` xác thực bằng session cookie, yêu cầu CSRF token cho request thay đổi dữ liệu, kiểm tra authority cụ thể trên Backend và ngăn administrator tự thay đổi role hoặc tự vô hiệu hóa tài khoản của chính mình. Khi gặp HTTP `401`, frontend phát event `livingdocs:unauthenticated`.

## Kiểm thử và tiêu chí chấp nhận tổng quan

- **LD-63 (`BE1.md`):** kiểm tra snapshot theo branch/commit, lọc file, giới hạn số lượng/kích thước, cảnh báo, xử lý lỗi GitHub, quyền sở hữu repository và payload `analysis-input`.
- **LD-376 (`BE2.md`):** kiểm tra local Markdown links, path traversal, external links, anchor-only links, ignored directories; xác minh trigger và các job CI.
- **LD-382 (`BE3.md`):** kiểm tra Compose config/build, trạng thái healthy của database và service, kết nối database, frontend port và khả năng giữ dữ liệu qua recreate.
- **LD-397 (`BE4.md`):** kiểm tra API health/analyze, Python/Java parsing, trạng thái từng file, trường hợp lỗi/rỗng/không hỗ trợ, non-root container và kết nối service qua network nội bộ.
- **LD-273 (`BE5.md`):** kiểm tra đọc danh sách/nhóm cấu hình, validation kiểu dữ liệu và miền giá trị, từ chối key ngoài catalog, lưu override kèm thông tin người cập nhật, reset nhóm về giá trị mặc định và kiểm soát quyền `SYSTEM_CONFIG_VIEW` / `SYSTEM_CONFIG_UPDATE` (`AdminSystemConfigurationControllerTest`, `SystemConfigurationServiceTest`).
- **LD-316 (`BE6.md`):** kiểm tra hiển thị đầy đủ 6 tab quản trị, tìm kiếm/lọc/phân trang user, đổi role và khóa/mở khóa user khác (chặn self-change), gán permission cho role, đồng bộ repository theo quyền workspace, chế độ read-only của `ConfigPanel`, 3 health probe trình duyệt, phân trang audit trail workflow và thông báo (`tests/test_frontend_admin.py` và các test controller/monitoring backend).
- **LD-177 (`BE7.md`):** kiểm tra ghi event, chuẩn hóa actor role, thứ tự timeline mới nhất trước, filter kết hợp status/trigger source, từ chối trigger source không hợp lệ, summary giới hạn 500 ký tự và migration bảng/index (`DocumentationChangeLogServiceTest`).
- **LD-405 (`BE9.md`):** kiểm tra database mới và database nâng cấp, nhận diện migration lineage theo tên script/checksum, xử lý lịch sử lỗi/không hợp lệ, bảo toàn unique/FK/cascade constraints, stable key và API liên kết tài liệu–code (`DocumentationCodeRelationshipMigrationTest`, `FlywayMigrationLineageSelectorTest`, `DocumentationCodeRelationshipApiTest`). CI có job `github-integration-test` chạy Maven verify theo workflow snapshot.
- **LD-404 (`BE8.md`):** kiểm tra clean deployment và các luồng smoke/E2E sau khi service khởi chạy, gồm sinh tài liệu/review, restart và persistence trên môi trường được hỗ trợ. Smoke test trong snapshot chưa bao phủ đầy đủ Staff Review/Manager Approval và chưa được xác nhận là tự động chạy trong CI.

## Không thuộc yêu cầu chức năng / giới hạn cần lưu ý

Các nội dung sau không được tự xem là chức năng đã có nếu không có đặc tả hoặc triển khai bổ sung:

- **LD-63 (`BE1.md`):** không bao gồm GitHub OAuth/đăng nhập, webhook, đồng bộ nền, Kafka, lưu lịch sử snapshot lâu dài hoặc phân tích AST; snapshot mới nhất chỉ lưu trong memory.
- **LD-376 (`BE2.md`):** không tự deploy production, không tự sửa Markdown link và không commit thay đổi ngược về repository.
- **LD-382 (`BE3.md`):** mô tả Docker Compose cho local/development/demo; không có Kubernetes, autoscaling, rolling deployment, ingress controller hoặc secret manager.
- **LD-397 (`BE4.md`):** chỉ phân tích cấu trúc code; không thực hiện chức năng sinh tài liệu AI và không đọc trực tiếp filesystem host.
- **LD-273 (`BE5.md`):** triển khai REST API và catalog cấu hình ở Backend; snapshot LD-273 chưa có màn hình giao diện chỉnh sửa cấu hình tương ứng trên Frontend. Việc bật thêm ngôn ngữ trong catalog không đồng nghĩa Code Analyzer đã hỗ trợ parse ngoài Java và Python.
- **LD-316 (`BE6.md`):**
  - `ConfigPanel` trên giao diện ở chế độ **read-only** (hiển thị runtime URL, build mode và drift severity rules từ `/api/documentation/drift/severity-rules`), chưa gọi API chỉnh sửa cấu hình của LD-273.
  - `WorkspacesPanel` chỉ hiển thị workspace mà tài khoản administrator sở hữu hoặc là thành viên, chưa có danh sách workspace toàn hệ thống.
  - `HealthPanel` chỉ thực hiện 3 kiểm tra mức trình duyệt (Backend API, Authentication session, GitHub Integration Service), chưa giám sát trực tiếp AI Service, Code Analyzer hay database.
  - `AuditPanel` hiển thị lịch sử workflow tài liệu và thống kê số lượng user theo trạng thái/role; chưa gọi endpoint `/api/admin/users/audit` hoặc `/api/admin/system-analytics`.
- **LD-177 (`BE7.md`):** API backend trả dữ liệu timeline nhưng snapshot frontend được rà soát chưa xác nhận component timeline riêng hoặc lời gọi endpoint change-log. Enum `DRIFT_SUGGESTION` tồn tại nhưng chưa xác định caller cụ thể; API timeline chưa thể hiện pagination/limit.
- **LD-404 (`BE8.md`):** smoke test chưa bao phủ đầy đủ các bước Staff Review/Manager Approval và chưa được xác nhận tự động hóa trong GitHub Actions CI. Không xem smoke test là bằng chứng thay thế cho kiểm thử đầy đủ trên mọi môi trường production.
- **LD-405 (`BE9.md`):** selector chỉ hỗ trợ các lineage/checksum đã được khai báo; lịch sử Flyway lạ, migration thất bại hoặc schema có bảng ứng dụng nhưng thiếu history sẽ bị từ chối thay vì tự sửa. Không tự chạy Flyway `repair`, xóa history hoặc đổi checksum migration đã áp dụng.

## Lưu ý về các snapshot và phiên bản

Chín tài liệu chức năng (`BE1.md` – `BE6.md`, `BE7.md`, `BE8.md`, `BE9.md`) được tổng hợp từ các snapshot/branch khác nhau. Chúng mô tả phạm vi của từng snapshot, không mặc nhiên là một bản triển khai duy nhất đã được hợp nhất hoàn chỉnh:

- **LD-382 (`BE3.md`)** mô tả cấu hình Docker Compose nền với các service và network mặc định; **LD-397 (`BE4.md`)** bổ sung Code Analyzer và phân tách các network nội bộ (`backend-network`, `github-internal`, `analysis-internal`).
- **LD-376 (`BE2.md`)** ghi rõ metadata Git của snapshot ZIP đang ở `main`, không khẳng định đó là toàn bộ lịch sử thay đổi của branch LD-376.
- **LD-273 (`BE5.md`)** cung cấp backend API `/api/admin/system-configuration`, trong khi **LD-316 (`BE6.md`)** xây dựng giao diện `AdminDashboard.jsx` dựa trên các API có sẵn tại thời điểm snapshot LD-316 (nên tab System configuration đang để read-only).
- **LD-405 (`BE9.md`)** mở rộng GitHub Integration Service với các migration lineage cho quan hệ tài liệu–code; **LD-177** bổ sung bảng change log trong `migration-common` (V10). Khi tích hợp hai thay đổi, cần kiểm tra đầy đủ thứ tự và location Flyway thực tế để bảo đảm migration common và lineage riêng không xung đột.
- **LD-404 (`BE8.md`)** là tài liệu xác minh triển khai/smoke test, không phải một service runtime mới hoặc một lớp orchestration thay thế Docker Compose.
- Khi triển khai tích hợp, cần đối chiếu `compose.yaml`, workflow, migration history và source code của branch/commit thực tế đang sử dụng để xử lý khác biệt giữa các snapshot.

## Tài liệu chi tiết

- [BE1.md — LD-63: Repository Synchronization](BE1.md)
- [BE2.md — LD-376: GitHub Actions CI and Documentation Drift](BE2.md)
- [BE3.md — LD-382: Docker & Deployment](BE3.md)
- [BE4.md — LD-397: Code Analyzer in Docker Compose](BE4.md)
- [BE5.md — LD-273: System Configuration](BE5.md)
- [BE6.md — LD-316: Administration & Dashboard Interface](BE6.md)
- [BE7.md — LD-177: Documentation Change Log](BE7.md)
- [BE8.md — LD-404: Deployment Verification & E2E Smoke Test](BE8.md)
- [BE9.md — LD-405: Verify Code Documentation Migration](BE9.md)