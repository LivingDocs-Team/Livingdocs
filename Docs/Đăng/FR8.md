# FR-USR-01 Hồ sơ người dùng và tùy chọn thông báo

| Mục | Nội dung |
|---|---|
| Feature Jira | epic LD-5 Authentication & User Management |
| Task đã làm | LD-48 (LD-49 Get User Profile, LD-50 Update User Profile, LD-51 Manage Notification Preferences, LD-52 Test Profile & Preferences); PR #123 |
| Người thực hiện | Lê Hiền Hải Đăng. Màn hình demo `Profile.jsx`, `NotificationPreferences.jsx` có từ LD-292; LD-48 nối hai màn hình này với backend |
| Thành phần | Backend (cổng 8080): `controller/ProfileController`, entity `User` (3 cột tùy chọn thông báo mới). Frontend: `Profile.jsx`, `NotificationPreferences.jsx`, nút **Profile** và **Notifications** trên thanh menu |
| Tác nhân | Người dùng đã đăng nhập (bằng email và mật khẩu, hoặc bằng GitHub) |
| Phụ thuộc | FR-AUTH-01 của Huy (đăng ký, đăng nhập bằng email hoặc GitHub, phiên làm việc) |

## 1. Mô tả

Người dùng đang đăng nhập xem và sửa hồ sơ của chính mình (username, họ, tên), và chọn loại thông báo muốn nhận. Backend chỉ làm việc với tài khoản của phiên hiện tại, kiểm tra dữ liệu trước khi lưu, không cho đổi email, vai trò hay mật khẩu qua chức năng này. Tùy chọn thông báo được lưu cùng tài khoản để các chức năng gửi thông báo đọc khi cần.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-USR-01.1 | Chỉ người đã đăng nhập mới dùng được: chưa có phiên thì `401`. Người dùng được xác định từ phiên: đăng nhập bằng email thì theo email, đăng nhập bằng GitHub thì theo GitHub id. Tài khoản không còn tồn tại thì `401`. |
| FR-USR-01.2 | **LD-49, xem hồ sơ.** `GET /api/profile` trả `id`, `username`, `email`, `firstName`, `lastName`, `role`; không bao giờ trả mật khẩu. |
| FR-USR-01.3 | **LD-50, sửa hồ sơ.** `PATCH /api/profile` sửa `username`, `firstName`, `lastName`; trường nào không gửi (null) thì giữ nguyên; giá trị được bỏ khoảng trắng hai đầu. |
| FR-USR-01.4 | Kiểm tra: `username` 1–50 ký tự; `firstName`, `lastName` 1–100 ký tự; sai thì `400 PROFILE_INVALID` kèm thông báo rõ trường nào. `username` đã thuộc người khác (không phân biệt hoa thường) thì `409 USERNAME_TAKEN`. Body rỗng thì `400 PROFILE_INVALID`. Có một trường sai thì **không lưu trường nào**. |
| FR-USR-01.5 | Email là tên đăng nhập nên không đổi được ở đây (đổi email làm phiên hiện tại mất hiệu lực); quản trị viên đổi qua `/api/admin/users`. `role` và `password` không có trong request, gửi kèm cũng bị bỏ qua. |
| FR-USR-01.6 | **LD-51, tùy chọn thông báo.** `GET /api/profile/notification-preferences` trả 4 tùy chọn: `emailUpdates`, `documentChanges`, `reviewRequests`, `systemNotifications`. Tài khoản mới bật cả 4; tài khoản có sẵn giữ lựa chọn cũ của `emailUpdates` và có 3 tùy chọn còn lại bật. |
| FR-USR-01.7 | `PUT /api/profile/notification-preferences` thay cả 4 tùy chọn cùng lúc; thiếu một tùy chọn (hoặc null) thì `400 PREFERENCES_INVALID`, không lưu gì. |
| FR-USR-01.8 | Yêu cầu sửa (`PATCH`, `PUT`) phải có CSRF token hợp lệ (header `X-XSRF-TOKEN`), thiếu thì `403`. |
| FR-USR-01.9 | Frontend: trang **User Profile** tải hồ sơ, cho sửa username, họ, tên; email hiện ở dạng chỉ đọc kèm vai trò; bấm **Save changes** thì lưu và báo "Profile saved.", lỗi thì hiện thông báo của backend (ví dụ "Username is already in use."). Trang **Notification Preferences** tải 4 tùy chọn (Email updates, Document changes, Review requests, System notifications), bấm **Save preferences** thì lưu và báo "Preferences saved.". Nút bị khoá trong lúc lưu. |

## 3. API

Trình duyệt gọi thẳng Backend (cookie phiên `JSESSIONID`, header `X-XSRF-TOKEN` cho yêu cầu sửa).

| Method | Endpoint | Body | Kết quả | Yêu cầu |
|---|---|---|---|---|
| GET | `/api/profile` | | `200` hồ sơ | FR-USR-01.1, 01.2 |
| PATCH | `/api/profile` | `{"username": "dang-le", "firstName": "Le Hien Hai", "lastName": "Dang"}` (trường nào cũng không bắt buộc) | `200` hồ sơ sau khi sửa | FR-USR-01.3 – 01.5, 01.8 |
| GET | `/api/profile/notification-preferences` | | `200` 4 tùy chọn | FR-USR-01.6 |
| PUT | `/api/profile/notification-preferences` | `{"emailUpdates": false, "documentChanges": true, "reviewRequests": true, "systemNotifications": true}` (bắt buộc cả 4) | `200` tùy chọn sau khi lưu | FR-USR-01.7, 01.8 |

Ví dụ:

```json
{"id": 7, "username": "dang", "email": "dang@example.test", "firstName": "Hai", "lastName": "Dang", "role": "DEVELOPER"}

{"status": 409, "code": "USERNAME_TAKEN", "message": "Username is already in use."}
```

## 4. Dữ liệu

Bảng `users` của Backend (Hibernate `ddl-auto=update` tự thêm cột khi khởi động):

| Cột | Tùy chọn | Ghi chú |
|---|---|---|
| `notification_enabled` (có sẵn) | `emailUpdates` | Giữ nguyên giá trị người dùng đã chọn |
| `notify_document_changes` | `documentChanges` | Mới, `boolean NOT NULL DEFAULT true` |
| `notify_review_requests` | `reviewRequests` | Mới, `boolean NOT NULL DEFAULT true` |
| `notify_system` | `systemNotifications` | Mới, `boolean NOT NULL DEFAULT true` |

`username` (≤ 50, duy nhất), `first_name`, `last_name` là cột có sẵn. Đã kiểm tra trên PostgreSQL 18: database có sẵn người dùng thêm được 3 cột mới, người dùng cũ giữ `notification_enabled` của mình và có 3 tùy chọn mới đều bật.

## 5. Luồng chính

1. Người dùng đã đăng nhập bấm **Profile** trên thanh menu; frontend gọi `GET /api/profile` và điền form.
2. Người dùng sửa username, họ hoặc tên, bấm **Save changes**; frontend lấy CSRF token rồi gọi `PATCH /api/profile`.
3. Backend xác định người dùng từ phiên, kiểm tra cả ba trường, kiểm tra username không trùng, lưu, trả hồ sơ mới; frontend báo "Profile saved.".
4. Người dùng bấm **Notifications**; frontend gọi `GET /api/profile/notification-preferences` và hiện 4 ô chọn.
5. Người dùng đổi tùy chọn, bấm **Save preferences**; frontend gọi `PUT` với cả 4 giá trị; backend lưu và trả lại; frontend báo "Preferences saved.".

## 6. Luồng lỗi

Lỗi trả JSON `{"status", "code", "message"}`; thông báo bằng tiếng Anh và được frontend hiện nguyên văn.

| Mã | HTTP | Khi nào | Thông báo |
|---|---|---|---|
| `PROFILE_INVALID` | 400 | Body rỗng; username rỗng hoặc dài hơn 50; họ hoặc tên rỗng hoặc dài hơn 100 | "Request body is required." / "Username must contain 1 to 50 characters." / "First name must contain 1 to 100 characters." / "Last name must contain 1 to 100 characters." |
| `USERNAME_TAKEN` | 409 | Username đã thuộc người khác | "Username is already in use." |
| `PREFERENCES_INVALID` | 400 | Thiếu một trong 4 tùy chọn | "emailUpdates, documentChanges, reviewRequests and systemNotifications are required." |
| | 401 | Chưa đăng nhập, phiên hết hạn, tài khoản không còn | Frontend chuyển về màn hình đăng nhập |
| | 403 | Thiếu hoặc sai CSRF token | |

## 7. Quy tắc nghiệp vụ

- Người dùng chỉ xem và sửa hồ sơ của chính mình; không có tham số id nào trong API.
- Không đổi email, vai trò, mật khẩu qua chức năng này.
- Dữ liệu được kiểm tra toàn bộ trước khi lưu; lỗi một trường thì không lưu gì.
- Tùy chọn thông báo mặc định bật; thêm loại thông báo mới không làm tắt thông báo của người dùng cũ.

## 8. Tiêu chí chấp nhận

- Người dùng đăng nhập bằng email hoặc GitHub xem được hồ sơ của mình, không có mật khẩu trong response.
- Sửa username và tên thì lưu đúng giá trị đã bỏ khoảng trắng; email và vai trò không đổi, kể cả khi request gửi kèm `email`, `role`.
- Username trùng người khác: `409`, không lưu; trường không hợp lệ: `400`, không lưu.
- Tài khoản mới có cả 4 tùy chọn thông báo bật; lưu rồi đọc lại đúng giá trị đã lưu; thiếu một tùy chọn: `400`, không lưu.
- Chưa đăng nhập: `401`; thiếu CSRF: `403`.

## 9. Kiểm thử

Test Backend nằm trong `backend/src/main/tests/java/com/cnpm/backend/`, chạy bằng `./backend/mvnw -f backend/pom.xml verify` (job CI **Backend Build and Test**, PostgreSQL 18). Test giao diện chạy trong job **Frontend E2E Test**.

| Test | Số test | Nội dung |
|---|---|---|
| `ProfileControllerTest` | 8 | `UserRepository` giả: xem hồ sơ không có mật khẩu; người dùng GitHub được tìm theo GitHub id; không có phiên hoặc tài khoản thì `401`; sửa bỏ khoảng trắng, giữ trường không gửi, không đổi email và vai trò; trường sai bị từ chối và không lưu gì; username của người khác bị từ chối; tùy chọn mặc định bật, lưu và đọc lại đúng; thiếu tùy chọn bị từ chối và không lưu gì |
| `security/BackendSecurityFilterChainTest` (1 test mới) | 1 | Cấu hình bảo mật thật: chưa đăng nhập `401`; đã đăng nhập xem được hồ sơ, không có mật khẩu; `PATCH` thiếu CSRF `403`; có CSRF thì lưu được, gửi kèm `email`, `role` cũng không đổi |
| `tests/test_profile_preferences.py` | 3 | Playwright, backend giả: tải và lưu hồ sơ (email chỉ đọc, gửi CSRF token); username trùng hiện thông báo lỗi; tải và lưu tùy chọn thông báo |
