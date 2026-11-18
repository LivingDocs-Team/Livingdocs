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

### Hợp đồng quan sát qua kiểm thử

- **FR-AUTH-REG.4 — Danh tính qua phiên.** `GET /api/auth/me` không nhận payload. Với phiên OAuth hợp lệ, tra tài khoản theo GitHub ID của principal đã xác thực. Với phiên email hợp lệ, tra theo email của principal. Trả `200` với `id`, `email`, `username`, `firstName`, `lastName`, `role` và không có token. Trả `401` nếu thiếu phiên hợp lệ, thiếu GitHub ID trong principal hoặc tài khoản tương ứng không tìm thấy.
- **FR-AUTH-REG.5 — Phân biệt xác thực và phân quyền.** Khi tài khoản bị khóa, yêu cầu dùng lại phiên cũ phải mất quyền truy cập. Khi phiên hợp lệ nhưng thiếu quyền hoặc thiếu CSRF ở thao tác yêu cầu CSRF, trả `403` và không ghi thay đổi.
- **FR-AUTH-REG.6 — Kiểm tra quyền qua các lớp.** Cùng một thao tác workspace/repository phải bị giới hạn theo danh tính phiên, quyền yêu cầu và phạm vi tài nguyên. Kiểm thử cả đường gọi qua Backend và kiểm tra ở GitHub Integration.

## 4. Luồng lỗi

Trả `401` khi không có xác thực hợp lệ và `403` khi thiếu quyền hoặc yêu cầu bị chính sách CSRF từ chối.

## 5. Tiêu chí chấp nhận

- **AC-AUTH-REG.1:** Callback mô phỏng thành công tạo phiên đọc được qua `/me` và phản hồi không chứa token.
- **AC-AUTH-REG.2:** Lỗi đổi token hoặc tài khoản bị khóa không tạo ra phiên sử dụng được.
- **AC-AUTH-REG.3:** Thiếu quyền hoặc CSRF bị chặn ở thao tác bảo vệ.

| Ca chấp nhận | Thiết lập và thao tác | Kết quả quan sát |
|---|---|---|
| AC-AUTH-REG.4 | GitHub mock trả callback hợp lệ. Gọi `/me` bằng cùng cookie phiên. | JSON đúng sáu trường danh tính; không có access token. |
| AC-AUTH-REG.5 | GitHub mock từ chối đổi mã; gọi lại `/me` với trình duyệt chưa đăng nhập trước đó. | `/me` trả `401`. |
| AC-AUTH-REG.6 | Dùng phiên đang hoạt động để gọi một thao tác cần quyền hoặc CSRF, lần lượt bỏ quyền và bỏ CSRF. | Từng lần trả `403`; kiểm tra tài nguyên đích chưa bị thay đổi. |

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#119](https://github.com/LivingDocs-Team/Livingdocs/pull/119) · [`79c4755`](https://github.com/LivingDocs-Team/Livingdocs/commit/79c4755).
- **Kiểm thử ghi nhận trong PR:** PR ghi nhận 60 test Backend và 50 test GitHub Integration thành công. Bộ Backend bỏ qua `BackendApplicationTests.contextLoads` do schema PostgreSQL local thiếu cột `roles_permissions.roles_name`. Callback dùng GitHub mock, còn chạy OAuth với GitHub thật trên trình duyệt được ghi là đang chờ.
