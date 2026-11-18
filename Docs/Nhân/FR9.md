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

## 4. Luồng lỗi

Giới hạn API cho người có quyền quản trị. Job AI đã mất sau khi service khởi động lại trả `404` khi truy vấn.

## 5. Tiêu chí chấp nhận

- **AC-SYSTEM-AUDIT.1:** Quản trị viên truy vấn được thống kê theo khoảng thời gian.
- **AC-SYSTEM-AUDIT.2:** Cập nhật chính sách cho một sự kiện có thể đọc lại từ API.
- **AC-SYSTEM-AUDIT.3:** Truy vấn job AI đã mất sau restart trả `404`.

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#141](https://github.com/LivingDocs-Team/Livingdocs/pull/141) · [`dfc83d3`](https://github.com/LivingDocs-Team/Livingdocs/commit/dfc83d3).
- **Kiểm thử ghi nhận trong PR:** PR ghi nhận 82 test Backend trên PostgreSQL 18, 260 test GitHub Integration thành công và 1 bỏ qua, 264 test AI thành công và 23 bỏ qua. Kiểm tra khởi động lại AI service xác nhận truy vấn job trở về 404 sau restart. Chưa xác minh triển khai Compose E2E.
