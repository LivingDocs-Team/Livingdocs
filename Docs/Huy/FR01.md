# FR-AUTH-01 User Registration, Login & GitHub OAuth Connection

| Mục | Nội dung |
| :--- | :--- |
| **Story Jira** | LD-20 User Registration, LD-38 Login/Logout, LD-43 GitHub OAuth Authentication |
| **Task đã làm** | LD-53 GitHub Account Connection, LD-63 Repository Synchronization, LD-292 Auth UI |
| **Người thực hiện** | Lâm Gia Huy |
| **Thành phần** | Backend API (`app/auth`, `app/github`), Frontend UI (`src/pages/auth`, `src/pages/repo`) |
| **Tác nhân** | GitHub OAuth Gateway |

---

## 1. Mô tả
Hệ thống cho phép người dùng đăng ký, đăng nhập tài khoản bằng email/mật khẩu hoặc thông qua tài khoản GitHub (OAuth2). Sau khi xác thực, người dùng có thể kết nối danh sách GitHub Repository của họ vào workspace LivingDocs và kích hoạt đồng bộ hóa dữ liệu mã nguồn.

---

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
| :--- | :--- |
| **FR-AUTH-01.1** | Cho phép đăng ký/đăng nhập bằng Email và Password hợp lệ với mật khẩu tối thiểu 8 ký tự. |
| **FR-AUTH-01.2** | Hỗ trợ đăng nhập nhanh thông qua GitHub OAuth2 authorization code flow. |
| **FR-AUTH-01.3** | Trả về cặp JWT Token (`access_token` thời hạn 30 phút, `refresh_token` 7 ngày) sau khi xác thực thành công. |
| **FR-AUTH-01.4** | Cho phép người dùng kết nối tài khoản GitHub và cấp quyền truy cập danh sách Repository (`repo` scope). |
| **FR-AUTH-01.5** | Hiển thị danh sách các Repository đã kết nối kèm theo thông tin branch mặc định, ngôn ngữ chính và thời gian đồng bộ cuối. |
| **FR-AUTH-01.6** | Cho phép người dùng gửi yêu cầu đồng bộ lại (Re-sync) cấu trúc Repository thủ công bất kỳ lúc nào. |

---

## 3. API

| Method | Endpoint | Kết quả | Yêu cầu |
| :--- | :--- | :--- | :--- |
| **POST** | `/api/v1/auth/register` | `201 Created` + User Object | FR-AUTH-01.1 |
| **POST** | `/api/v1/auth/login` | `200 OK` + JWT Tokens | FR-AUTH-01.1 |
| **GET** | `/api/v1/auth/github/url` | `200 OK` + Auth Redirect URL | FR-AUTH-01.2 |
| **POST** | `/api/v1/auth/github/callback` | `200 OK` + JWT Tokens | FR-AUTH-01.2, 01.3 |
| **GET** | `/api/v1/repositories` | `200 OK` + List[Repo] | FR-AUTH-01.5 |
| **POST** | `/api/v1/repositories/{id}/sync` | `202 Accepted` + Sync Job ID | FR-AUTH-01.6 |

Ví dụ body `/api/v1/auth/github/callback`:
```json
{
  "code": "8c2f1e0a4b91238f12a3",
  "state": "livingdocs_secure_state_string"
}
```

---

## 4. Luồng chính
1. Người dùng bấm chọn **"Sign in with GitHub"** trên giao diện Frontend.
2. Frontend chuyển hướng người dùng đến trang ủy quyền của GitHub OAuth Gateway.
3. Người dùng xác nhận cấp quyền; GitHub redirect về ứng dụng kèm query parameter `code`.
4. Frontend gửi `code` tới API `/api/v1/auth/github/callback`.
5. Backend trao đổi `code` lấy `access_token` từ GitHub, lưu thông tin User và phát hành cặp JWT Token cho ứng dụng.
6. Người dùng chọn Repository cần làm việc và nhấn nút **"Connect Repository"**.
7. Hệ thống tiến hành cào danh sách nhánh và cấu trúc thư mục ban đầu.

---

## 5. Luồng lỗi

| Trường hợp | HTTP | Kết quả |
| :--- | :--- | :--- |
| Email hoặc Mật khẩu không đúng | `401` | `{"detail": "Invalid credentials"}` |
| GitHub Auth Code bị hết hạn hoặc sai | `400` | `{"detail": "Invalid OAuth code"}` |
| GitHub Access Token bị thu hồi bởi user | `403` | `{"detail": "GitHub integration revoked. Please re-authenticate"}` |
| Repository không tồn tại hoặc mất quyền | `404` | `{"detail": "Repository not found or access denied"}` |

---

## 6. Quy tắc nghiệp vụ
* Mọi Token xác thực GitHub của người dùng phải được mã hóa trước khi lưu trữ dưới CSDL (dùng AES-256).
* Nếu kết nối Webhook hoặc OAuth Token bị thất bại trong 3 lần thử lại, hệ thống tự động đổi trạng thái kết nối sang `requires_reauth` và thông báo cho người dùng.

---

## 7. Tiêu chí chấp nhận
* **AC-AUTH-01.1:** Người dùng đăng nhập thành công qua GitHub nhận được JWT Token hợp lệ trong < 2 giây.
* **AC-AUTH-01.2:** Danh sách Repository kết nối hiển thị đầy đủ thông tin branch mặc định và thời điểm sync gần nhất.
* **AC-AUTH-01.3:** Nút Re-sync hiển thị trạng thái `syncing` và khóa tương tác cho đến khi tiến trình hoàn tất.

---

## 8. Kiểm thử
* `backend/tests/test_auth_api.py`
* `backend/tests/test_github_integration.py`
