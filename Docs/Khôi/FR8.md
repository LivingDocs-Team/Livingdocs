# FR-FE-08 Giao diện xác thực và quản lý người dùng

| Mục | Nội dung |
|---|---|
| Epic Jira | LD-286 Frontend Implementation |
| Task Jira | LD-292 [Authentication & User Interface] Implement Authentication & User Interface |
| Task đã làm | LD-293, LD-294, LD-295, LD-296, LD-297 |
| Người thực hiện | Khôi Nguyễn Hữu Đăng |
| Thành phần | Frontend LivingDocs Web: màn hình đăng ký, đăng nhập và đăng xuất, đăng nhập bằng GitHub, hồ sơ người dùng, tùy chọn thông báo |
| Tác nhân | Người dùng LivingDocs (đăng ký, đăng nhập, quản lý hồ sơ và thông báo), Backend (API xác thực, hồ sơ và tùy chọn thông báo), GitHub (đăng nhập OAuth) |

## 1. Mô tả

Hệ thống cung cấp giao diện web để người dùng đăng ký tài khoản, đăng nhập và đăng xuất, đăng nhập bằng tài khoản GitHub, xem và cập nhật hồ sơ cá nhân, và chọn các loại thông báo muốn nhận. Các trạng thái và lỗi liên quan đến xác thực được hiển thị rõ ràng cho người dùng.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-FE-08.1 | (LD-293) Có giao diện đăng ký với tên đăng nhập, email, họ, tên, mật khẩu và xác nhận mật khẩu. |
| FR-FE-08.2 | (LD-293) Kiểm tra mật khẩu và xác nhận mật khẩu trùng nhau trước khi gửi, và hiển thị lỗi xác thực dữ liệu do backend trả về. |
| FR-FE-08.3 | (LD-294) Có giao diện đăng nhập bằng email và mật khẩu; đăng nhập thành công thì hiển thị thông báo và vào ứng dụng. |
| FR-FE-08.4 | (LD-294) Có chức năng đăng xuất kết thúc phiên làm việc. |
| FR-FE-08.5 | (LD-294) Khôi phục phiên đăng nhập khi mở lại trang, và báo khi phiên hết hạn. |
| FR-FE-08.6 | (LD-295) Có nút "Continue with GitHub" đăng nhập bằng tài khoản GitHub; đăng nhập GitHub thất bại thì quay về trang đăng nhập kèm thông báo. |
| FR-FE-08.7 | (LD-296) Hiển thị và cho phép cập nhật hồ sơ: tên đăng nhập, họ và tên; email chỉ hiển thị, không sửa được. |
| FR-FE-08.8 | (LD-297) Hiển thị và cho phép lưu bốn tùy chọn thông báo: Email updates, Document changes, Review requests, System notifications. |
| FR-FE-08.9 | (LD-292) Hiển thị thông báo trạng thái xác thực và người dùng (thành công, lỗi, đang tải). |

## 3. Giao diện

| Màn hình / thành phần | Nội dung hiển thị | Yêu cầu |
|---|---|---|
| Đăng ký | Các ô nhập, nút tạo tài khoản, thông báo thành công hoặc lỗi | FR-FE-08.1 – 08.2 |
| Đăng nhập và đăng xuất | Ô email, mật khẩu, nút đăng nhập, nút đăng xuất, thông báo phiên hết hạn | FR-FE-08.3 – 08.5 |
| Đăng nhập GitHub | Nút "Continue with GitHub" | FR-FE-08.6 |
| Hồ sơ | Tên đăng nhập, họ, tên, email chỉ đọc, vai trò, nút lưu | FR-FE-08.7 |
| Tùy chọn thông báo | Bốn công tắc và nút lưu | FR-FE-08.8 |

Frontend gọi API của Backend cùng origin: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `GET` và `PATCH /api/profile`, `GET` và `PUT /api/profile/notification-preferences`, và chuyển hướng tới `/oauth2/authorization/github` để đăng nhập GitHub. Các yêu cầu ghi dùng mã CSRF của Backend.

## 4. Luồng chính

1. Người dùng đăng ký tài khoản; sau khi đăng ký thành công, người dùng đăng nhập bằng email và mật khẩu hoặc bằng tài khoản GitHub.
2. Sau khi đăng nhập, giao diện lưu phiên và hiển thị thông báo đăng nhập thành công.
3. Người dùng mở hồ sơ, sửa tên đăng nhập, họ và tên rồi lưu; mở tùy chọn thông báo, bật hoặc tắt từng loại rồi lưu.
4. Người dùng đăng xuất; phiên kết thúc và giao diện quay về màn hình đăng nhập.

## 5. Luồng lỗi

| Trường hợp | Kết quả hiển thị |
|---|---|
| Mật khẩu và xác nhận mật khẩu khác nhau | "Passwords do not match.", không gửi yêu cầu |
| Tên đăng nhập hoặc email đã được đăng ký | "That username or email is already registered." |
| Dữ liệu đăng ký không hợp lệ | Hiển thị các lỗi xác thực do backend trả về |
| Sai email hoặc mật khẩu | "Invalid email or password." |
| Backend trả phản hồi đăng nhập không hợp lệ | "The backend returned an invalid login response." |
| Không kết nối được backend | Thông báo không kết nối được backend (đăng ký, đăng nhập, đăng xuất) |
| Đăng xuất thất bại | "Could not sign out. Please retry." và giữ người dùng ở trạng thái đã đăng nhập |
| Phiên hết hạn | "Your LivingDocs session has expired. Please sign in again." và quay về đăng nhập |
| Đăng nhập GitHub thất bại | Quay về đăng nhập với gợi ý đăng nhập bằng mật khẩu rồi kết nối GitHub trong mục GitHub Connection |
| Tên đăng nhập đã được dùng khi cập nhật hồ sơ | Hiển thị lỗi trả về từ backend, giữ dữ liệu đang nhập |
| Không tải hoặc không lưu được hồ sơ, tùy chọn thông báo | Hiển thị thông báo lỗi tương ứng |

## 6. Quy tắc nghiệp vụ

- Frontend không lưu mật khẩu hay thông tin xác thực GitHub; phiên do Backend quản lý bằng cookie và mã CSRF.
- Email là tên đăng nhập, không sửa được trong hồ sơ; vai trò hiển thị chỉ đọc và do Administrator gán.
- Đăng ký chỉ tạo tài khoản Developer.
- Giới hạn trường hồ sơ theo backend: tên đăng nhập 1 đến 50 ký tự, họ và tên mỗi trường tối đa 100 ký tự.
- Ghi chú: ở các nhánh sau, đăng ký, đăng nhập và đăng xuất được đặt trên các màn hình công khai Home, Login, Register, còn hồ sơ và tùy chọn thông báo nằm trong menu Account Management sau khi đăng nhập (xem FRCREATEINTERFACE).

## 7. Tiêu chí chấp nhận

- **AC-FE-08.1:** Đăng ký hợp lệ tạo được tài khoản và hiển thị thông báo thành công; dữ liệu sai hoặc trùng hiển thị lỗi tương ứng.
- **AC-FE-08.2:** Đăng nhập đúng vào được ứng dụng; đăng nhập sai hiển thị lỗi, không vào ứng dụng.
- **AC-FE-08.3:** Mở lại trang khi còn phiên thì vẫn ở trạng thái đã đăng nhập; phiên hết hạn thì quay về đăng nhập kèm thông báo.
- **AC-FE-08.4:** Đăng xuất kết thúc phiên và quay về màn hình đăng nhập.
- **AC-FE-08.5:** Đăng nhập GitHub thành công vào được ứng dụng; thất bại hiển thị thông báo hướng dẫn.
- **AC-FE-08.6:** Cập nhật hồ sơ và tùy chọn thông báo được lưu và hiển thị lại đúng sau khi tải lại.

## 8. Kiểm thử

Kiểm thử theo các tiêu chí chấp nhận ở mục 7 trên giao diện web, kèm các kịch bản Playwright trong `tests/test_frontend.py` (đăng nhập, quay về từ lỗi GitHub OAuth) và `tests/test_profile_preferences.py` (tải và lưu hồ sơ, tên đăng nhập bị trùng, tải và lưu tùy chọn thông báo). Jira ghi nhận LD-292 hoàn thành ngày 11/10/2026; mã nguồn được merge qua pull request #6 trên GitHub.
