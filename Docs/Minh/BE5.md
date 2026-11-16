# LivingDocs — Đặc tả tái tạo chức năng LD-273: System Configuration

## 1. Mục tiêu

Triển khai chức năng cấu hình hệ thống LivingDocs để quản trị viên có thể xem, cập nhật và khôi phục các nhóm thiết lập liên quan đến GitHub, GitHub Actions/Webhooks, ngôn ngữ mã nguồn, sinh tài liệu, cập nhật tài liệu tự động, thời hạn lưu log, AI và truy xuất tài liệu.

Các nhóm chức năng theo yêu cầu:
1. Cấu hình GitHub App và OAuth.
2. Cấu hình GitHub Actions và Webhooks.
3. Chọn các ngôn ngữ source code được hỗ trợ.
4. Cấu hình sinh tài liệu.
5. Cấu hình trigger và chính sách cập nhật tài liệu tự động.
6. Cấu hình thời hạn lưu Change Log và Audit Log.
7. Cấu hình AI model, embedding model, confidence threshold và token budget.
8. Cấu hình indexing và retrieval.

## 2. Thành phần và vị trí mã nguồn

### Backend

- `backend/src/main/java/com/cnpm/backend/controller/AdminSystemConfigurationController.java`: REST API xem danh sách nhóm cấu hình, xem một nhóm, cập nhật và reset nhóm.
- `backend/src/main/java/com/cnpm/backend/service/SystemConfigurationService.java`: catalog cấu hình, giá trị mặc định, kiểu dữ liệu, validation, chuyển đổi giá trị và lưu override.
- `backend/src/main/java/com/cnpm/backend/entity/SystemSetting.java`: entity lưu override của từng setting.
- `backend/src/main/java/com/cnpm/backend/repository/SystemSettingRepository.java`: truy vấn dữ liệu cấu hình.
- `backend/src/main/java/com/cnpm/backend/security/SystemAdminAccess.java`: kiểm tra quyền quản trị hệ thống.
- `backend/src/main/java/com/cnpm/backend/security/SecurityConfig.java`: cấu hình bảo vệ endpoint và authority.
- `backend/src/main/resources/application.properties`: cấu hình runtime, database và thời hạn lưu admin-user audit.
- `backend/src/main/tests/java/com/cnpm/backend/AdminSystemConfigurationControllerTest.java`: kiểm thử controller.
- `backend/src/main/tests/java/com/cnpm/backend/SystemConfigurationServiceTest.java`: kiểm thử service và validation.

### Các service liên quan

- `services/github-integration-service/src/main/resources/application.yml`: cấu hình GitHub App/OAuth, webhook secret, token encryption, URL dịch vụ.
- `ai-service/`: AI generator, confidence và retrieval; catalog LD-273 mô tả các tham số cấu hình liên quan đến các thành phần này.

### Frontend

Snapshot có `frontend/src/App.jsx` và các màn hình chức năng hiện có, nhưng không có component quản trị cấu hình tương ứng với `/api/admin/system-configuration`. Vì vậy API quản trị được triển khai ở Backend; không mô tả một giao diện chỉnh sửa cấu hình như thể nó đã tồn tại.

## 3. Kiến trúc và nguyên tắc lưu cấu hình

`SystemConfigurationService` khai báo catalog tập trung. Mỗi định nghĩa setting chứa:
- Nhóm cấu hình và key.
- Kiểu dữ liệu: `STRING`, `INT`, `DECIMAL`, `BOOLEAN`, `CHOICE`, `LIST`.
- Giá trị mặc định.
- Mô tả.
- Giới hạn min/max, danh sách giá trị được phép, regex hoặc số lượng item tối thiểu khi áp dụng.

Giá trị mặc định được thiết kế để phản ánh các giá trị mà service đang sử dụng. Database chỉ lưu các giá trị administrator override; khi không có override, hệ thống trả về default. Catalog được kiểm tra ngay khi khởi tạo để bảo đảm default tự thỏa validation.

Các secret như GitHub client secret, webhook secret, token-encryption key và API keys không nằm trong catalog. Chúng tiếp tục được lấy từ environment variables. API từ chối key không được khai báo trong catalog.

## 4. Nhóm cấu hình và giá trị mặc định

### 4.1 GitHub App & OAuth (`github`)

| Key | Default | Ý nghĩa |
|---|---|---|
| `github.appSlug` | `livingdocs-dev-hai` | GitHub App slug dùng trong installation URL |
| `github.clientId` | rỗng | OAuth client ID công khai |
| `github.redirectUri` | `http://localhost:8082/api/github/callback` | OAuth redirect URI |
| `github.oauthScopes` | `read:user,user:email` | OAuth scopes |
| `github.oauthBaseUrl` | `https://github.com` | GitHub OAuth base URL |
| `github.apiBaseUrl` | `https://api.github.com` | GitHub REST API base URL |

Client secret không được lưu trong bảng system settings; phải cấu hình bằng environment.

### 4.2 GitHub Actions & Webhooks (`actions-webhooks`)

| Key | Default | Ý nghĩa |
|---|---|---|
| `actions.workflowFile` | `.github/workflows/ci.yml` | Đường dẫn workflow CI |
| `actions.requiredChecks` | Backend, Frontend, GitHub Integration, AI Service checks | Các CI jobs bắt buộc phải pass |
| `webhooks.enabled` | `true` | Cho phép nhận webhook deliveries |
| `webhooks.events` | `push,pull_request` | Các event được xử lý |
| `webhooks.payloadUrl` | rỗng | Public URL của `POST /api/github/webhook` |

Các event ngoài danh sách được cấu hình không nằm trong phạm vi xử lý theo catalog. Webhook secret không phải system setting.

### 4.3 Supported Source-Code Languages (`languages`)

- Key: `languages.enabled`
- Default: `java,python`
- Danh sách cho phép: `java`, `python`, `javascript`, `typescript`, `kotlin`, `go`, `ruby`, `php`, `csharp`, `c`, `cpp`, `rust`, `swift`, `scala`, `sql`.
- Mô tả trong code lưu ý Code Analyzer hiện parse Java và Python; bật ngôn ngữ khác không đồng nghĩa analyzer đã hỗ trợ parse ngôn ngữ đó.

### 4.4 Documentation Generation (`generation`)

| Key | Default | Validation / ý nghĩa |
|---|---|---|
| `generation.outputLanguage` | `vi` | Choice `vi` hoặc `en` |
| `generation.templateId` | `default` | Template mặc định |
| `generation.sections` | `Overview,Classes,Functions,API Endpoints` | Các section trong tài liệu |
| `generation.maxAttempts` | `3` | Số lần AI thử cho mỗi file; từ 1 đến 10 |

### 4.5 Automatic Update Policies (`auto-update`)

| Key | Default | Ý nghĩa |
|---|---|---|
| `autoUpdate.enabled` | `false` | Bật/tắt tự động cập nhật tài liệu khi code thay đổi |
| `autoUpdate.triggers` | `push,pull_request` | GitHub events kích hoạt update |
| `autoUpdate.branches` | `main` | Branch được áp dụng; hỗ trợ wildcard `*` ở cuối |
| `autoUpdate.minDriftSeverity` | `medium` | Severity thấp nhất kích hoạt update: `low`, `medium`, `high`, `critical` |
| `autoUpdate.requireReview` | `true` | Tài liệu cập nhật vẫn phải qua staff review và manager approval |

### 4.6 Change-Log & Audit-Log Retention (`retention`)

| Key | Default | Giới hạn |
|---|---:|---:|
| `retention.changeLogDays` | 365 ngày | 30–3650 |
| `retention.auditLogDays` | 730 ngày | 30–3650 |

Ngoài catalog này, `application.properties` có `app.admin-user-audit.retention-days`, mặc định `0`; comment trong file nêu giá trị dương mới bật expiry cho admin user audit records. Không đồng nhất setting runtime này với hai key retention trong catalog.

### 4.7 AI Model & Confidence (`ai`)

| Key | Default | Validation / ý nghĩa |
|---|---|---|
| `ai.model` | `claude-sonnet-5-5` | Model sinh tài liệu |
| `ai.embeddingModel` | `tfidf` | Embedding/retrieval model; `tfidf` là built-in TF-IDF ranking |
| `ai.confidenceThreshold` | `0.5` | Confidence thấp hơn ngưỡng sẽ được đánh dấu review; 0–1 |
| `ai.tokenBudget` | `4096` | Token tối đa cho một AI response; 256–64000 |

### 4.8 Indexing & Retrieval (`retrieval`)

| Key | Default | Giới hạn / ý nghĩa |
|---|---:|---|
| `indexing.reindexOnChange` | `true` | Rebuild index khi code hoặc tài liệu thay đổi |
| `retrieval.codeResults` | 4 | Số code items liên quan đưa cho AI; 0–20 |
| `retrieval.docResults` | 3 | Số đoạn tài liệu đưa cho AI; 0–20 |
| `retrieval.minScore` | 0.05 | Similarity tối thiểu; 0–1 |
| `retrieval.chunkChars` | 1200 | Số ký tự tối đa của một documentation chunk; 200–10000 |
| `retrieval.excerptChars` | 600 | Số ký tự tối đa của evidence excerpt; 100–5000 |

## 5. API contract

Base path: `/api/admin/system-configuration`.

### 5.1 Lấy tất cả nhóm cấu hình

`GET /api/admin/system-configuration`

- Yêu cầu authority `SYSTEM_CONFIG_VIEW`.
- Trả về danh sách `GroupView`.
- Mỗi group có `id`, `title`, `settings`.
- Mỗi setting trả `key`, `type`, `value`, `defaultValue`, `description`, giới hạn/allowed values, `overridden`, `updatedAt`, `updatedBy`.

### 5.2 Lấy một nhóm

`GET /api/admin/system-configuration/{group}`

- Yêu cầu `SYSTEM_CONFIG_VIEW`.
- Trả về một `GroupView` của group được yêu cầu.

### 5.3 Cập nhật nhóm

`PATCH /api/admin/system-configuration/{group}`

- Yêu cầu `SYSTEM_CONFIG_UPDATE`.
- Request body có field `settings`, là map key/value.
- Nếu body hoặc `settings` null, trả HTTP 400 với thông báo `settings is required`.
- Service kiểm tra key có thuộc catalog và ép kiểu/validate theo định nghĩa trước khi lưu.
- Giá trị override được gắn với người thực hiện cập nhật (`authentication.getName()`).
- Response trả về group sau cập nhật.

Ví dụ cấu trúc request:

```json
{
  "settings": {
    "ai.confidenceThreshold": 0.7,
    "ai.tokenBudget": 8192
  }
}
```

### 5.4 Reset nhóm

`DELETE /api/admin/system-configuration/{group}`

- Yêu cầu `SYSTEM_CONFIG_UPDATE`.
- Xóa override của group để các setting quay về default.
- Response trả về `GroupView` sau reset.

## 6. Quy tắc bảo mật và validation

- Chỉ principal có authority tương ứng mới được đọc hoặc thay đổi cấu hình.
- Chỉ các key đã đăng ký trong catalog được chấp nhận.
- Kiểu dữ liệu và giới hạn được xác định theo từng Definition.
- `STRING` có giới hạn độ dài và regex theo setting; `CHOICE` chỉ nhận lựa chọn được khai báo; `LIST` kiểm tra item hợp lệ và số lượng; số nguyên/số thập phân được kiểm tra min/max.
- Secret không được expose như setting có thể đọc/ghi qua API.
- Không đưa credential thật vào Markdown, source control hoặc request mẫu.

## 7. Luồng xử lý

### Đọc cấu hình

1. Administrator gọi GET endpoint.
2. Controller kiểm tra authority `SYSTEM_CONFIG_VIEW`.
3. Service duyệt catalog theo group.
4. Với mỗi key, service lấy override trong `system_settings` nếu có; nếu không dùng default.
5. API trả group và metadata của từng setting, gồm trạng thái overridden và thông tin cập nhật.

### Cập nhật cấu hình

1. Administrator gửi PATCH với group và map settings.
2. Controller kiểm tra request body.
3. Service xác định group/key trong catalog.
4. Service chuyển đổi kiểu và validate từng giá trị.
5. Giá trị hợp lệ được lưu thành override, kèm người cập nhật/thời điểm cập nhật.
6. API trả về cấu hình nhóm mới.

### Reset cấu hình

1. Administrator gọi DELETE theo group.
2. Controller yêu cầu `SYSTEM_CONFIG_UPDATE`.
3. Service xóa các override thuộc group.
4. Giá trị hiệu lực trở về default của catalog.

## 8. Kiểm thử và tiêu chí chấp nhận

Các test source có sẵn:
- `AdminSystemConfigurationControllerTest.java`
- `SystemConfigurationServiceTest.java`

Tiêu chí chức năng cần xác minh:
1. GET tất cả groups trả các nhóm catalog.
2. GET một group trả đúng group và metadata.
3. PATCH cập nhật các key hợp lệ và trả giá trị mới.
4. Thiếu `settings` trả HTTP 400.
5. Key không nằm trong catalog bị từ chối.
6. Giá trị sai kiểu, ngoài min/max, không đúng regex hoặc không thuộc choices bị từ chối.
7. DELETE group xóa override và trả default.
8. Người không có `SYSTEM_CONFIG_VIEW` không đọc được cấu hình.
9. Người không có `SYSTEM_CONFIG_UPDATE` không thể PATCH/DELETE.
10. Secret không xuất hiện trong catalog/API.
11. Giá trị mặc định luôn tự thỏa validation khi service khởi tạo.

## 9. Phạm vi và giới hạn của snapshot

- Backend có REST API và catalog cho các nhóm cấu hình nêu trên.
- Không thấy màn hình quản trị cấu hình tương ứng trong frontend snapshot LD-273; tài liệu này không khẳng định có UI để administrator thao tác trực tiếp trên trình duyệt.
- Catalog cho phép cấu hình danh sách ngôn ngữ rộng hơn khả năng parse hiện được ghi chú của Code Analyzer (Java/Python).
- Các secret và API keys tiếp tục được quản lý qua environment variables, không phải qua system settings.
- Các yêu cầu trong LD-273 được mô tả theo catalog và API hiện diện; không suy diễn rằng thay đổi mọi setting tự động cập nhật runtime của mọi service nếu source không thể hiện cơ chế áp dụng tương ứng.

## 10. Hướng dẫn cho AI tái tạo code

- Giữ catalog cấu hình tập trung trong `SystemConfigurationService`; không phân tán default/validation ở controller.
- Giữ phân biệt default và administrator override trong `system_settings`.
- Bảo đảm GET trả cả metadata phục vụ giao diện cấu hình: type, default, description, constraints, overridden, updatedAt, updatedBy.
- PATCH chỉ nhận các key được catalog khai báo và validate trước khi lưu.
- DELETE group phải xóa override để quay về default, không hard-code lại từng giá trị.
- Giữ authority `SYSTEM_CONFIG_VIEW` và `SYSTEM_CONFIG_UPDATE`.
- Không lưu GitHub secret, webhook secret, token encryption key hoặc API key trong bảng system settings.
- Không tự tuyên bố frontend configuration UI đã tồn tại trong snapshot LD-273.
