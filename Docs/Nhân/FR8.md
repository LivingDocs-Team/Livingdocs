# FR-AUTH-REG — Hồi quy phân quyền và GitHub OAuth

| Mục | Nội dung |
|---|---|
| Story / Task Jira | [LD-399](https://ut-team-lvdocs.atlassian.net/browse/LD-399), [LD-400](https://ut-team-lvdocs.atlassian.net/browse/LD-400) |
| Trạng thái Jira (18/11/2026) | Done |
| Người thực hiện | Nhân Nguyễn ([nhanndt750402-max](https://github.com/nhanndt750402-max), đối chiếu theo PR và commit) |
| Thành phần | Backend Auth, GitHub Integration |
| Tác nhân | Người dùng đăng nhập GitHub, quản trị viên |
| Phụ thuộc | [FR1 — Phục hồi phiên](FR1.md), [FR5 — RBAC](FR5.md), [FR7 — Workspace](FR7.md) |
| Mục tiêu | Xác minh các contract bảo mật tại ranh giới phiên và quyền truy cập. |

## 1. Mô tả

Phạm vi là kiểm thử hồi quy của PR #119. Jira LD-400 nhắc PR #94 trong tiêu đề; bằng chứng của bộ kiểm thử này nằm ở PR #119.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AUTH-REG.1 | Callback OAuth thành công cho phép khôi phục danh tính qua `GET /api/auth/me` mà phản hồi không chứa token. |
| FR-AUTH-REG.2 | Từ chối callback nếu đổi mã lấy token thất bại và vô hiệu phiên khi tài khoản bị khóa. |
| FR-AUTH-REG.3 | Kiểm tra CSRF và quyền trên workspace/repository trước khi thực hiện thao tác được bảo vệ. |

## 3. API và luồng xử lý

Sau callback, frontend gọi `GET /api/auth/me` để đọc phiên. Các API yêu cầu xác thực hoặc quyền workspace/repository được kiểm tra bằng các tình huống hồi quy.

## 4. Luồng lỗi

Trả `401` khi không có xác thực hợp lệ và `403` khi thiếu quyền hoặc yêu cầu bị chính sách CSRF từ chối.

## 5. Tiêu chí chấp nhận

- **AC-AUTH-REG.1:** Callback mô phỏng thành công tạo phiên đọc được qua `/me` và phản hồi không chứa token.
- **AC-AUTH-REG.2:** Lỗi đổi token hoặc tài khoản bị khóa không tạo ra phiên sử dụng được.
- **AC-AUTH-REG.3:** Thiếu quyền hoặc CSRF bị chặn ở thao tác bảo vệ.

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#119](https://github.com/LivingDocs-Team/Livingdocs/pull/119) · [`79c4755`](https://github.com/LivingDocs-Team/Livingdocs/commit/79c4755).
- **Kiểm thử ghi nhận trong PR:** PR ghi nhận 60 test Backend và 50 test GitHub Integration thành công. Bộ Backend bỏ qua `BackendApplicationTests.contextLoads` do schema PostgreSQL local thiếu cột `roles_permissions.roles_name`. Callback dùng GitHub mock, còn chạy OAuth với GitHub thật trên trình duyệt được ghi là đang chờ.
