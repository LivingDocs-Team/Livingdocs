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

### Hợp đồng biểu mẫu và API

| Thao tác | JSON gửi từ frontend | Phản hồi thành công |
|---|---|---|
| `POST /api/auth/register` | `username`, `email`, `password`, `firstName`, `lastName` | `201`, hiển thị thông báo đăng ký thành công. |
| `POST /api/auth/login` | `email`, `password` | `200`, trình duyệt nhận cookie phiên. JSON gồm `message`, `id`, `email`, `username`, `firstName`, `lastName`, `role`. |

- **FR-AUTH-UI.5 — Validate đăng ký.** Kiểm tra hai ô mật khẩu khớp trước khi gửi. Chỉ gửi năm trường trong bảng. Backend yêu cầu username 3–50 ký tự, email hợp lệ tối đa 255 ký tự, mật khẩu 6–255 ký tự và cả hai phần tên có giá trị.
- **FR-AUTH-UI.6 — Validate đăng nhập.** Email hợp lệ và mật khẩu có giá trị. Backend chuẩn hóa email bằng cách bỏ khoảng trắng đầu/cuối và chuyển chữ thường, rồi xác thực mật khẩu. Sai thông tin trả `401` với thông báo chung.
- **FR-AUTH-UI.7 — Quản lý lần gửi.** Gửi JSON với `credentials: 'include'` và header CSRF theo cấu hình hiện hành. Giữ trạng thái đang gửi trong lúc chờ phản hồi, đọc thông báo lỗi từ API khi có, hiển thị thông báo kết nối riêng khi không gọi được Backend, và đặt lại trạng thái gửi cả khi thành công lẫn thất bại.

## 4. Luồng lỗi

Đăng ký trùng trả `409`; dữ liệu đăng ký không hợp lệ trả `400`. Giao diện báo lỗi khi API từ chối đăng nhập.

## 5. Tiêu chí chấp nhận

- **AC-AUTH-UI.1:** Đăng ký hợp lệ trả `201`.
- **AC-AUTH-UI.2:** Đăng ký trùng hoặc sai dữ liệu hiển thị lỗi tương ứng.
- **AC-AUTH-UI.3:** Đăng nhập hợp lệ thiết lập phiên để trình duyệt tiếp tục sử dụng.

| Ca chấp nhận | Thao tác | Kết quả quan sát |
|---|---|---|
| AC-AUTH-UI.4 | Nhập mật khẩu xác nhận khác mật khẩu. | Form báo lỗi và chưa gọi API. |
| AC-AUTH-UI.5 | Gửi lại email hoặc username đã đăng ký. | API trả `409`, form báo trùng và cho sửa rồi thử lại. |
| AC-AUTH-UI.6 | Đăng nhập đúng với email có chữ hoa trên form, rồi đọc `GET /api/auth/me` bằng cùng phiên. | `/me` trả danh tính tương ứng. Thử với mật khẩu sai trả `401`. |

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#34](https://github.com/LivingDocs-Team/Livingdocs/pull/34) · [`78096bd`](https://github.com/LivingDocs-Team/Livingdocs/commit/78096bd).
- **Kiểm thử ghi nhận trong PR:** PR ghi nhận ESLint và build Vite thành công, cùng 3 test controller đăng ký cho 201, 409 và 400. Kiểm thử trình duyệt với backend đang chạy chưa được thực hiện trong PR này.
