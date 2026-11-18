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

### Hợp đồng quản trị tài khoản

| API | Input và ràng buộc | Kết quả |
|---|---|---|
| `GET /api/admin/users` | Cần `USER_VIEW`. `page=0`, `size=20` mặc định; bộ lọc tùy chọn `search`, `role`, `active`. | Trang tài khoản và metadata phân trang. |
| `PATCH /api/admin/users/{id}` | Cần `USER_UPDATE`. Cập nhật từng trường `username`, `email`, `firstName`, `lastName`; trường vắng mặt giữ giá trị cũ. | Trả tài khoản sau cập nhật. Username 1–50 ký tự; email được trim và viết thường, tối đa 255 ký tự. Email và username phải duy nhất khi so sánh không phân biệt hoa thường. |
| `PATCH /api/admin/users/{id}/status` | `{"active":false}` để khóa, `true` để mở khóa. Cần `USER_DISABLE`. | Trả tài khoản sau cập nhật. |
| `PATCH /api/admin/users/{id}/role` | `{"role":"STAFF"}`. Cần `USER_ASSIGN_ROLE`. Chấp nhận `DEVELOPER`, `STAFF`, `MANAGER`, `TECHNICAL_LEAD`, `ADMINISTRATOR`. | Trả tài khoản với vai trò chính mới. |

- **FR-RBAC.5 — Bảo vệ tài khoản quản trị đang thao tác.** Từ chối quản trị viên đổi trạng thái hoặc vai trò chính của chính mình bằng `403`. Dữ liệu thiếu hoặc sai trả `400`, tài khoản đích không tồn tại trả `404`, email/username trùng trả `409`.
- **FR-RBAC.6 — Lưu cấu hình quyền.** Cần `ROLE_VIEW` để đọc vai trò, `PERMISSION_VIEW` để đọc quyền và `ROLE_ASSIGN_PERMISSION` để cập nhật cấu hình. `PATCH /api/admin/roles/{name}` nhận `description` dài 1–120 ký tự. `PUT /api/admin/roles/{name}/permissions` nhận `permissionCodes` là tập mã quyền thay thế, kiểm tra mã tồn tại và bảo vệ quyền của `ADMINISTRATOR` khỏi bị gỡ. Vai trò trả về có `name`, `description`, `permissions`.
- **FR-RBAC.7 — Ghi audit khi thực sự thay đổi.** Ghi ID người thao tác, tài khoản đích và thay đổi về hồ sơ, trạng thái hoặc vai trò. Gửi lại cùng giá trị không tạo audit thay đổi mới.

## 4. Luồng lỗi

Phiên không hợp lệ bị từ chối xác thực. Tài khoản thiếu quyền quản trị bị chặn tại thao tác tương ứng.

## 5. Tiêu chí chấp nhận

- **AC-RBAC.1:** Quản trị viên có thể cập nhật trạng thái và vai trò.
- **AC-RBAC.2:** Phiên hiện có của tài khoản bị khóa không còn truy cập được.
- **AC-RBAC.3:** Người dùng thiếu quyền bị từ chối khi gọi API quản trị.

| Ca chấp nhận | Thiết lập và thao tác | Kết quả quan sát |
|---|---|---|
| AC-RBAC.4 | Quản trị viên tự gửi yêu cầu khóa tài khoản của mình. | `403`; tài khoản vẫn hoạt động. |
| AC-RBAC.5 | Đổi email user A thành email user B chỉ khác hoa thường. | `409`; đọc lại A thấy email cũ. |
| AC-RBAC.6 | Gửi danh sách quyền chứa mã không tồn tại. | `400`; đọc lại vai trò thấy nguyên tập quyền trước đó. |

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#107](https://github.com/LivingDocs-Team/Livingdocs/pull/107), [#109](https://github.com/LivingDocs-Team/Livingdocs/pull/109) · [`5a4bf2f`](https://github.com/LivingDocs-Team/Livingdocs/commit/5a4bf2f), [`ecb480b`](https://github.com/LivingDocs-Team/Livingdocs/commit/ecb480b).
- **Kiểm thử ghi nhận trong PR:** #107 ghi nhận 25 test Maven và 7 job CI thành công. #109 ghi nhận 17 test workflow, test khởi tạo danh mục vai trò và biên dịch Java 21 thành công. Phần kiểm chứng của #109 còn để ngỏ migration trên cơ sở dữ liệu đang chạy và E2E toàn hệ thống.
