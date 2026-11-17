# LivingDocs — Đặc tả tái tạo chức năng LD-177: Documentation Change Log

## 1. Mục tiêu

Triển khai **Documentation Change Log** cho LivingDocs nhằm lưu lại lịch sử thay đổi của từng tài liệu và cung cấp dữ liệu để hiển thị lịch sử theo dạng timeline.

Chức năng cần đáp ứng các yêu cầu trong đề bài LD-177:

1. Ghi nhận các thay đổi của tài liệu.
2. Hiển thị lịch sử thay đổi theo thứ tự thời gian.
3. Lưu người dùng và role thực hiện thay đổi.
4. Lưu thời điểm thay đổi.
5. Lưu nguồn kích hoạt thay đổi (trigger source).
6. Theo dõi trạng thái tài liệu tại thời điểm ghi nhận thay đổi.

Trong snapshot dự án, phần triển khai được xác định chủ yếu ở **GitHub Integration Service**: có entity, repository, service, controller, DTO và migration cho change log. API timeline đã có; không thấy một component frontend riêng hoặc lời gọi API `change-log` trong danh sách source frontend được cung cấp, vì vậy không mô tả giao diện timeline frontend như một phần đã hoàn thành.

## 2. Thành phần và vị trí mã nguồn

Các thành phần liên quan nằm trong `services/github-integration-service/`.

### Backend — GitHub Integration Service

- `src/main/java/com/livingdocs/github/entity/DocumentationChangeLog.java`: entity ánh xạ bảng `documentation_change_logs`.
- `src/main/java/com/livingdocs/github/entity/ChangeTriggerSource.java`: enum định nghĩa các nguồn kích hoạt thay đổi.
- `src/main/java/com/livingdocs/github/repository/DocumentationChangeLogRepository.java`: lớp truy vấn các bản ghi change log theo document, status và trigger source.
- `src/main/java/com/livingdocs/github/service/DocumentationChangeLogService.java`: ghi nhận change log, chuẩn hóa actor role/status và truy xuất timeline.
- `src/main/java/com/livingdocs/github/controller/DocumentationChangeLogController.java`: REST endpoint đọc lịch sử thay đổi.
- `src/main/java/com/livingdocs/github/dto/DocumentationChangeLogResponse.java`: DTO trả dữ liệu change log cho client.
- `src/main/resources/db/migration-common/V10__documentation_change_log.sql`: tạo bảng và index phục vụ truy vấn change log.

### Các luồng nghiệp vụ tích hợp

- `DocumentationGenerationService.java`: ghi nhận tài liệu được lưu sau khi AI generation hoàn tất; ghi nhận chỉnh sửa nội dung, quyết định review và rollback.
- `DocumentWorkflowService.java`: ghi nhận thay đổi timeline phát sinh từ các thao tác workflow và rollback.
- `GitHubWebhookController.java`: có phương thức ghi nhận tài liệu bị ảnh hưởng bởi sự kiện Push/Pull Request webhook.
- `DocumentationGenerationService.ChangeLogOverride`: hỗ trợ truyền authorities và điều khiển việc bỏ qua log khi một thao tác đã được ghi nhận ở lớp workflow, tránh tạo bản ghi trùng.

## 3. Kiến trúc xử lý tổng quan

Luồng dữ liệu change log:

1. Một thao tác làm thay đổi tài liệu xảy ra, ví dụ AI tạo tài liệu, người dùng sửa nội dung, reviewer đưa ra quyết định, rollback hoặc GitHub webhook ảnh hưởng đến tài liệu.
2. Lớp nghiệp vụ xác định document ID, action, summary, actor, authorities, trigger source, status và reference ID.
3. `DocumentationChangeLogService.recordChange(...)` tạo entity `DocumentationChangeLog`.
4. Service chuẩn hóa summary, actor name, actor role, trigger source và status.
5. Repository lưu entity vào bảng `documentation_change_logs`.
6. Khi client yêu cầu lịch sử, `DocumentationChangeLogController` gọi `getTimeline(...)`.
7. Service truy vấn theo document ID và các filter tùy chọn, sắp xếp `createdAt` giảm dần, rồi chuyển entity thành `DocumentationChangeLogResponse`.

Change log là dữ liệu lịch sử riêng; không phải nội dung tài liệu hoặc bảng version của AI Service. Bản ghi giữ thông tin tham chiếu đến version/job/workflow/webhook nếu luồng nghiệp vụ cung cấp `referenceId`.

## 4. Mô hình dữ liệu Documentation Change Log

Entity `DocumentationChangeLog` ánh xạ bảng `documentation_change_logs`.

| Trường | Kiểu / giới hạn | Ý nghĩa |
|---|---|---|
| `id` | String, tối đa 64 | ID bản ghi; nếu chưa có sẽ tự sinh UUID dạng String |
| `documentId` | String, tối đa 64, bắt buộc | ID tài liệu được thay đổi |
| `repositoryId` | UUID, nullable | Repository liên quan nếu luồng nghiệp vụ có cung cấp |
| `versionNumber` | Integer, nullable | Số version liên quan đến thay đổi |
| `action` | String, tối đa 64, bắt buộc | Loại hành động, ví dụ `CREATED`, `CONTENT_UPDATED`, `ROLLED_BACK` |
| `summary` | String, tối đa 500, bắt buộc | Nội dung mô tả thay đổi |
| `actorId` | String, tối đa 128, nullable | ID người hoặc tác nhân tạo thay đổi |
| `actorName` | String, tối đa 255, nullable | Tên hiển thị của actor |
| `actorRole` | String, tối đa 64, bắt buộc | Role chính của actor hoặc `SYSTEM` |
| `triggerSource` | Enum String, tối đa 64, bắt buộc | Nguồn kích hoạt thay đổi |
| `status` | String, tối đa 64, bắt buộc | Trạng thái tài liệu tại thời điểm ghi nhận |
| `referenceId` | String, tối đa 128, nullable | ID tham chiếu như job ID hoặc version |
| `createdAt` | Instant, bắt buộc | Thời điểm tạo bản ghi, không cập nhật lại |

### Tự động khởi tạo

Trong `@PrePersist`:

- Nếu `id` chưa có, entity tạo UUID dạng String.
- Nếu `createdAt` chưa có, entity gán `Instant.now()`.
- Nếu `actorRole` chưa có hoặc rỗng, entity dùng `SYSTEM`.

`createdAt` được đánh dấu `updatable = false`, do đó thời điểm của một event lịch sử không bị cập nhật lại khi entity được lưu sau đó.

## 5. Trigger Source và Action

### 5.1 Các nguồn kích hoạt

Enum `ChangeTriggerSource` định nghĩa:

| Giá trị | Ý nghĩa |
|---|---|
| `AI_GENERATION` | Sinh tài liệu tự động từ kết quả phân tích code |
| `MANUAL_EDIT` | Người dùng tạo hoặc chỉnh sửa trực tiếp trong editor |
| `DRIFT_SUGGESTION` | Áp dụng gợi ý cập nhật từ phát hiện Documentation Drift |
| `PR_WEBHOOK` | Kích hoạt từ sự kiện Push / Pull Request trên GitHub |
| `REVIEW_WORKFLOW` | Thao tác tạo workflow, gửi duyệt, nhận duyệt, phê duyệt hoặc từ chối |
| `ROLLBACK` | Khôi phục về phiên bản tài liệu trước đó |

Nếu `recordChange(...)` nhận `triggerSource == null`, service mặc định dùng `MANUAL_EDIT`.

### 5.2 Action được ghi nhận trong các luồng hiện có

Các action xuất hiện trong code:

- `CREATED`: tài liệu được lưu từ kết quả AI generation.
- `CONTENT_UPDATED`: nội dung tài liệu được chỉnh sửa.
- `WORKFLOW_{DECISION}`: quyết định workflow, ví dụ `WORKFLOW_APPROVED` hoặc action tương ứng với decision thực tế.
- `ROLLED_BACK`: tài liệu được rollback về version trước.
- `PR_WEBHOOK_IMPACT`: tài liệu bị ảnh hưởng bởi sự kiện GitHub webhook.

Action là chuỗi mô tả nghiệp vụ, không phải enum cố định trong entity. Vì vậy khi bổ sung action mới cần giữ quy ước tên nhất quán với các luồng đang có.

## 6. Ghi nhận người dùng, role và timestamp

### 6.1 Actor

`recordChange(...)` nhận các thông tin:

- `actorId`: user ID hoặc định danh tác nhân.
- `actorName`: tên hiển thị.
- `authorities`: tập quyền/role của actor.

Nếu `actorName` null hoặc rỗng, service dùng `actorId` làm tên hiển thị dự phòng.

Với sự kiện webhook, code dùng actor cố định:
- `actorId = "github-webhook"`
- `actorName = "GitHub Webhook"`
- authorities rỗng, do đó role được xác định là `SYSTEM`.

### 6.2 Quy tắc xác định primary role

`resolvePrimaryRole(...)` chuẩn hóa authorities:

1. Loại bỏ giá trị null/rỗng.
2. Xóa prefix `ROLE_` nếu có.
3. Chuyển về chữ hoa.
4. Chọn role theo thứ tự ưu tiên:

`ADMINISTRATOR` → `ADMIN` → `MANAGER` → `TECHNICAL_LEAD` → `STAFF` → `DEVELOPER`.

Quy tắc đặc biệt:
- `ADMIN` được chuẩn hóa thành `ADMINISTRATOR`.
- Authorities null/rỗng trả về `SYSTEM`.
- Nếu có authorities nhưng không khớp danh sách ưu tiên, lấy authority đầu tiên sau chuẩn hóa.
- Nếu sau lọc không còn authority hợp lệ, trả về `USER`.

### 6.3 Timestamp

Timestamp được ghi tự động tại thời điểm persist bằng `Instant.now()` trong entity `DocumentationChangeLog`. API trả thời gian này dưới dạng `Instant`.

## 7. Ghi nhận thay đổi theo từng luồng nghiệp vụ

### 7.1 Lưu tài liệu được sinh bởi AI

Trong `DocumentationGenerationService.saveOwnedDocument(...)`:

- Yêu cầu quyền `DOCUMENT_CREATE`.
- Kiểm tra job thuộc user hiện tại.
- Gọi AI Service để lưu tài liệu từ job.
- Khi nhận được document hợp lệ và `changeLogService` khả dụng, ghi bản ghi:
  - action: `CREATED`
  - trigger: `AI_GENERATION`
  - version: `1`
  - status: `DRAFT`
  - reference: job ID
  - actor: user hiện tại và authorities tương ứng.

### 7.2 Chỉnh sửa nội dung tài liệu

Trong `editOwnedDocument(...)`:

- Gửi nội dung mới và `expectedVersion` sang AI Service.
- Truyền `X-User-Id`, `X-User-Roles`, `X-Trigger-Source`.
- Trigger source là `MANUAL_EDIT`.
- Khi thao tác thành công và không bị yêu cầu suppress log, ghi:
  - action: `CONTENT_UPDATED`
  - version: version mới từ response
  - summary: note của người dùng; nếu không có note thì dùng mô tả cập nhật mặc định
  - status: `DRAFT`.

### 7.3 Review workflow

Trong `resolveDocumentVersion(...)`:

- Gửi actor, document owner, primary role và trigger `REVIEW_WORKFLOW` sang AI Service.
- Sau khi AI Service xử lý thành công, ghi action `WORKFLOW_` ghép với decision.
- Status trong change log là decision được truyền vào.
- Reference ID là `v{version}`.

### 7.4 Rollback

Trong `rollbackDocumentVersion(...)` và luồng rollback workflow:

- Gửi version nguồn và lý do rollback sang AI Service.
- Trigger source là `ROLLBACK`.
- Ghi action `ROLLED_BACK`.
- Reference ID tham chiếu version nguồn theo dạng `v{sourceVersion}`.
- Trong workflow rollback, `DocumentWorkflowService` ghi timeline sau khi rollback version hợp lệ và workflow được cập nhật.

### 7.5 GitHub webhook

`GitHubWebhookController.recordWebhookDocumentImpact(...)` ghi nhận ảnh hưởng của Push/Pull Request webhook đến tài liệu:

- action: `PR_WEBHOOK_IMPACT`
- trigger: `PR_WEBHOOK`
- actor: `GitHub Webhook`
- status: status hiện tại nếu có, nếu không dùng `DRAFT`
- reference: reference ID do caller cung cấp
- summary: nội dung caller cung cấp; nếu rỗng dùng thông báo mặc định.

Phương thức bỏ qua việc ghi log nếu `changeLogService` không khả dụng hoặc document ID null/rỗng.

### 7.6 Drift suggestion

Enum có `DRIFT_SUGGESTION` để biểu diễn việc áp dụng gợi ý từ Documentation Drift. Tuy nhiên, trong các vị trí gọi `recordChange(...)` được xác định rõ trong snapshot, chưa có bằng chứng đủ để mô tả một luồng gọi cụ thể cho trigger này. Không nên khẳng định mọi thao tác áp dụng drift suggestion đã được nối vào change log nếu chưa kiểm tra thêm caller thực tế.

## 8. API truy xuất Change Log Timeline

Controller:

`DocumentationChangeLogController`

Base path:

`/api/documentation`

### Endpoint

| Method | Endpoint | Mục đích |
|---|---|---|
| GET | `/api/documentation/{docId}/change-log` | Lấy lịch sử thay đổi của một tài liệu |

Query parameters:

| Parameter | Bắt buộc | Mô tả |
|---|---|---|
| `status` | Không | Lọc theo trạng thái; service trim và chuyển thành chữ hoa |
| `triggerSource` | Không | Lọc theo enum `ChangeTriggerSource`; controller trim và chuyển thành chữ hoa |

Ví dụ:

```http
GET /api/documentation/doc-123/change-log
GET /api/documentation/doc-123/change-log?status=DRAFT
GET /api/documentation/doc-123/change-log?triggerSource=AI_GENERATION
GET /api/documentation/doc-123/change-log?status=APPROVED&triggerSource=REVIEW_WORKFLOW
```

Nếu `triggerSource` không thuộc enum, controller trả HTTP `400 Bad Request` với thông báo `Unsupported triggerSource: ...`.

Endpoint trả danh sách `DocumentationChangeLogResponse`, được sắp xếp mới nhất trước. Snapshot hiện không thể hiện query parameter phân trang hoặc giới hạn số lượng bản ghi.

## 9. Response DTO và dữ liệu Timeline

`DocumentationChangeLogResponse` trả các trường:

| Trường | Nội dung |
|---|---|
| `id` | ID bản ghi change log |
| `documentId` | ID tài liệu |
| `repositoryId` | Repository liên quan |
| `versionNumber` | Version liên quan |
| `action` | Hành động đã xảy ra |
| `summary` | Mô tả thay đổi |
| `actorId` | ID người/tác nhân |
| `actorName` | Tên người/tác nhân |
| `actorRole` | Role chính |
| `triggerSource` | Nguồn kích hoạt |
| `status` | Trạng thái tài liệu |
| `referenceId` | ID tham chiếu |
| `createdAt` | Timestamp tạo event |

Dữ liệu có đủ các thuộc tính để client dựng timeline: mỗi phần tử là một event, có actor, hành động, mô tả, trạng thái, nguồn kích hoạt, version và thời điểm. Việc trình bày thành component timeline là trách nhiệm phía client; trong source frontend được cung cấp chưa xác định được component chuyên biệt gọi endpoint này.

## 10. Database Migration và Index

Migration:

`services/github-integration-service/src/main/resources/db/migration-common/V10__documentation_change_log.sql`

Migration tạo bảng `documentation_change_logs` với các cột tương ứng entity:

- `id VARCHAR(64)` primary key.
- `document_id VARCHAR(64)` not null.
- `repository_id UUID`.
- `version_number INTEGER`.
- `action VARCHAR(64)` not null.
- `summary VARCHAR(500)` not null.
- `actor_id VARCHAR(128)`.
- `actor_name VARCHAR(255)`.
- `actor_role VARCHAR(64)` not null.
- `trigger_source VARCHAR(64)` not null.
- `status VARCHAR(64)` not null.
- `reference_id VARCHAR(128)`.
- `created_at TIMESTAMP WITH TIME ZONE` not null, default `CURRENT_TIMESTAMP`.

Hai index được tạo:

- `idx_doc_changelog_doc_created` trên `(document_id, created_at DESC)` để truy vấn timeline của một tài liệu.
- `idx_doc_changelog_repo_created` trên `(repository_id, created_at DESC)` để hỗ trợ truy vấn theo repository.

Migration nằm trong `migration-common`, được dùng chung với các migration lineage của GitHub Integration Service. Khi thay đổi schema, cần kiểm tra cơ chế chọn lineage Flyway hiện có và không sửa tùy tiện migration đã được áp dụng trên database.

## 11. Kiểm thử và tiêu chí chấp nhận

Snapshot có test:

`services/github-integration-service/src/test/java/com/livingdocs/github/service/DocumentationChangeLogServiceTest.java`

Test sử dụng `@SpringBootTest`, profile `test` và `@Transactional`.

Test `shouldRecordFilterAndResolvePrimaryRole()` kiểm tra:

1. Ghi hai event cho cùng document với actor, role, trigger, status và reference khác nhau.
2. Truy vấn timeline không filter trả về đủ hai bản ghi.
3. Thứ tự timeline là mới nhất trước.
4. Authorities chứa `ROLE_ADMIN` được chuẩn hóa thành `ADMINISTRATOR`.
5. Authorities chứa cả `ROLE_DEVELOPER` và `ROLE_MANAGER` chọn `MANAGER` theo thứ tự ưu tiên.
6. Filter kết hợp `status=PENDING_STAFF_REVIEW` và `triggerSource=ROLLBACK` chỉ trả event phù hợp.

### Tiêu chí chấp nhận theo yêu cầu LD-177

1. Mỗi luồng thay đổi được tích hợp phải tạo bản ghi change log với document ID và action phù hợp.
2. Bản ghi lưu actor ID/name và primary role; sự kiện hệ thống/webhook được thể hiện là `SYSTEM` khi không có authorities.
3. Timestamp được tự động ghi và không bị cập nhật lại.
4. Trigger source được lưu đúng theo nguồn phát sinh.
5. Status tại thời điểm thay đổi được lưu trong bản ghi.
6. API lấy timeline theo document ID, sắp xếp giảm dần theo `createdAt`.
7. API hỗ trợ lọc theo status, trigger source hoặc đồng thời cả hai.
8. Trigger source không hợp lệ trả HTTP 400.
9. Summary rỗng có giá trị mặc định; summary dài hơn 500 ký tự được cắt còn 497 ký tự và thêm `...`.
10. Migration tạo bảng và index phù hợp với entity/repository.

Không kết luận test đã pass chỉ dựa trên việc có file test trong source snapshot; cần chạy Maven test/verify để xác nhận kết quả thực tế.

## 12. Các giới hạn cần giữ nguyên khi tái tạo

- Controller change log trong snapshot chỉ thể hiện endpoint GET timeline; không thấy API tạo/sửa/xóa change log công khai. Ghi log được thực hiện qua service nội bộ từ các luồng nghiệp vụ.
- Timeline query hiện không có pagination hoặc limit được thể hiện trong controller/service.
- `DRIFT_SUGGESTION` đã có trong enum nhưng chưa xác định được caller cụ thể trong các call site được rà soát; không khẳng định luồng này đã ghi log đầy đủ.
- Một số luồng gọi service chỉ ghi log khi `changeLogService` khác null; không mô tả change log là luôn hoạt động nếu dependency không được cấu hình.
- Summary được giới hạn tối đa 500 ký tự.
- `repositoryId`, `versionNumber`, `actorId`, `actorName` và `referenceId` có thể null theo schema/entity; không giả định mọi event đều có đủ các trường này.
- Snapshot thể hiện backend endpoint và DTO cung cấp dữ liệu cho timeline, nhưng không xác nhận có giao diện frontend timeline hoàn chỉnh.
- Không tự thêm action, trigger source, trạng thái hoặc hành vi audit ngoài những gì được tích hợp và kiểm thử.

## 13. Hướng dẫn cho AI tái tạo code

- Giữ change log trong GitHub Integration Service; không chuyển trách nhiệm lưu lịch sử sang frontend.
- Dùng `DocumentationChangeLogService.recordChange(...)` làm điểm ghi nhận thống nhất cho các luồng nghiệp vụ.
- Giữ đầy đủ metadata: document ID, repository ID nếu có, version, action, summary, actor, role, trigger source, status và reference ID.
- Giữ nguyên thứ tự ưu tiên role và quy tắc chuẩn hóa `ADMIN` thành `ADMINISTRATOR`.
- Giữ timestamp do entity tự tạo bằng `Instant.now()` và không cập nhật lại event lịch sử.
- Khi bổ sung luồng nghiệp vụ mới, xác định rõ actor, trigger source, action, status và reference ID trước khi gọi service.
- Tránh ghi trùng khi workflow và generation service cùng tham gia một thao tác; tuân theo cơ chế `ChangeLogOverride`/`suppressChangeLog` hiện có.
- Giữ API `GET /api/documentation/{docId}/change-log` và hai filter `status`, `triggerSource`; nếu thêm pagination hoặc filter mới cần cập nhật DTO/contract/test tương ứng.
- Giữ migration `V10__documentation_change_log.sql` trong `migration-common` và kiểm tra tất cả Flyway lineage liên quan khi thay đổi schema.
- Bổ sung test cho từng caller mới, trường hợp trigger/status không hợp lệ và quyền truy cập nếu mở rộng endpoint.
- Không tuyên bố có frontend timeline hoặc test pass nếu chưa có bằng chứng tương ứng trong source và kết quả chạy thực tế.
