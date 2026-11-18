# FR-SYSTEM-AUDIT — Audit, giám sát và chính sách thông báo

| Mục | Nội dung |
|---|---|
| Story / Task Jira | [LD-280](https://ut-team-lvdocs.atlassian.net/browse/LD-280), [LD-281](https://ut-team-lvdocs.atlassian.net/browse/LD-281), [LD-282](https://ut-team-lvdocs.atlassian.net/browse/LD-282), [LD-283](https://ut-team-lvdocs.atlassian.net/browse/LD-283), [LD-284](https://ut-team-lvdocs.atlassian.net/browse/LD-284), [LD-285](https://ut-team-lvdocs.atlassian.net/browse/LD-285) |
| Trạng thái Jira (18/11/2026) | Done |
| Người thực hiện | Nhân Nguyễn ([nhanndt750402-max](https://github.com/nhanndt750402-max), đối chiếu theo PR và commit) |
| Thành phần | Backend, GitHub Integration, AI service |
| Tác nhân | Quản trị viên, service nội bộ |
| Phụ thuộc | [FR5 — RBAC](FR5.md), [ENG-OPS-01](ENG-OPS-01-Docker-Compose-CI-Validation.md) |
| Mục tiêu | Theo dõi tác vụ, phân tích hoạt động và quản lý chính sách thông báo. |

## 1. Mô tả

Các service ghi nhận kết quả xử lý để phục vụ audit và chẩn đoán. Quản trị viên truy vấn thống kê và thiết lập chính sách thông báo; phạm vi xác minh của PR dừng ở cấu hình chính sách.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-SYSTEM-AUDIT.1 | Ghi trạng thái tác vụ AI và kết quả webhook. |
| FR-SYSTEM-AUDIT.2 | Kiểm tra tình trạng phụ thuộc, ghi audit thao tác quản trị và dọn bản ghi hết hạn. |
| FR-SYSTEM-AUDIT.3 | Cung cấp thống kê theo khoảng thời gian và cho phép quản trị chính sách thông báo. |

## 3. API và luồng xử lý

`GET /api/admin/system-analytics` đọc thống kê. `/api/admin/notification-policies` liệt kê chính sách; `PUT` và `DELETE` trên `/{event}` cập nhật hoặc xóa cấu hình.

### Hợp đồng thống kê và chính sách

- **FR-SYSTEM-AUDIT.4 — Khoảng thời gian thống kê.** `GET /api/admin/system-analytics?from=...&to=...` nhận hai thời điểm ISO 8601 có offset. Yêu cầu `from < to`, chính xác tối đa đến microsecond. Phạm vi đếm là `[from, to)`. `200` trả `from`, `to`, `repositoriesCreated`, `documentsCreated`, `audit` và `aiJobs`. `audit` gồm `administration`, `documentWorkflow`, `documentVersion`. `aiJobs` gồm `completed`, `failed`, `observedSince` và `scope=CURRENT_AI_PROCESS`.
- **FR-SYSTEM-AUDIT.5 — Xử lý nguồn không khả dụng.** Khoảng sai trả `400`. Khi phụ thuộc GitHub Integration/AI không khả dụng hoặc trả số liệu thiếu, trả `503`; frontend phải phân biệt lỗi truy vấn với thống kê bằng 0. Kết quả có header `Cache-Control: no-store`.
- **FR-SYSTEM-AUDIT.6 — Lưu chính sách theo sự kiện.** `GET /api/admin/notification-policies` trả `supportedEvents` và `policies`. `PUT /{event}` nhận `recipients` từ 1–50 email hợp lệ, mỗi địa chỉ tối đa 254 ký tự, và `enabled` bắt buộc. Loại email trùng khi lưu. Một sự kiện có một bản ghi chính sách; PUT lần sau cập nhật bản ghi đó, trả `event`, `recipients`, `enabled`, `updatedAt`. DELETE trả `204`. Ghi audit khi lưu hoặc khi thực sự xóa bản ghi.
- **FR-SYSTEM-AUDIT.7 — Danh mục sự kiện.** Hỗ trợ `REPOSITORY_CONNECTED`, `DOCUMENT_SUBMITTED`, `DOCUMENT_APPROVED`, `DOCUMENT_REJECTED`, `AI_JOB_COMPLETED`, `AI_JOB_FAILED`.

## 4. Luồng lỗi

Giới hạn API cho người có quyền quản trị. Job AI đã mất sau khi service khởi động lại trả `404` khi truy vấn.

## 5. Tiêu chí chấp nhận

- **AC-SYSTEM-AUDIT.1:** Quản trị viên truy vấn được thống kê theo khoảng thời gian.
- **AC-SYSTEM-AUDIT.2:** Cập nhật chính sách cho một sự kiện có thể đọc lại từ API.
- **AC-SYSTEM-AUDIT.3:** Truy vấn job AI đã mất sau restart trả `404`.

| Ca chấp nhận | Thiết lập và thao tác | Kết quả quan sát |
|---|---|---|
| AC-SYSTEM-AUDIT.4 | Đặt hai sự kiện audit đúng tại `from` và `to`. | Chỉ sự kiện đúng `from` được tính. |
| AC-SYSTEM-AUDIT.5 | Nguồn AI trả lỗi trong lúc truy vấn. | API trả `503`. |
| AC-SYSTEM-AUDIT.6 | Lưu chính sách với cùng email hai lần, đọc lại rồi xóa. | Đọc được một email; sau `204`, danh sách không còn chính sách của sự kiện đó. |

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#141](https://github.com/LivingDocs-Team/Livingdocs/pull/141) · [`dfc83d3`](https://github.com/LivingDocs-Team/Livingdocs/commit/dfc83d3).
- **Kiểm thử ghi nhận trong PR:** PR ghi nhận 82 test Backend trên PostgreSQL 18, 260 test GitHub Integration thành công và 1 bỏ qua, 264 test AI thành công và 23 bỏ qua. Kiểm tra khởi động lại AI service xác nhận truy vấn job trở về 404 sau restart. Chưa xác minh triển khai Compose E2E.
