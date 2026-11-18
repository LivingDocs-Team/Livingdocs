# FR-APPROVAL-HISTORY — Lịch sử phê duyệt tài liệu

| Mục | Nội dung |
|---|---|
| Story / Task Jira | [LD-251](https://ut-team-lvdocs.atlassian.net/browse/LD-251), [LD-252](https://ut-team-lvdocs.atlassian.net/browse/LD-252), [LD-253](https://ut-team-lvdocs.atlassian.net/browse/LD-253), [LD-254](https://ut-team-lvdocs.atlassian.net/browse/LD-254), [LD-255](https://ut-team-lvdocs.atlassian.net/browse/LD-255), [LD-256](https://ut-team-lvdocs.atlassian.net/browse/LD-256) |
| Trạng thái Jira (18/11/2026) | Done |
| Người thực hiện | Nhân Nguyễn ([nhanndt750402-max](https://github.com/nhanndt750402-max), đối chiếu theo PR và commit) |
| Thành phần | GitHub Integration, giao diện workflow |
| Tác nhân | Manager và người có quyền xem lịch sử |
| Phụ thuộc | [FR5 — RBAC](FR5.md), [screen flow RBAC](../rbac-screen-flow.md) |
| Mục tiêu | Tra cứu quyết định đã lưu theo quyền xem. |

## 1. Mô tả

Lịch sử lưu quyết định cùng danh tính và vai trò xác thực tại thời điểm phê duyệt. Bản ghi tạo trước khi có trường vai trò vẫn có thể xuất hiện.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-APPROVAL-HISTORY.1 | Lưu quyết định, người phê duyệt, vai trò đã xác thực, thời điểm và lý do. |
| FR-APPROVAL-HISTORY.2 | Phân trang danh sách workflow có lịch sử theo quyền xem. |
| FR-APPROVAL-HISTORY.3 | Hiển thị dữ liệu quyết định đã lưu và hỗ trợ bản ghi cũ thiếu vai trò. |

## 3. API và luồng xử lý

`GET /api/document-workflows/history-accessible` lấy danh sách theo quyền. `GET /api/document-workflows/{id}/history` lấy lịch sử của workflow được chọn.

## 4. Luồng lỗi

Từ chối truy cập lịch sử của workflow ngoài phạm vi quyền. Giao diện vẫn hiển thị được bản ghi cũ thiếu vai trò.

## 5. Tiêu chí chấp nhận

- **AC-APPROVAL-HISTORY.1:** Quyết định mới có đầy đủ thông tin audit.
- **AC-APPROVAL-HISTORY.2:** Phân trang và quyền xem giới hạn đúng tập workflow.
- **AC-APPROVAL-HISTORY.3:** Bản ghi cũ thiếu vai trò vẫn đọc được.

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#113](https://github.com/LivingDocs-Team/Livingdocs/pull/113) · [`6c57a87`](https://github.com/LivingDocs-Team/Livingdocs/commit/6c57a87), [`9892f65`](https://github.com/LivingDocs-Team/Livingdocs/commit/9892f65).
- **Kiểm thử ghi nhận trong PR:** PR ghi nhận 25 test Backend gồm 22 test service và 3 test persistence H2, cùng ESLint và build Vite thành công.
