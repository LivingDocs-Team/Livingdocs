# FR-BE—05 Ghi nhận và hiển thị lịch sử thay đổi tài liệu

| Mục | Nội dung |
|---|---|
| Story Jira | LD-177 – [Documentation Change Log] Implement Documentation Change Log (thuộc Epic `LD-10`) |
| Task đã làm | `LD-178` Record Documentation Changes; `LD-179` Display Documentation Change Timeline; `LD-180` Record Change User and Role; `LD-181` Record Change Timestamp and Trigger; `LD-182` Test Documentation Change Log |
| Người thực hiện | Nguyễn Lê Minh |
| Thành phần | GitHub Integration Service (`V10__documentation_change_log.sql`, `DocumentationChangeLog.java`, `ChangeTriggerSource.java`, `DocumentationChangeLogRepository.java`, `DocumentationChangeLogService.java`, `DocumentationChangeLogResponse.java`, `DocumentationChangeLogController.java`, `DocumentWorkflowService.java`, `DocumentationGenerationService.java`, `IngestionService.java`); Backend BFF (`GitHubIntegrationBffController.java`); AI Service (`app/version_models.py`, `app/versions.py`, `main.py`); Frontend (`frontend/src/app/documentation/change-log-timeline/ChangeLogTimeline.tsx`); Tests (`DocumentationChangeLogServiceTest.java`, `GitHubIntegrationBffDocumentationAuthTest.java`, `ai-service/tests/test_versions.py`) |
| Tác nhân | Người dùng tạo/chỉnh sửa/xét duyệt tài liệu (`DEVELOPER`, `STAFF`, `TECHNICAL_LEAD`, `MANAGER`, `ADMINISTRATOR`); Hệ thống sinh tài liệu AI và Webhook GitHub (`SYSTEM`) |

## 1. Mô tả

Chức năng bổ sung hệ thống nhật ký thay đổi tài liệu (**Documentation Change Log**) cho LivingDocs nhằm ghi nhận toàn bộ vòng đời biến động của tài liệu. Mỗi sự kiện thay đổi đều lưu trữ định danh tài liệu, repository, số phiên bản, loại hành động, nội dung tóm tắt, người thực hiện (`actor_id`, `actor_name`), vai trò chính (`actor_role`), nguồn kích hoạt (`trigger_source`), trạng thái tài liệu (`status`), mã tham chiếu (`reference_id`) và dấu thời gian (`created_at`).

Kiến trúc triển khai gồm 4 lớp phối hợp:
- **GitHub Integration Service:** Lưu trữ bền vững vào bảng PostgreSQL `documentation_change_logs` (Flyway `V10`), tự động ghi log từ các luồng sinh tài liệu AI, cập nhật/duyệt workflow và sự kiện ingestion/webhook, đồng thời cung cấp API `GET /api/documentation/{docId}/change-log` hỗ trợ lọc theo `status` và `triggerSource`.
- **Backend BFF:** Xác thực người dùng, kiểm tra quyền truy cập workspace/tài liệu trước khi proxy yêu cầu `GET /api/documentation/{docId}/change-log` sang GitHub Integration Service.
- **AI Service:** Quản lý audit trail phiên bản (`HistoryEvent`) theo từng document và cung cấp API đọc lịch sử (`/documents/{doc_id}/history` và `/internal/documents/{doc_id}/history`).
- **Frontend:** Component `ChangeLogTimeline` truy vấn `/api/documentation/{documentId}/change-log` và hiển thị dòng thời gian thay đổi cùng các trạng thái tải, rỗng và lỗi phân quyền.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-BE—05.1 | **Lưu trữ bền vững bảng `documentation_change_logs`:** Migration `V10__documentation_change_log.sql` tạo bảng `documentation_change_logs` với khóa chính `id VARCHAR(64)`, các cột `document_id`, `repository_id`, `version_number`, `action`, `summary`, `actor_id`, `actor_name`, `actor_role`, `trigger_source`, `status`, `reference_id`, `created_at` (`TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP`), cùng 2 index `idx_doc_changelog_doc_created` và `idx_doc_changelog_repo_created`. |
| FR-BE—05.2 | **Ghi nhận sự kiện thay đổi tài liệu (`LD-178`):** `DocumentationChangeLogService.recordChange(...)` ghi nhận mọi biến động trong vòng đời tài liệu (từ `DocumentationGenerationService`, `DocumentWorkflowService`, `IngestionService`), gắn với `document_id`, `repository_id`, `version_number`, `action` (ví dụ `CREATED`, `PROPOSED`, `ACCEPTED`, `EDITED`, `DISMISSED`, `REGENERATED`, `SUPERSEDED`, `ROLLED_BACK`) và `reference_id`. |
| FR-BE—05.3 | **Chuẩn hóa tóm tắt & giá trị mặc định:** `summary` được cắt gọn tối đa 500 ký tự (thêm `...` nếu vượt quá) hoặc gán mặc định `"Documentation updated"` nếu trống; `status` được chuẩn hóa chữ hoa (mặc định `"DRAFT"`); `@PrePersist` tự sinh `id` dạng UUID nếu chưa có. |
| FR-BE—05.4 | **Ghi nhận người thực hiện & phân giải vai trò chính (`LD-180`):** Lưu `actor_id` và `actor_name` (nếu `actor_name` trống thì fallback về `actor_id`). Hàm `resolvePrimaryRole(authorities)` loại bỏ tiền tố `ROLE_` và chọn vai trò có độ ưu tiên cao nhất theo thứ tự `ADMINISTRATOR` (chuẩn hóa từ `ADMIN`), `MANAGER`, `TECHNICAL_LEAD`, `STAFF`, `DEVELOPER`; nếu không có quyền nào thì gán `"SYSTEM"`. |
| FR-BE—05.5 | **Ghi nhận thời điểm & nguồn kích hoạt (`LD-181`):** Tự động ghi nhận dấu thời gian `created_at = Instant.now()` (UTC) và phân loại nguồn kích hoạt qua enum `ChangeTriggerSource` gồm 6 giá trị: `AI_GENERATION`, `MANUAL_EDIT`, `DRIFT_SUGGESTION`, `PR_WEBHOOK`, `REVIEW_WORKFLOW`, `ROLLBACK` (mặc định `MANUAL_EDIT` nếu không truyền). |
| FR-BE—05.6 | **Truy vấn & lọc timeline theo tài liệu:** `DocumentationChangeLogService.getTimeline(documentId, statusFilter, triggerFilter)` truy vấn các bản ghi của `documentId` sắp xếp giảm dần theo `created_at DESC`, hỗ trợ lọc tùy chọn theo `status`, `triggerSource` hoặc kết hợp cả hai. |
| FR-BE—05.7 | **Kiểm soát quyền truy cập ở BFF và Downstream Service:** Tại Backend BFF (`GitHubIntegrationBffController`), route `GET /api/documentation/{docId}/change-log` giải quyết workspace sở hữu tài liệu qua `/api/internal/documents/{docId}/workspace` và kiểm tra quyền thành viên/chủ workspace trước khi proxy. Tại GitHub Integration Service (`DocumentationChangeLogController`), kiểm tra header `X-User-Id` và quyền đọc tài liệu qua `DocumentAccessService.canReadDocument(callerUserId, docId)`. |
| FR-BE—05.8 | **Audit trail phiên bản trên AI Service:** Mô hình `HistoryEvent` (`app/version_models.py`) và module `app/versions.py` ghi nhận lịch sử phiên bản (`action`, `version`, `actor`, `actor_role`, `trigger_source`, `status`, `note`, `related_version`, `at`) và cung cấp API `GET /documents/{doc_id}/history` cùng `GET /internal/documents/{doc_id}/history` (sắp xếp theo thứ tự thời gian tăng dần). |
| FR-BE—05.9 | **Hiển thị timeline trên giao diện (`LD-179`):** Component `ChangeLogTimeline.tsx` hiển thị tiêu đề `"Lịch sử thay đổi tài liệu"`, gọi `GET /api/documentation/${documentId}/change-log`, hiển thị danh sách `<ol>` gồm tên người thực hiện (`actorName`), thời điểm định dạng theo locale (`toLocaleString()`), tóm tắt (`summary`) và loại sự kiện (`eventType`). |
| FR-BE—05.10 | **Xử lý trạng thái tải, rỗng và lỗi trên giao diện:** Khi đang gọi API hiển thị `"Đang tải…"`; khi danh sách trống hiển thị `"Chưa có thay đổi nào."`; khi nhận HTTP `403` hoặc `404` hiển thị `"Bạn không có quyền xem lịch sử thay đổi của tài liệu này."`; các lỗi HTTP/mạng khác hiển thị `"Không tải được lịch sử thay đổi."`. |

## 3. API / Giao diện & Mô hình dữ liệu

### 3.1. Danh sách Endpoint

| Service | Method | Endpoint | Tham số / Header | Kết quả | Yêu cầu |
|---|---|---|---|---|---|
| Backend BFF / GitHub Integration | `GET` | `/api/documentation/{docId}/change-log` | Query tùy chọn: `status`, `triggerSource`; Header nội bộ: `X-User-Id` | `200 OK` + `List<DocumentationChangeLogResponse>` | FR-BE—05.6, FR-BE—05.7 |
| GitHub Integration (Internal) | `GET` | `/api/internal/documents/{docId}/workspace` | Header: `Authorization: Bearer <secret>`, `X-User-Id`, `X-User-Authorities` | `200 OK` + `{"workspaceId": "..."}` (dùng để BFF xác minh quyền đọc tài liệu) | FR-BE—05.7 |
| AI Service | `GET` | `/documents/{doc_id}/history` | Path: `doc_id` | `200 OK` + `List[HistoryEvent]` (cũ trước, mới sau) | FR-BE—05.8 |
| AI Service (Internal) | `GET` | `/internal/documents/{doc_id}/history` | Path: `doc_id`, Internal Service Auth | `200 OK` + `List[HistoryEvent]` | FR-BE—05.8 |

### 3.2. Cấu trúc bảng `documentation_change_logs` (`V10__documentation_change_log.sql`)

| Cột | Kiểu dữ liệu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| `id` | `VARCHAR(64)` | `PRIMARY KEY` | Định danh UUID của bản ghi change log. |
| `document_id` | `VARCHAR(64)` | `NOT NULL` | Định danh tài liệu phát sinh thay đổi. |
| `repository_id` | `UUID` | Nullable | Định danh repository liên quan (nếu có). |
| `version_number` | `INTEGER` | Nullable | Số phiên bản tài liệu tại thời điểm sự kiện. |
| `action` | `VARCHAR(64)` | `NOT NULL` | Hành động thay đổi (`CREATED`, `PROPOSED`, `ACCEPTED`, `EDITED`, `DISMISSED`, `REGENERATED`, `SUPERSEDED`, `ROLLED_BACK`...). |
| `summary` | `VARCHAR(500)` | `NOT NULL` | Mô tả tóm tắt thay đổi (tối đa 500 ký tự). |
| `actor_id` | `VARCHAR(128)` | Nullable | ID người dùng thực hiện (hoặc `null` nếu tác nhân hệ thống). |
| `actor_name` | `VARCHAR(255)` | Nullable | Tên hiển thị của người thực hiện. |
| `actor_role` | `VARCHAR(64)` | `NOT NULL` | Vai trò chính (`ADMINISTRATOR`, `MANAGER`, `TECHNICAL_LEAD`, `STAFF`, `DEVELOPER`, `SYSTEM`). |
| `trigger_source` | `VARCHAR(64)` | `NOT NULL` | Nguồn kích hoạt (`AI_GENERATION`, `MANUAL_EDIT`, `DRIFT_SUGGESTION`, `PR_WEBHOOK`, `REVIEW_WORKFLOW`, `ROLLBACK`). |
| `status` | `VARCHAR(64)` | `NOT NULL` | Trạng thái tài liệu tại thời điểm ghi nhận (ví dụ `DRAFT`, `PENDING_STAFF_REVIEW`, `APPROVED`). |
| `reference_id` | `VARCHAR(128)` | Nullable | Mã tham chiếu liên quan (ví dụ `jobId`, `workflowId`, mã phiên bản). |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL DEFAULT CURRENT_TIMESTAMP` | Thời điểm tạo bản ghi (UTC). |

**Ví dụ response `GET /api/documentation/{docId}/change-log` (`200 OK`):**

```json
[
  {
    "id": "8f14e45f-ea9c-4b21-9d2a-1c3b4d5e6f70",
    "documentId": "doc-123",
    "repositoryId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "versionNumber": 2,
    "action": "ROLLED_BACK",
    "summary": "Rollback to version 1",
    "actorId": "u-2",
    "actorName": "Bob",
    "actorRole": "ADMINISTRATOR",
    "triggerSource": "ROLLBACK",
    "status": "PENDING_STAFF_REVIEW",
    "referenceId": "v1",
    "createdAt": "2026-11-23T02:15:30Z"
  },
  {
    "id": "45c48cce-2e2d-4fb6-a1b2-3c4d5e6f7a8b",
    "documentId": "doc-123",
    "repositoryId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "versionNumber": 1,
    "action": "CREATED",
    "summary": "Initial AI generation",
    "actorId": "u-1",
    "actorName": "Alice",
    "actorRole": "MANAGER",
    "triggerSource": "AI_GENERATION",
    "status": "DRAFT",
    "referenceId": "job-001",
    "createdAt": "2026-11-23T01:40:00Z"
  }
]