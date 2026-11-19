# ENG-OPS-03 — Tổ chức mã xác thực và kiểm thử Backend

| Mục | Nội dung |
|---|---|
| Story / Task Jira | Chưa xác minh ticket riêng. |
| Người thực hiện | Nhân Nguyễn ([nhanndt750402-max](https://github.com/nhanndt750402-max), đối chiếu theo PR và commit) |
| Thành phần | Backend Java, cấu hình Maven. |
| Mục tiêu | Tách mã xác thực, cấu hình bảo mật và các nguồn kiểm thử theo cấu trúc Backend. |

## Thay đổi

- PR #120 gom mã xác thực vào package `auth`, cấu hình bảo mật và CSRF vào `security`, rồi chuyển test tương ứng.
- PR #121 chuyển 12 tệp test vào `backend/src/main/tests/java` và cập nhật Maven để nhận đúng thư mục nguồn test.

## Tiêu chí chấp nhận

- Maven tìm và chạy test từ thư mục mới.
- JAR ứng dụng không chứa lớp test hoặc thư viện chỉ dùng cho test.

## Kiểm thử và PR

- **GitHub:** Cả hai PR đã merge vào `main`. [#120](https://github.com/LivingDocs-Team/Livingdocs/pull/120), [#121](https://github.com/LivingDocs-Team/Livingdocs/pull/121) · [`014d5bf`](https://github.com/LivingDocs-Team/Livingdocs/commit/014d5bf), [`362dc5b`](https://github.com/LivingDocs-Team/Livingdocs/commit/362dc5b).
- **Kiểm thử ghi nhận trong PR:** Mỗi PR chạy thành công 60 test Backend, bỏ qua `BackendApplicationTests.contextLoads` do schema PostgreSQL local thiếu cột `roles_permissions.roles_name`. #121 kiểm tra JAR ứng dụng không chứa test class hoặc thư viện test.

Xem [FR8](FR8.md) cho phạm vi hồi quy xác thực và phân quyền trước refactor.
