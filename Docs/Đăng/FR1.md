# FR-GH-01 Kết nối tài khoản GitHub

| Mục | Nội dung |
|---|---|
| Feature Jira | LD-22 GitHub Account Connection (epic LD-6 GitHub Integration) |
| Task đã làm | LD-53 (LD-54 Configure GitHub Connection, LD-55 Implement GitHub OAuth Connection, LD-56 Implement Connect & Disconnect, LD-57 Test GitHub Account Connection); LD-23: quay về frontend sau khi kết nối, xử lý khi người dùng bấm Cancel |
| Người thực hiện | Lê Hiền Hải Đăng |
| Thành phần | GitHub Integration Service (cổng 8082): `controller/GitHubConnectionController`, `service/GitHubConnectionService`, `client/GitHubClient`, `security/OAuthStateStore`, `security/TokenEncryptor`, `security/EncryptedStringConverter`, `entity/GitHubConnection` |
| Tác nhân | Developer (trang GitHub Connection của frontend, đi qua Backend BFF); GitHub (OAuth của GitHub App) |

## 1. Mô tả

Developer liên kết tài khoản GitHub với tài khoản LivingDocs qua một **GitHub App** (OAuth user-to-server), để hệ thống đọc được các repository mà Developer đã chọn khi cài app. Hệ thống lưu token GitHub ở dạng mã hoá, tự làm mới token sắp hết hạn, cho xem trạng thái kết nối và cho ngắt kết nối. Mỗi tài khoản LivingDocs có tối đa một kết nối GitHub.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-GH-01.1 | Tạo link kết nối cho người dùng hiện tại: `authorizeUrl` = `https://github.com/login/oauth/authorize?client_id=…&redirect_uri=…&state=…` và `installUrl` = `https://github.com/apps/<GITHUB_APP_SLUG>/installations/new?state=…` (dùng lần đầu để cài app và chọn repo). |
| FR-GH-01.2 | Mỗi lần tạo link sinh một `state` chống giả mạo: 24 byte ngẫu nhiên mã hoá Base64 URL-safe, gắn với người dùng, hiệu lực 10 phút, chỉ dùng được một lần. State giữ trong bộ nhớ của service. |
| FR-GH-01.3 | Callback `GET /api/github/callback?code=…&state=…`: kiểm tra `state` (sai, hết hạn hoặc đã dùng thì từ chối), đổi `code` lấy access token và refresh token, đọc tài khoản GitHub (`id`, `login`), tạo hoặc cập nhật kết nối của người dùng với trạng thái `ACTIVE`. |
| FR-GH-01.4 | Người dùng bấm Cancel trên GitHub (callback có `error` và không có `code`): báo lỗi `GITHUB_ACCESS_DENIED`, không tạo kết nối, không gọi GitHub. |
| FR-GH-01.5 | Có cấu hình `FRONTEND_URL`: callback chuyển trình duyệt (`302`) về `FRONTEND_URL?github=connected&login=<login>`; lỗi thì về `?github=error&reason=<mã lỗi>` (`BAD_REQUEST`, `GITHUB_ACCESS_DENIED`, `GITHUB_API_ERROR`). Không cấu hình thì trả JSON `{"message": "Kết nối GitHub thành công", "githubLogin": "<login>"}`. |
| FR-GH-01.6 | Access token và refresh token được mã hoá AES-256-GCM (IV 12 byte ngẫu nhiên cho mỗi lần mã hoá, tag 128 bit) trước khi ghi database. Không API nào trả token ra ngoài. Service không khởi động nếu `TOKEN_ENCRYPTION_KEY` thiếu, sai Base64 hoặc không đúng 32 byte. |
| FR-GH-01.7 | Xem trạng thái kết nối: `connected`, `githubLogin`, `status` (`ACTIVE`, `INVALID`, `REVOKED`, hoặc `NOT_CONNECTED` khi chưa từng kết nối), `connectedAt`, `tokenExpiresAt`. `connected = true` chỉ khi `status = ACTIVE`. |
| FR-GH-01.8 | Trước mọi lời gọi GitHub thay người dùng, lấy kết nối `ACTIVE` của người dùng; không có thì trả `409 GITHUB_NOT_CONNECTED`. Token còn dưới 5 phút là hết hạn thì tự làm mới bằng refresh token. Không có refresh token hoặc làm mới lỗi: kết nối chuyển `INVALID`, trả `401 GITHUB_REAUTH_REQUIRED`. |
| FR-GH-01.9 | Khi GitHub trả HTTP 401 cho token đang dùng (ví dụ lúc liệt kê hoặc đồng bộ repo), kết nối chuyển `INVALID` để giao diện nhắc người dùng kết nối lại GitHub. |
| FR-GH-01.10 | Ngắt kết nối: thu hồi quyền trên GitHub (`DELETE /applications/{client_id}/grant`; GitHub lỗi thì bỏ qua), xoá token đã lưu, đặt `REVOKED`, chuyển mọi repository của kết nối sang `DISCONNECTED`. Chưa kết nối mà ngắt thì trả `404`. |
| FR-GH-01.11 | Kết nối lại khi đã có kết nối: cập nhật chính bản ghi cũ của người dùng (`user_id` là duy nhất), không tạo bản ghi mới. |

## 3. API

Trình duyệt không gọi thẳng service: Backend (BFF) chuyển tiếp `/api/github/**` sang GitHub Integration Service, tự gắn header `X-User-Id` và mã nội bộ (xem [README](README.md)). Riêng callback do GitHub gọi thẳng vào service theo `GITHUB_REDIRECT_URI` (mặc định `http://localhost:8082/api/github/callback`).

| Method | Endpoint | Kết quả | Yêu cầu |
|---|---|---|---|
| GET | `/api/github/authorize-url` | `200` `{"authorizeUrl", "installUrl", "state"}` | FR-GH-01.1, 01.2 |
| GET | `/api/github/callback?code=&state=&error=` | `302` về frontend, hoặc `200` JSON khi không có `FRONTEND_URL` | FR-GH-01.3 – 01.5 |
| GET | `/api/github/connection` | `200` `{"connected", "githubLogin", "status", "connectedAt", "tokenExpiresAt"}` | FR-GH-01.7 |
| DELETE | `/api/github/connection` | `204` | FR-GH-01.10 |

Ví dụ `GET /api/github/connection`:

```json
{"connected": true, "githubLogin": "d3r-bbb", "status": "ACTIVE",
 "connectedAt": "2026-10-11T08:00:00Z", "tokenExpiresAt": "2026-10-11T16:00:00Z"}
```

Lời gọi GitHub dùng trong chức năng này: `POST https://github.com/login/oauth/access_token` (đổi code, làm mới token), `GET https://api.github.com/user`, `DELETE https://api.github.com/applications/{client_id}/grant`.

## 4. Dữ liệu

Bảng `github_connections` (Flyway `V1__init_github_integration.sql`), entity `GitHubConnection`:

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | UUID | khoá chính |
| `user_id` | VARCHAR(100), unique | id người dùng LivingDocs |
| `github_user_id` | BIGINT | id tài khoản GitHub |
| `github_login` | VARCHAR(100) | tên đăng nhập GitHub |
| `access_token`, `refresh_token` | VARCHAR(2048) | đã mã hoá AES-GCM (`EncryptedStringConverter`) |
| `access_token_expires_at` | timestamptz | null nếu GitHub không trả `expires_in` |
| `status` | VARCHAR(20) | `ACTIVE`, `INVALID` (token hỏng, cần kết nối lại), `REVOKED` (người dùng đã ngắt) |
| `created_at`, `updated_at` | timestamptz | gán tự động khi tạo và khi cập nhật |

## 5. Luồng chính

1. Developer mở trang GitHub Connection và bấm kết nối; frontend gọi `GET /api/github/authorize-url`.
2. Lần đầu mở `installUrl` để cài GitHub App và chọn repo; các lần sau mở `authorizeUrl`.
3. Developer bấm Authorize trên GitHub; GitHub chuyển trình duyệt về `/api/github/callback?code=…&state=…`.
4. Service kiểm tra `state`, đổi `code` lấy token, lưu kết nối `ACTIVE`, rồi chuyển về `FRONTEND_URL?github=connected&login=…`.
5. Trang GitHub Connection gọi `GET /api/github/connection` và hiện tài khoản đã kết nối.
6. Muốn ngắt: frontend gọi `DELETE /api/github/connection`.

## 6. Luồng lỗi

| Tình huống | Kết quả |
|---|---|
| Gọi thẳng service mà thiếu header `X-User-Id` | `400 BAD_REQUEST` |
| Callback thiếu `code` | `400 BAD_REQUEST`, "Thiếu tham số code từ GitHub." (có `FRONTEND_URL`: `reason=BAD_REQUEST`) |
| `state` sai, hết hạn hoặc đã dùng | `400 BAD_REQUEST`, "State không hợp lệ hoặc đã hết hạn. Hãy bấm 'Kết nối GitHub' lại từ đầu." |
| Bấm Cancel trên GitHub | `400 GITHUB_ACCESS_DENIED`, "Bạn chưa cho phép LivingDocs truy cập GitHub. Hãy bấm 'Kết nối GitHub' lại nếu muốn kết nối." (hoặc `reason=GITHUB_ACCESS_DENIED`) |
| GitHub lỗi khi đổi code hoặc đọc tài khoản | `502 GITHUB_API_ERROR` (hoặc `reason=GITHUB_API_ERROR`); thông báo không chứa nội dung GitHub trả về |
| Dùng chức năng cần GitHub khi chưa kết nối hoặc kết nối không còn `ACTIVE` | `409 GITHUB_NOT_CONNECTED` |
| Token hết hạn và không làm mới được | `401 GITHUB_REAUTH_REQUIRED`, kết nối chuyển `INVALID` |
| Ngắt kết nối khi chưa kết nối | `404 NOT_FOUND`, "Bạn chưa kết nối GitHub." |

## 7. Quy tắc nghiệp vụ

- Mỗi người dùng LivingDocs có tối đa một kết nối GitHub; kết nối lại thì thay kết nối cũ.
- Token GitHub chỉ nằm trong database ở dạng mã hoá và không bao giờ gửi về trình duyệt.
- Mỗi yêu cầu kết nối (`state`) chỉ dùng được một lần và hết hạn sau 10 phút.
- Ngắt kết nối không xoá repo khỏi workspace, chỉ chuyển repo sang `DISCONNECTED`.

## 8. Tiêu chí chấp nhận

- `authorizeUrl` chứa `client_id` và `state`; `installUrl` chứa `/apps/<GITHUB_APP_SLUG>/installations/new`.
- Callback hợp lệ tạo kết nối `ACTIVE`; token trong database khác token gốc; API trạng thái không trả token.
- Có `FRONTEND_URL` thì trình duyệt quay về frontend kèm kết quả trên URL; bấm Cancel thì về với `reason=GITHUB_ACCESS_DENIED`.
- Token còn dưới 5 phút được tự làm mới; làm mới thất bại thì kết nối `INVALID` và API trả `GITHUB_REAUTH_REQUIRED`.
- Ngắt kết nối thì `status = REVOKED`, `connected = false`, các repo của kết nối chuyển `DISCONNECTED`.

## 9. Kiểm thử

Test nằm trong `services/github-integration-service/src/test/java/com/livingdocs/github/`, chạy bằng `mvn verify` (job CI **GitHub Integration Service Test**).

| Test | Số test | Nội dung |
|---|---|---|
| `security/TokenEncryptorTest` | 5 | Mã hoá rồi giải mã ra đúng chuỗi gốc; cùng đầu vào cho hai bản mã khác nhau; `null` giữ nguyên; từ chối khoá sai độ dài; từ chối thiếu khoá |
| `security/OAuthStateStoreTest` | 3 | State chỉ dùng một lần; state lạ bị từ chối; state quá 10 phút bị từ chối |
| `controller/GitHubConnectionControllerTest` | 6 | Không có `FRONTEND_URL` thì trả JSON; thành công thì chuyển về frontend; state sai, GitHub lỗi, bấm Cancel thì chuyển về với đúng `reason`; bấm Cancel không gọi service |
| `GitHubIntegrationFlowTest` | 4 (dùng chung với FR-GH-02) | Cả luồng kết nối → xem trạng thái (không lộ token, token trong database đã mã hoá) → ngắt kết nối; callback với state giả bị `400`; thiếu `X-User-Id` bị `400`; GitHub trả 401 thì kết nối `INVALID` và API trả `GITHUB_REAUTH_REQUIRED` |
