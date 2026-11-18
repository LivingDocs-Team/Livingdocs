# FR-AUTH-UI — Tích hợp đăng ký và đăng nhập trên frontend

| Mục | Nội dung |
|---|---|
| Story / Task Jira | [LD-389](https://ut-team-lvdocs.atlassian.net/browse/LD-389) |
| Trạng thái Jira (18/11/2026) | Done |
| Người thực hiện | Nhân Nguyễn ([nhanndt750402-max](https://github.com/nhanndt750402-max), đối chiếu theo PR và commit) |
| Thành phần | Frontend, Backend Auth |
| Tác nhân | Người dùng chưa đăng nhập |
| Phụ thuộc | [Yêu cầu xác thực chung](../Huy/FR01.md) |
| Mục tiêu | Hoàn tất đăng ký và đăng nhập bằng biểu mẫu web. |

## 1. Mô tả

Form email và mật khẩu gọi API Backend và sử dụng cookie phiên. Phạm vi bao gồm tích hợp form, phản hồi trên giao diện và CORS cho môi trường phát triển.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AUTH-UI.1 | Gửi dữ liệu đăng ký từ form đến Backend. |
| FR-AUTH-UI.2 | Gửi thông tin đăng nhập và cho phép trình duyệt dùng cookie phiên. |
| FR-AUTH-UI.3 | Hiển thị trạng thái đang gửi và thông báo lỗi từ API. |
| FR-AUTH-UI.4 | Cho phép preflight từ frontend local theo cấu hình CORS. |

## 3. API và luồng xử lý

Form đăng ký gọi `POST /api/auth/register`. Form đăng nhập gọi `POST /api/auth/login`. Giao diện cập nhật theo phản hồi của từng API.

## 4. Luồng lỗi

Đăng ký trùng trả `409`; dữ liệu đăng ký không hợp lệ trả `400`. Giao diện báo lỗi khi API từ chối đăng nhập.

## 5. Tiêu chí chấp nhận

- **AC-AUTH-UI.1:** Đăng ký hợp lệ trả `201`.
- **AC-AUTH-UI.2:** Đăng ký trùng hoặc sai dữ liệu hiển thị lỗi tương ứng.
- **AC-AUTH-UI.3:** Đăng nhập hợp lệ thiết lập phiên để trình duyệt tiếp tục sử dụng.

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#34](https://github.com/LivingDocs-Team/Livingdocs/pull/34) · [`78096bd`](https://github.com/LivingDocs-Team/Livingdocs/commit/78096bd).
- **Kiểm thử ghi nhận trong PR:** PR ghi nhận ESLint và build Vite thành công, cùng 3 test controller đăng ký cho 201, 409 và 400. Kiểm thử trình duyệt với backend đang chạy chưa được thực hiện trong PR này.
