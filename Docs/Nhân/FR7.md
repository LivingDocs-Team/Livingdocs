# FR-WORKSPACE — Quản trị workspace và repository

| Mục | Nội dung |
|---|---|
| Story / Task Jira | [LD-267](https://ut-team-lvdocs.atlassian.net/browse/LD-267), [LD-268](https://ut-team-lvdocs.atlassian.net/browse/LD-268), [LD-269](https://ut-team-lvdocs.atlassian.net/browse/LD-269), [LD-270](https://ut-team-lvdocs.atlassian.net/browse/LD-270), [LD-271](https://ut-team-lvdocs.atlassian.net/browse/LD-271), [LD-272](https://ut-team-lvdocs.atlassian.net/browse/LD-272) |
| Trạng thái Jira (18/11/2026) | Done |
| Người thực hiện | Nhân Nguyễn ([nhanndt750402-max](https://github.com/nhanndt750402-max), đối chiếu theo PR và commit) |
| Thành phần | Backend, GitHub Integration, Frontend |
| Tác nhân | OWNER, MEMBER |
| Phụ thuộc | [FR5 — RBAC](FR5.md), [luồng repository dùng chung](../Đăng/FR2.md) |
| Mục tiêu | Quản lý thành viên và vị trí của repository trong workspace. |

## 1. Mô tả

Workspace tập hợp repository và thành viên. Quyền theo membership chi phối thao tác trên workspace và việc chuyển repository.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-WORKSPACE.1 | Tạo, liệt kê, xem và sửa workspace trong phạm vi quyền. |
| FR-WORKSPACE.2 | Quản lý thành viên theo vai trò OWNER/MEMBER. |
| FR-WORKSPACE.3 | Kiểm tra liên kết repository trùng và kiểm tra quyền khi chuyển repository giữa workspace. |

## 3. API và luồng xử lý

Backend dùng `/api/managed-workspaces` để tạo và liệt kê, `GET` và `PUT` trên `/{workspaceId}` để xem và sửa. Dùng `GET` và `POST` trên `/{workspaceId}/members` và `DELETE` trên `/{workspaceId}/members/{userId}` để quản lý thành viên. Luồng chuyển repository kiểm tra quyền trước khi thay đổi liên kết.

## 4. Luồng lỗi

Từ chối thao tác quản trị khi thiếu quyền và từ chối liên kết trùng.

## 5. Tiêu chí chấp nhận

- **AC-WORKSPACE.1:** OWNER có thể quản lý thành viên trong workspace của mình.
- **AC-WORKSPACE.2:** MEMBER không thực hiện được thao tác dành riêng cho OWNER.
- **AC-WORKSPACE.3:** Một lần chuyển hợp lệ cập nhật liên kết; lần chuyển không hợp lệ giữ liên kết cũ.

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#114](https://github.com/LivingDocs-Team/Livingdocs/pull/114) · [`00281cc`](https://github.com/LivingDocs-Team/Livingdocs/commit/00281cc), [`b7f410d`](https://github.com/LivingDocs-Team/Livingdocs/commit/b7f410d).
- **Kiểm thử ghi nhận trong PR:** PR ghi nhận 25 test mock Backend, 11 test mock GitHub Integration, 9 test Repository Sync trên H2, ESLint và build Vite thành công. PR chưa xác minh persistence workspace/thành viên trên cơ sở dữ liệu riêng hoặc ghi liên kết đồng thời trên PostgreSQL.
