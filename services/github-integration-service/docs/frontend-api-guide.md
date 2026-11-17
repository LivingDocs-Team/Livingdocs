# Gọi API GitHub Integration từ frontend (cho Khôi)

Browser APIs go through the Backend BFF at `/api/...`. GitHub Integration listens on `8082` for
the GitHub OAuth callback and internal Backend requests; browser requests must not call it directly.

## 1. Địa chỉ gọi API

| Frontend chạy bằng | Gọi tới | Cần làm gì |
|---|---|---|
| `npm run dev` (cổng 5173) | đường dẫn tương đối `/api/...` | Proxy của Vite chuyển tiếp, sửa `vite.config.js` như bên dưới |
| Docker Compose (cổng 3000) | đường dẫn tương đối `/api/...` | Nginx frontend proxy chuyển tiếp tới Backend (8080) |

`vite.config.js`: mọi request `/api` đi qua Backend (8080), nơi xác minh session rồi proxy các API tích hợp:

```js
server: {
  proxy: {
    '/api': 'http://localhost:8080',
  },
},
```

Frontend development origins được giới hạn trong allowlist CORS của Backend. CORS không được dùng để xác thực người dùng.

## 2. Hàm gọi API dùng chung

Frontend gửi session cookie tới Backend bằng `credentials: 'include'`. Backend lấy user ID từ principal đã xác thực, thay thế mọi `X-User-Id`/Authorization do browser gửi, rồi dùng `GITHUB_INTEGRATION_INTERNAL_SECRET` để xác thực với GitHub Integration. Frontend không được tự gửi `X-User-Id`.

```js
const GITHUB_API = import.meta.env.VITE_API_BASE_URL || '';

export async function githubApi(path, { method = 'GET', body } = {}) {
  const res = await fetch(`${GITHUB_API}${path}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // Lỗi luôn có dạng { status, code, message, timestamp }
    const error = new Error(data.message || `HTTP ${res.status}`);
    error.code = data.code;
    error.status = res.status;
    error.retryAfter = res.headers.get('Retry-After'); // số giây, chỉ có khi 429
    throw error;
  }
  return data;
}
```

## 3. Màn hình "Kết nối GitHub"

| Việc | API | Kết quả |
|---|---|---|
| Xem trạng thái | `GET /api/github/connection` | `{ connected, githubLogin, status, connectedAt, tokenExpiresAt }`; `status`: `ACTIVE`, `INVALID` (cần kết nối lại), `REVOKED`, `NOT_CONNECTED` |
| Bấm "Kết nối GitHub" | `GET /api/github/authorize-url` | `{ authorizeUrl, installUrl, state }` |
| Ngắt kết nối | `DELETE /api/github/connection` | `204` |

Khi bấm "Kết nối GitHub":

```js
const { authorizeUrl, installUrl } = await githubApi('/api/github/authorize-url');
// Lần đầu (chưa cài GitHub App, chưa chọn repo) dùng installUrl; đã cài rồi thì dùng authorizeUrl
window.location.href = installUrl;
```

Người dùng cho phép trên GitHub xong, GitHub gọi về service (`/api/github/callback`). Nếu service có cấu hình **`FRONTEND_URL`** (ví dụ `http://localhost:5173` khi dev, `http://localhost:3000` khi chạy Docker), người dùng được chuyển về trang đó kèm kết quả trên URL:

| URL quay về | Ý nghĩa |
|---|---|
| `?github=connected&login=d3r-bbb` | Kết nối thành công |
| `?github=error&reason=GITHUB_ACCESS_DENIED` | Người dùng bấm Cancel trên GitHub |
| `?github=error&reason=BAD_REQUEST` | Link đã hết hạn (quá 10 phút) hoặc bị dùng lại, bấm kết nối lại |
| `?github=error&reason=GITHUB_API_ERROR` | GitHub lỗi khi đổi mã, thử lại |

```js
const params = new URLSearchParams(window.location.search);
if (params.get('github') === 'connected') { /* báo thành công, tải lại trạng thái */ }
if (params.get('github') === 'error') { /* báo lỗi theo params.get('reason') */ }
```

Không cấu hình `FRONTEND_URL` thì callback trả JSON `"Kết nối GitHub thành công"`; callback vẫn chỉ hoàn tất state dùng một lần đã được tạo từ authorize request qua Backend BFF. Swagger UI của service không mở cho browser.

## 4. Màn hình "Repository"

`workspaceId` hiện là workspace cá nhân duy nhất `ws-${userId}`. Backend lấy `${userId}` từ session; GitHub Integration kiểm tra lại workspace ID và chỉ liệt kê repository thuộc connection của user đó.

| Việc | API | Body / kết quả |
|---|---|---|
| Repo có thể thêm | `GET /api/github/repos/available` | `[{ githubRepoId, fullName, privateRepo, defaultBranch, htmlUrl }]` |
| Thêm repo | `POST /api/workspaces/{workspaceId}/repositories` | body `{ "githubRepoIds": [123, 456] }`, trả `201` + danh sách repo vừa thêm (thêm trùng thì bỏ qua) |
| Danh sách repo | `GET /api/workspaces/{workspaceId}/repositories` | `[{ id, workspaceId, githubRepoId, fullName, defaultBranch, privateRepo, htmlUrl, status, lastSyncedAt, createdAt }]` |
| Chi tiết repo | `GET /api/repositories/{id}` | như trên, 1 repo |
| Đồng bộ | `POST /api/repositories/{id}/sync` | body không bắt buộc, ví dụ `{ "branch": "develop" }`; trả kết quả như `docs/samples/sync-api-response.sample.json` |
| Kết quả đồng bộ gần nhất | `GET /api/repositories/{id}/sync/latest` | như trên; `404` nếu chưa đồng bộ lần nào |
| Gỡ repo | `DELETE /api/repositories/{id}` | `204` |

- `status` của repo: `CONNECTED`, `SYNCING` (đang đồng bộ), `ERROR` (repo bị xoá hoặc mất quyền), `DISCONNECTED` (đã ngắt kết nối GitHub).
- Đồng bộ repo khoảng 100 file mất 10–30 giây: hiện vòng xoay và khoá nút "Đồng bộ" trong lúc chờ.
- Màn hình chỉ cần danh sách file thì gửi `{ "includeContent": false }` cho nhanh.

## 5. Xử lý lỗi

| `code` | HTTP | Hiển thị |
|---|---|---|
| `GITHUB_NOT_CONNECTED` | 409 | Nút "Kết nối GitHub" |
| `GITHUB_REAUTH_REQUIRED`, `TOKEN_INVALID` | 401 | Nút "Kết nối lại GitHub" |
| `ACCESS_DENIED` | 403 | "GitHub App chưa được cấp quyền cho repo này", kèm link `installUrl` |
| `FORBIDDEN` | 403 | "Repo này không thuộc tài khoản của bạn" |
| `REPOSITORY_NOT_FOUND` | 404 | Gợi ý gỡ repo khỏi workspace |
| `BRANCH_NOT_FOUND` | 404 | Cho chọn nhánh khác |
| `NOT_FOUND` | 404 | Repo không còn trong workspace, hoặc chưa đồng bộ lần nào (`/sync/latest`) |
| `EMPTY_REPOSITORY` | 409 | "Repo trống, chưa có gì để đồng bộ" |
| `RATE_LIMITED` | 429 | "Thử lại sau X phút", X lấy từ `error.retryAfter` |
| `GITHUB_UNAVAILABLE` | 503 | Nút "Thử lại" |
| `GITHUB_API_ERROR` | 502 | "GitHub đang lỗi, thử lại sau" (khi liệt kê repo) |
| `BAD_REQUEST`, `VALIDATION_ERROR`, `INVALID_REQUEST` | 400 | Hiện `message` |

Response lỗi thật của từng mã: `docs/samples/sync-errors.sample.json`. Chi tiết: mục 4 của [repository-sync-contract.md](repository-sync-contract.md).
