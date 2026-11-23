# FR-BE—06 Cấu hình hệ thống LivingDocs

| Mục | Nội dung | 
|---|---| 
| Story Jira | LD-273 – [System Configuration] Implement System Configuration (thuộc Epic `LD-13`) | 
| Task liên quan | `LD-274` Configure GitHub App & OAuth; `LD-275` Configure GitHub Actions & Webhooks; `LD-277` Configure Documentation Generation Settings; `LD-278` Configure Automatic Update Policies; `LD-279` Configure AI & Retrieval Settings | 
| Người thực hiện | Nguyễn Lê Minh | 
| Thành phần | Backend (`AdminSystemConfigurationController.java`, `SystemConfigurationService.java`, `SystemSetting.java`, `SystemSettingRepository.java`, `AdminUserAuditRetention.java`, Flyway migration `V9__create_system_settings.sql`); Security & RBAC (`ApiRoutePermissions.java`, `ScreenPermissions.java`, `RoleCatalogInitializer.java`, `administrator.flow.js`); GitHub Integration Service (`GitHubProperties.java`, `GitHubWebhookController.java`, `GitHubConnectionController.java`); AI Service (`app/generator.py`, `app/retrieval.py`, `app/confidence.py`, `app/templates.py`); Tests (`SystemConfigurationServiceTest.java`, `AdminSystemConfigurationControllerTest.java`, `AdminUserAuditRetentionTest.java`) | 
| Tác nhân | Quản trị viên hệ thống (`ADMINISTRATOR` / `ADMIN`); các dịch vụ nội bộ tiêu thụ tham số cấu hình (`AdminUserAuditRetention`, `GitHubIntegrationService`, `AIService`) | 
| Phạm vi | Quản lý tập trung 8 nhóm cấu hình vận hành của LivingDocs qua REST API `/api/admin/system-configuration`, lưu trữ giá trị ghi đè (override) trong bảng PostgreSQL `system_settings`, cơ chế fallback về giá trị mặc định/biến môi trường, kiểm tra phân quyền RBAC và bảo mật các khóa bí mật (secrets). | 

## 1. Mô tả

Chức năng cấu hình hệ thống (**System Configuration**) cung cấp khả năng quản lý tập trung toàn bộ các tham số vận hành của LivingDocs cho Quản trị viên (`ADMINISTRATOR`).

Hệ thống hỗ trợ 8 nhóm cấu hình bao phủ toàn bộ kiến trúc ứng dụng:

1. **GitHub App & OAuth (`github`):** Định danh công khai của GitHub App, OAuth scopes và các URL kết nối.

2. **GitHub Actions & Webhooks (`actions-webhooks`):** Đường dẫn workflow CI, danh sách check bắt buộc, bật/tắt webhook, danh sách event tiếp nhận và payload URL.

3. **Supported Source-Code Languages (`languages`):** Danh sách ngôn ngữ lập trình được bật để đồng bộ và phân tích mã nguồn.

4. **Documentation Generation (`generation`):** Ngôn ngữ tài liệu đầu ra, template mặc định, các section tạo tài liệu và số lần thử gọi AI tối đa.

5. **Automatic Update Policies (`auto-update`):** Bật/tắt cập nhật tài liệu tự động, sự kiện kích hoạt, nhánh áp dụng, ngưỡng mức độ trôi lệch tài liệu (drift severity) tối thiểu và yêu cầu duyệt trước khi xuất bản.

6. **Change-Log & Audit-Log Retention (`retention`):** Số ngày lưu trữ dữ liệu change log và audit log.

7. **AI Model & Confidence (`ai`):** Tên mô hình sinh tài liệu, mô hình embedding/retrieval, ngưỡng điểm tin cậy (confidence threshold) và ngân sách token tối đa.

8. **Indexing & Retrieval (`retrieval`):** Bật/tắt tái lập chỉ mục khi có thay đổi, số lượng kết quả code/tài liệu truy xuất, điểm tương đồng tối thiểu và giới hạn kích thước chunk/excerpt.

Kiến trúc triển khai bao gồm:

* **Chiến lược lưu trữ Override-only:** Bảng `system_settings` (`V9__create_system_settings.sql`) chỉ lưu giữ các tham số đã bị quản trị viên chỉnh sửa (`PATCH`). Các tham số chưa ghi đè sẽ tự động dùng giá trị mặc định trong `SystemConfigurationService.CATALOG` (hoặc fallback từ biến môi trường qua `envInt`).

* **Tách biệt thông tin bí mật (Secrets):** Các giá trị nhạy cảm (`GITHUB_CLIENT_SECRET`, `GITHUB_WEBHOOK_SECRET`, `TOKEN_ENCRYPTION_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_INTEGRATION_INTERNAL_SECRET`) được bảo vệ nghiêm ngặt qua biến môi trường, không nằm trong `CATALOG`, không lưu trong DB và bị API từ chối nếu gửi lên.

* **Tiêu thụ cấu hình:** Tác vụ `AdminUserAuditRetention` đọc trực tiếp `retention.auditLogDays` từ `SystemConfigurationService` ở mỗi chu kỳ chạy (`00:00 UTC`) để tự động xóa nhật ký quản trị quá hạn.

## 2. Yêu cầu chức năng

| ID | Yêu cầu | 
| ----- | ----- | 
| FR-BE—06.1 | **Danh mục cấu hình tập trung (Catalog):** Khai báo 32 tham số thuộc 8 nhóm cấu hình (`github`, `actions-webhooks`, `languages`, `generation`, `auto-update`, `retention`, `ai`, `retrieval`) kèm kiểu dữ liệu (`STRING`, `INT`, `DECIMAL`, `BOOLEAN`, `CHOICE`, `LIST`), giá trị mặc định, mô tả và các ràng buộc kiểm tra hợp lệ. | 
| FR-BE—06.2 | **Truy vấn danh sách và chi tiết nhóm cấu hình:** Cung cấp API cho phép tài khoản có quyền `SYSTEM_CONFIG_VIEW` truy vấn toàn bộ 8 nhóm hoặc từng nhóm cụ thể; trả về đầy đủ `value`, `defaultValue`, `min`, `max`, `allowedValues`, cờ `overridden`, `updatedAt` và `updatedBy`. | 
| FR-BE—06.3 | **Cập nhật cấu hình theo nhóm (Atomic PATCH):** Cung cấp API cho phép tài khoản có quyền `SYSTEM_CONFIG_UPDATE` cập nhật một hoặc nhiều tham số trong cùng một nhóm. Kiểm tra tính hợp lệ của toàn bộ payload trước khi lưu; từ chối toàn bộ giao dịch (`400 Bad Request`) nếu có bất kỳ lỗi nào. | 
| FR-BE—06.4 | **Khôi phục mặc định theo nhóm (Reset):** Cho phép tài khoản có quyền `SYSTEM_CONFIG_UPDATE` xóa toàn bộ giá trị ghi đè của một nhóm (`DELETE /api/admin/system-configuration/{group}`) để đưa các tham số của nhóm đó về giá trị mặc định trong `CATALOG`. | 
| FR-BE—06.5 | **Cấu hình GitHub App & OAuth (`LD-274`):** Quản lý `github.appSlug`, `github.clientId`, `github.redirectUri`, `github.oauthScopes`, `github.oauthBaseUrl` và `github.apiBaseUrl` tại backend; hỗ trợ kết nối/ngắt kết nối OAuth trên `github-integration-service`. | 
| FR-BE—06.6 | **Cấu hình GitHub Actions & Webhooks (`LD-275`):** Quản lý `actions.workflowFile`, `actions.requiredChecks`, `webhooks.enabled`, `webhooks.events` (`push`, `pull_request`) và `webhooks.payloadUrl`; tiếp nhận webhook tại `POST /api/github/webhook` và xác minh chữ ký `X-Hub-Signature-256`. | 
| FR-BE—06.7 | **Cấu hình ngôn ngữ mã nguồn hỗ trợ:** Quản lý danh sách `languages.enabled` (mặc định `java,python`) trong tập 15 ngôn ngữ chuẩn (`java`, `python`, `javascript`, `typescript`, `kotlin`, `go`, `ruby`, `php`, `csharp`, `c`, `cpp`, `rust`, `swift`, `scala`, `sql`). | 
| FR-BE—06.8 | **Cấu hình sinh tài liệu (`LD-277`):** Quản lý `generation.outputLanguage` (`vi`, `en`), `generation.templateId`, `generation.sections` (`Overview`, `Classes`, `Functions`, `API Endpoints`) và `generation.maxAttempts` (`1..10`, mặc định `3` hoặc `GENERATION_MAX_ATTEMPTS`). | 
| FR-BE—06.9 | **Cấu hình chính sách cập nhật tự động (`LD-278`):** Quản lý `autoUpdate.enabled`, `autoUpdate.triggers`, `autoUpdate.branches` (hỗ trợ wildcard `*`), `autoUpdate.minDriftSeverity` (`low`, `medium`, `high`, `critical`) và `autoUpdate.requireReview` (mặc định `true`). | 
| FR-BE—06.10 | **Cấu hình retention Change Log & Audit Log:** Quản lý `retention.changeLogDays` (`30..3650`, mặc định `365` hoặc `RETENTION_CHANGE_LOG_DAYS`) và `retention.auditLogDays` (`30..3650`, mặc định `730` hoặc `ADMIN_USER_AUDIT_RETENTION_DAYS`). `AdminUserAuditRetention` đọc giá trị này để dọn dẹp DB tự động. | 
| FR-BE—06.11 | **Cấu hình AI Model & Confidence (`LD-279`):** Quản lý `ai.model`, `ai.embeddingModel`, `ai.confidenceThreshold` (`0..1`, mặc định `0.5`) và `ai.tokenBudget` (`256..64000`, mặc định `4096`). | 
| FR-BE—06.12 | **Cấu hình Indexing & Retrieval (`LD-279`):** Quản lý `indexing.reindexOnChange`, `retrieval.codeResults` (`0..20`), `retrieval.docResults` (`0..20`), `retrieval.minScore` (`0..1`), `retrieval.chunkChars` (`200..10000`) và `retrieval.excerptChars` (`100..5000`). | 

## 3. Các nhóm cấu hình

### 3.1. Nhóm `github` – GitHub App & OAuth

| Key | Kiểu | Mặc định | Ràng buộc / Ý nghĩa | 
| ----- | ----- | ----- | ----- | 
| `github.appSlug` | `STRING` | `livingdocs-dev-hai` | Regex `^[A-Za-z0-9][A-Za-z0-9-]{0,99}$`; slug dùng tạo URL cài đặt GitHub App. | 
| `github.clientId` | `STRING` | `""` | Regex `^[A-Za-z0-9._-]{0,100}$`; OAuth Client ID công khai của GitHub App. | 
| `github.redirectUri` | `STRING` | `http://localhost:8082/api/github/callback` | Regex `^https?://[^\s,]+$`; callback URI khớp với cấu hình trên GitHub. | 
| `github.oauthScopes` | `LIST` | `read:user,user:email` | Tối thiểu 1 phần tử, tối đa 20 phần tử; mỗi item khớp `^[a-z][a-z:_]{0,49}$`. | 
| `github.oauthBaseUrl` | `STRING` | `https://github.com` | Regex `^https?://[^\s,]+$`; URL gốc của GitHub OAuth. | 
| `github.apiBaseUrl` | `STRING` | `https://api.github.com` | Regex `^https?://[^\s,]+$`; URL gốc của GitHub REST API. | 

### 3.2. Nhóm `actions-webhooks` – GitHub Actions & Webhooks

| Key | Kiểu | Mặc định | Ràng buộc / Ý nghĩa | 
| ----- | ----- | ----- | ----- | 
| `actions.workflowFile` | `STRING` | `.github/workflows/ci.yml` | Regex `^\.github/workflows/[A-Za-z0-9._-]+\.ya?ml$`; đường dẫn file workflow CI. | 
| `actions.requiredChecks` | `LIST` | `Backend Build and Test,Frontend Build and Test,GitHub Integration Service Test,AI Service Build and Test` | Cho phép rỗng (`minItems = 0`), tối đa 20 phần tử; mỗi item khớp `^[A-Za-z0-9][A-Za-z0-9 ._()/-]{0,99}$`. | 
| `webhooks.enabled` | `BOOLEAN` | `true` | Bật/tắt tiếp nhận GitHub webhook deliveries. | 
| `webhooks.events` | `LIST` | `push,pull_request` | Giá trị hợp lệ: `push`, `pull_request`; tối thiểu 1 phần tử. | 
| `webhooks.payloadUrl` | `STRING` | `""` | Regex `^(https?://[^\s,]+)?$`; URL công khai của `POST /api/github/webhook`. | 

### 3.3. Nhóm `languages` – Supported Source-Code Languages

| Key | Kiểu | Mặc định | Ràng buộc / Ý nghĩa | 
| ----- | ----- | ----- | ----- | 
| `languages.enabled` | `LIST` | `java,python` | Tối thiểu 1 phần tử, tối đa 20 phần tử; chỉ chấp nhận các giá trị trong danh sách: `java`, `python`, `javascript`, `typescript`, `kotlin`, `go`, `ruby`, `php`, `csharp`, `c`, `cpp`, `rust`, `swift`, `scala`, `sql`. | 

### 3.4. Nhóm `generation` – Documentation Generation

| Key | Kiểu | Mặc định | Ràng buộc / Ý nghĩa | 
| ----- | ----- | ----- | ----- | 
| `generation.outputLanguage` | `CHOICE` | `vi` | Giá trị hợp lệ: `vi`, `en` (chuẩn hóa chữ thường). | 
| `generation.templateId` | `STRING` | `default` | Regex `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`; mã template mặc định khi sinh tài liệu. | 
| `generation.sections` | `LIST` | `Overview,Classes,Functions,API Endpoints` | Giá trị hợp lệ: `Overview`, `Classes`, `Functions`, `API Endpoints`; tối thiểu 1 phần tử. | 
| `generation.maxAttempts` | `INT` | `GENERATION_MAX_ATTEMPTS` hoặc `3` | Khoảng giá trị `1..10`; số lần gọi AI tối đa cho mỗi file trước khi fallback sang dữ liệu phân tích. | 

### 3.5. Nhóm `auto-update` – Automatic Update Policies

| Key | Kiểu | Mặc định | Ràng buộc / Ý nghĩa | 
| ----- | ----- | ----- | ----- | 
| `autoUpdate.enabled` | `BOOLEAN` | `false` | Bật/tắt tự động cập nhật tài liệu khi mã nguồn thay đổi. | 
| `autoUpdate.triggers` | `LIST` | `push,pull_request` | Giá trị hợp lệ: `push`, `pull_request`; tối thiểu 1 phần tử. | 
| `autoUpdate.branches` | `LIST` | `main` | Tối thiểu 1 phần tử; mỗi item khớp `^[A-Za-z0-9._/*-]{1,100}$` (hỗ trợ wildcard `*`). | 
| `autoUpdate.minDriftSeverity` | `CHOICE` | `medium` | Giá trị hợp lệ: `low`, `medium`, `high`, `critical`. | 
| `autoUpdate.requireReview` | `BOOLEAN` | `true` | Tài liệu cập nhật tự động vẫn phải đi qua quy trình Staff review và Manager approval. | 

### 3.6. Nhóm `retention` – Change-Log & Audit-Log Retention

| Key | Kiểu | Mặc định | Ràng buộc / Ý nghĩa | 
| ----- | ----- | ----- | ----- | 
| `retention.changeLogDays` | `INT` | `RETENTION_CHANGE_LOG_DAYS` hoặc `365` | Khoảng giá trị `30..3650` ngày; thời gian lưu trữ bản ghi change log. | 
| `retention.auditLogDays` | `INT` | `ADMIN_USER_AUDIT_RETENTION_DAYS` hoặc `730` | Khoảng giá trị `30..3650` ngày; thời gian lưu trữ bản ghi `admin_user_audit`. | 

### 3.7. Nhóm `ai` – AI Model & Confidence

| Key | Kiểu | Mặc định | Ràng buộc / Ý nghĩa | 
| ----- | ----- | ----- | ----- | 
| `ai.model` | `STRING` | `claude-sonnet-5-5` | Regex `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$`; tên model LLM sinh tài liệu. | 
| `ai.embeddingModel` | `STRING` | `tfidf` | Regex `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$`; mô hình embedding cho retrieval. | 
| `ai.confidenceThreshold` | `DECIMAL` | `0.5` | Khoảng giá trị `0..1`; các entity có confidence dưới ngưỡng này bị gắn cờ cần rà soát. | 
| `ai.tokenBudget` | `INT` | `4096` | Khoảng giá trị `256..64000`; số token tối đa cho một phản hồi AI. | 

### 3.8. Nhóm `retrieval` – Indexing & Retrieval

| Key | Kiểu | Mặc định | Ràng buộc / Ý nghĩa | 
| ----- | ----- | ----- | ----- | 
| `indexing.reindexOnChange` | `BOOLEAN` | `true` | Tự động dựng lại chỉ mục tài liệu khi mã nguồn hoặc tài liệu thay đổi. | 
| `retrieval.codeResults` | `INT` | `4` | Khoảng giá trị `0..20`; số đoạn code liên quan tối đa gửi kèm prompt cho mỗi file. | 
| `retrieval.docResults` | `INT` | `3` | Khoảng giá trị `0..20`; số đoạn tài liệu context tối đa gửi kèm prompt cho mỗi file. | 
| `retrieval.minScore` | `DECIMAL` | `0.05` | Khoảng giá trị `0..1`; điểm tương đồng tối thiểu để giữ kết quả truy xuất. | 
| `retrieval.chunkChars` | `INT` | `1200` | Khoảng giá trị `200..10000`; số ký tự tối đa của một đoạn tài liệu được lập chỉ mục. | 
| `retrieval.excerptChars` | `INT` | `600` | Khoảng giá trị `100..5000`; số ký tự tối đa của đoạn trích dẫn làm bằng chứng (evidence). | 

## 4. API và điểm cấu hình

### 4.1. System Configuration REST API (`/api/admin/system-configuration`)

| Method | Endpoint | Authority yêu cầu | Kết quả | Mục đích | 
| ----- | ----- | ----- | ----- | ----- | 
| **GET** | `/api/admin/system-configuration` | `SYSTEM_CONFIG_VIEW` | `200 OK` (`List<GroupView>`) | Lấy toàn bộ 8 nhóm cấu hình kèm giá trị hiện tại, mặc định và trạng thái `overridden`. | 
| **GET** | `/api/admin/system-configuration/{group}` | `SYSTEM_CONFIG_VIEW` | `200 OK` (`GroupView`) hoặc `404` | Lấy chi tiết cấu hình của một nhóm (`github`, `actions-webhooks`, `languages`, `generation`, `auto-update`, `retention`, `ai`, `retrieval`). | 
| **PATCH** | `/api/admin/system-configuration/{group}` | `SYSTEM_CONFIG_UPDATE` | `200 OK` (`GroupView`) hoặc `400` / `404` | Cập nhật một hoặc nhiều setting trong nhóm `{group}`; body dạng `{"settings": {"key": value}}`. | 
| **DELETE** | `/api/admin/system-configuration/{group}` | `SYSTEM_CONFIG_UPDATE` | `200 OK` (`GroupView`) hoặc `404` | Xóa các override của nhóm `{group}` trong bảng `system_settings`, khôi phục toàn bộ về giá trị mặc định. | 

### 4.2. Schema Bảng `system_settings` (`V9__create_system_settings.sql`)

```
CREATE TABLE IF NOT EXISTS system_settings (
    setting_key VARCHAR(128) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(128) NOT NULL
);

```

## 5. Luồng chính

1. **Xem cấu hình:** Quản trị viên truy cập màn hình System Configuration (quyền `SYSTEM_CONFIG_VIEW`). Client gửi `GET /api/admin/system-configuration`. `SystemConfigurationService` nạp các bản ghi override từ bảng `system_settings`, kết hợp với `CATALOG` và trả về danh sách 8 nhóm kèm cờ `overridden`.

2. **Cập nhật cấu hình:** Quản trị viên chỉnh sửa tham số và gửi `PATCH /api/admin/system-configuration/{group}` kèm CSRF token. Service xác thực tên nhóm, kiểm tra từng key trong payload (phải thuộc nhóm, đúng kiểu, nằm trong khoảng `min..max` hoặc danh sách `allowed`). Nếu hợp lệ, hệ thống mã hóa và lưu vào DB với `updated_by = authentication.getName()` và `updated_at = Instant.now()`.

3. **Khôi phục mặc định (Reset):** Quản trị viên bấm reset nhóm. Client gửi `DELETE /api/admin/system-configuration/{group}`. Service gọi `repository.deleteAllById(...)` xóa các bản ghi của nhóm trong DB. Nhóm đó trở về trạng thái `overridden = false`.

4. **Dọn dẹp nhật ký quản trị tự động:** Định kỳ `00:00 UTC`, scheduler `AdminUserAuditRetention` đọc `retention.auditLogDays` từ `SystemConfigurationService` (tự động lấy giá trị ghi đè mới nhất nếu có) và xóa các bản ghi `admin_user_audit` có thời điểm tạo vượt quá số ngày quy định.

## 6. Luồng lỗi

| Trường hợp | HTTP / Kết quả | Cơ chế xử lý | 
| ----- | ----- | ----- | 
| Người dùng chưa đăng nhập | 401 Unauthorized | Spring Security chặn tại filter chain. | 
| Thiếu vai trò `ADMIN`/`ADMINISTRATOR` hoặc thiếu quyền `SYSTEM_CONFIG_VIEW`/`SYSTEM_CONFIG_UPDATE` | 403 Forbidden | Chặn bởi `@PreAuthorize` hoặc `SecurityFilterChain`. | 
| Thiếu hoặc sai CSRF token khi gọi `PATCH`/`DELETE` | 403 Forbidden | Spring Security từ chối yêu cầu thay đổi trạng thái. | 
| Tên nhóm trong path không thuộc 8 nhóm hợp lệ | 404 Not Found | Ném `ResponseStatusException(404, "Configuration group not found")`. | 
| Payload `PATCH` rỗng hoặc thiếu `settings` | 400 Bad Request | Từ chối với thông báo `"settings is required"` hoặc `"settings must contain at least one value"`. | 
| Key không nằm trong catalog, thuộc nhóm khác, hoặc giá trị không hợp lệ (sai kiểu/vượt ngưỡng) | 400 Bad Request | Thu thập toàn bộ lỗi validation và từ chối toàn bộ giao dịch (all-or-nothing). | 
| Dữ liệu `setting_value` trong DB bị hỏng/không đúng định dạng | 200 OK (Fallback) | `decodeOrDefault` tự động trả về giá trị mặc định của catalog và ghi log cảnh báo. | 

## 7. Quy tắc nghiệp vụ

* **Nguyên tắc Override-only:** Bảng `system_settings` chỉ lưu trữ các cấu hình đã bị thay đổi bởi quản trị viên; giá trị mặc định được quản lý tập trung trong `SystemConfigurationService.CATALOG`.

* **Thứ tự ưu tiên cấu hình:** Giá trị override trong DB (1) $\rightarrow$ Biến môi trường fallback (2) $\rightarrow$ Giá trị mặc định trong `CATALOG` (3).

* **Không lưu thông tin bí mật trong cấu hình động:** Mọi secret (`API key`, `client secret`, `webhook secret`, `token encryption key`) chỉ được nạp từ biến môi trường; API từ chối bất kỳ key nào không có trong catalog.

* **Tính nguyên tử khi cập nhật (All-or-Nothing):** Một lệnh `PATCH` chỉ ghi xuống cơ sở dữ liệu khi tất cả tham số trong payload đều vượt qua bước kiểm tra hợp lệ.

* **Chuẩn hóa dữ liệu đầu vào:** Giá trị `LIST` được cắt khoảng trắng thừa, loại bỏ chuỗi rỗng và loại bỏ phần tử trùng lặp; các tham số `CHOICE`/`LIST` được kiểm tra khớp danh sách cho phép.

* **Ghi nhận vết người chỉnh sửa:** Mỗi bản ghi trong `system_settings` lưu `updated_by` (username của quản trị viên) và `updated_at` (thời điểm UTC).

## 8. Tiêu chí chấp nhận

* **AC-BE-06.1:** `GET /api/admin/system-configuration` trả về đầy đủ 8 nhóm cấu hình (`github`, `actions-webhooks`, `languages`, `generation`, `auto-update`, `retention`, `ai`, `retrieval`) với giá trị mặc định khớp với hành vi hệ thống và `overridden = false` khi chưa có chỉnh sửa.

* **AC-BE-06.2:** `PATCH /api/admin/system-configuration/{group}` kiểm tra kiểu dữ liệu, regex, danh sách `allowed` và khoảng `min..max`; khi hợp lệ thì lưu vào `system_settings`, đánh dấu `overridden = true` và ghi nhận `updatedBy`.

* **AC-BE-06.3:** Khi payload `PATCH` có ít nhất một giá trị không hợp lệ, thuộc nhóm khác hoặc là key bí mật không nằm trong catalog, API trả về `400 Bad Request` và không lưu thay đổi nào.

* **AC-BE-06.4:** `DELETE /api/admin/system-configuration/{group}` xóa toàn bộ override của nhóm được chỉ định và đưa các setting của nhóm đó về giá trị mặc định mà không làm thay đổi nhóm khác.

* **AC-BE-06.5:** Chỉ tài khoản có vai trò `ADMINISTRATOR` (hoặc `ADMIN`) với quyền `SYSTEM_CONFIG_VIEW` mới đọc được cấu hình và chỉ tài khoản có quyền `SYSTEM_CONFIG_UPDATE` mới cập nhật hoặc reset được cấu hình.

* **AC-BE-06.6:** Các tham số `retention.auditLogDays`, `retention.changeLogDays` và `generation.maxAttempts` hỗ trợ đọc giá trị mặc định từ biến môi trường khi chưa bị override trong database.

* **AC-BE-06.7:** Tác vụ `AdminUserAuditRetention` sử dụng giá trị `retention.auditLogDays` hiện hành ở mỗi lần chạy để xóa các bản ghi `admin_user_audit` quá hạn.

* **AC-BE-06.8:** Nếu giá trị lưu trong `system_settings` bị sai định dạng, hệ thống tự động fallback về giá trị mặc định của catalog thay vì gây lỗi runtime.

## 9. Kiểm thử

* **Unit & Integration Test Backend (`SystemConfigurationServiceTest.java`):** Kiểm tra 8 nhóm mặc định, cập nhật hợp lệ, tính chất all-or-nothing, từ chối key lạ/secret/sai kiểu/vượt ngưỡng, chuẩn hóa `LIST`/`CHOICE`, `reset` theo nhóm, `404` khi sai tên nhóm, fallback khi dữ liệu DB hỏng và các typed accessors.

* **Controller & Security Test (`AdminSystemConfigurationControllerTest.java`):** Kiểm tra ghi nhận `authentication.getName()` khi `PATCH`, bắt buộc body `settings`, kiểm tra phân quyền `@PreAuthorize` (`SYSTEM_CONFIG_VIEW` / `SYSTEM_CONFIG_UPDATE`) và xác thực CSRF.

* **Audit Retention Scheduler Test (`AdminUserAuditRetentionTest.java`):** Kiểm tra `AdminUserAuditRetention` đọc động `retention.auditLogDays` ở mỗi lần chạy và bỏ qua khi giá trị `<= 0`.

* **RBAC Parity Test (`ScreenPermissionsParityTest.java` & `frontend/src/rbac/__tests__/permissions.test.js`):** Kiểm tra tính nhất quán ma trận phân quyền cho màn hình #26 `systemConfiguration` (`CRU` cho `ADMINISTRATOR`).