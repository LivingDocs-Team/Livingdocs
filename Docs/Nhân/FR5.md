# FR-RBAC — Quản lý người dùng, vai trò và quyền

| Mục | Nội dung |
|---|---|
| Story / Task Jira | [LD-261](https://ut-team-lvdocs.atlassian.net/browse/LD-261), [LD-262](https://ut-team-lvdocs.atlassian.net/browse/LD-262), [LD-263](https://ut-team-lvdocs.atlassian.net/browse/LD-263), [LD-264](https://ut-team-lvdocs.atlassian.net/browse/LD-264), [LD-265](https://ut-team-lvdocs.atlassian.net/browse/LD-265), [LD-266](https://ut-team-lvdocs.atlassian.net/browse/LD-266) |
| Trạng thái Jira (18/11/2026) | Done |
| Người thực hiện | Nhân Nguyễn ([nhanndt750402-max](https://github.com/nhanndt750402-max), đối chiếu theo PR và commit) |
| Thành phần | Backend Admin, GitHub Integration |
| Tác nhân | Quản trị viên, người dùng đã xác thực |
| Phụ thuộc | Danh mục vai trò/quyền, cơ chế xác thực, [screen flow RBAC](../rbac-screen-flow.md) |
| Mục tiêu | Quản trị tài khoản và áp dụng quyền theo danh tính. |

## 1. Mô tả

PR #107 triển khai quản trị tài khoản. PR #109 bổ sung danh mục vai trò và quyền, đồng thời đặt nền cho luồng Developer gửi, Staff review và Manager quyết định. Xem [FR6](FR6.md) và [FR10](FR10.md) cho các phần mở rộng workflow.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-RBAC.1 | Cho phép quản trị viên tra cứu, sửa, khóa và mở khóa tài khoản. |
| FR-RBAC.2 | Chặn đăng nhập và vô hiệu phiên hiện có khi tài khoản bị khóa. |
| FR-RBAC.3 | Cho phép quản lý vai trò và tập quyền gắn với từng vai trò. |
| FR-RBAC.4 | Kiểm tra quyền theo danh tính đã xác thực tại Backend và GitHub Integration. |

## 3. API và luồng xử lý

`GET /api/admin/users` liệt kê người dùng; `PATCH /api/admin/users/{id}` cập nhật tài khoản. Các đường dẫn con `/status` và `/role` cập nhật trạng thái và vai trò. Dùng `GET /api/admin/roles`, `GET /api/admin/permissions` và `PUT /api/admin/roles/{name}/permissions` để xem danh mục và gán quyền.

## 4. Luồng lỗi

Phiên không hợp lệ bị từ chối xác thực. Tài khoản thiếu quyền quản trị bị chặn tại thao tác tương ứng.

## 5. Tiêu chí chấp nhận

- **AC-RBAC.1:** Quản trị viên có thể cập nhật trạng thái và vai trò.
- **AC-RBAC.2:** Phiên hiện có của tài khoản bị khóa không còn truy cập được.
- **AC-RBAC.3:** Người dùng thiếu quyền bị từ chối khi gọi API quản trị.

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#107](https://github.com/LivingDocs-Team/Livingdocs/pull/107), [#109](https://github.com/LivingDocs-Team/Livingdocs/pull/109) · [`5a4bf2f`](https://github.com/LivingDocs-Team/Livingdocs/commit/5a4bf2f), [`ecb480b`](https://github.com/LivingDocs-Team/Livingdocs/commit/ecb480b).
- **Kiểm thử ghi nhận trong PR:** #107 ghi nhận 25 test Maven và 7 job CI thành công. #109 ghi nhận 17 test workflow, test khởi tạo danh mục vai trò và biên dịch Java 21 thành công. Phần kiểm chứng của #109 còn để ngỏ migration trên cơ sở dữ liệu đang chạy và E2E toàn hệ thống.
