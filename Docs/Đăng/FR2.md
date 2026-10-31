# FR-GH-02 Quản lý repository trong workspace

| Mục | Nội dung |
|---|---|
| Feature Jira | LD-23 Repository Management (epic LD-6 GitHub Integration) |
| Task đã làm | LD-58 (LD-59 List Available GitHub Repositories, LD-60 Select Repository for Workspace, LD-61 Manage Connected Repositories, LD-62 Test Repository Management); LD-23 |
| Người thực hiện | Lê Hiền Hải Đăng |
| Thành phần | GitHub Integration Service (cổng 8082): `controller/RepositoryController`, `service/RepositoryManagementService`, `client/GitHubClient`, `entity/ConnectedRepository`, `repository/ConnectedRepositoryRepository` |
| Tác nhân | Developer (trang Repository Management của frontend, đi qua Backend BFF); GitHub (danh sách repo mà GitHub App được cấp quyền) |
| Phụ thuộc | FR-GH-01 (cần kết nối GitHub `ACTIVE`) |

## 1. Mô tả

Developer đã kết nối GitHub chọn các repository mà GitHub App được cấp quyền để đưa vào workspace của mình trong LivingDocs, xem danh sách và chi tiết các repo đã thêm, và gỡ repo khỏi workspace. Chỉ repo đã thêm vào workspace mới được đồng bộ (FR-GH-03) và sinh tài liệu. Mỗi người dùng có một workspace cá nhân `ws-{userId}`.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-GH-02.1 | Liệt kê các repo mà GitHub App được cấp quyền: lấy mọi installation của người dùng, rồi lấy repo của từng installation (100 repo mỗi trang, tối đa 10 trang mỗi installation). Mỗi repo gồm `githubRepoId`, `fullName`, `privateRepo`, `defaultBranch`, `htmlUrl`. |
| FR-GH-02.2 | Thêm một hoặc nhiều repo vào workspace theo danh sách `githubRepoIds` (ít nhất 1). Id trùng trong cùng request chỉ tính một lần. |
| FR-GH-02.3 | Chỉ thêm được repo nằm trong danh sách GitHub App được cấp quyền; id không có trong danh sách thì từ chối với `400`. |
| FR-GH-02.4 | Repo đã có trong workspace (cùng workspace, cùng kết nối, cùng `githubRepoId`) thì bỏ qua, không tạo bản ghi mới. |
| FR-GH-02.5 | Repo mới thêm lưu `fullName`, `defaultBranch`, `privateRepo`, `htmlUrl` lấy từ GitHub, trạng thái `CONNECTED`, `lastSyncedAt = null`. API trả về danh sách các repo vừa thêm (`201`). |
| FR-GH-02.6 | Xem danh sách repo của workspace, sắp theo `fullName`. Người dùng chưa từng kết nối GitHub thì nhận danh sách rỗng. |
| FR-GH-02.7 | Xem chi tiết và gỡ một repo theo `id` (UUID). Gỡ repo chỉ xoá liên kết trong LivingDocs, không thay đổi gì trên GitHub. |
| FR-GH-02.8 | Workspace phải là workspace cá nhân `ws-{userId}` của người dùng đã xác thực; workspace khác thì từ chối với `403`. |
| FR-GH-02.9 | Chỉ chủ repo (repo thuộc kết nối GitHub của người dùng) được xem chi tiết hoặc gỡ repo; người khác nhận `403`. |
| FR-GH-02.10 | Repo có một trong bốn trạng thái: `CONNECTED` (sẵn sàng), `SYNCING` (đang đồng bộ), `ERROR` (repo không còn đọc được trên GitHub), `DISCONNECTED` (người dùng đã ngắt kết nối GitHub). |
| FR-GH-02.11 | GitHub báo token không hợp lệ (401) khi liệt kê repo thì kết nối chuyển `INVALID` và trả `401 GITHUB_REAUTH_REQUIRED`; lỗi GitHub khác trả `502 GITHUB_API_ERROR`. |

## 3. API

Trình duyệt gọi qua Backend (BFF), Backend tự gắn `X-User-Id` (xem [README](README.md)).

| Method | Endpoint | Body | Kết quả | Yêu cầu |
|---|---|---|---|---|
| GET | `/api/github/repos/available` | | `200` danh sách repo được cấp quyền | FR-GH-02.1 |
| POST | `/api/workspaces/{workspaceId}/repositories` | `{"githubRepoIds": [101, 202]}` | `201` danh sách repo vừa thêm | FR-GH-02.2 – 02.5, 02.8 |
| GET | `/api/workspaces/{workspaceId}/repositories` | | `200` danh sách repo, sắp theo `fullName` | FR-GH-02.6, 02.8 |
| GET | `/api/repositories/{id}` | | `200` một repo | FR-GH-02.7, 02.9 |
| DELETE | `/api/repositories/{id}` | | `204` | FR-GH-02.7, 02.9 |

Ví dụ `GET /api/workspaces/ws-42/repositories`:

```json
[{"id": "5b1c6f0e-7d3a-4c2b-9a8e-0f1e2d3c4b5a", "workspaceId": "ws-42", "githubRepoId": 101,
  "fullName": "LivingDocs-Team/Livingdocs", "defaultBranch": "main", "privateRepo": false,
  "htmlUrl": "https://github.com/LivingDocs-Team/Livingdocs", "status": "CONNECTED",
  "lastSyncedAt": null, "createdAt": "2026-10-11T08:00:00Z"}]
```

Lời gọi GitHub: `GET /user/installations?per_page=100`, `GET /user/installations/{id}/repositories?per_page=100&page={p}`.

## 4. Dữ liệu

Bảng `repositories` (cùng migration `V1__init_github_integration.sql`), entity `ConnectedRepository`:

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | UUID | khoá chính, là `id` trong API |
| `workspace_id` | VARCHAR(100) | `ws-{userId}` |
| `connection_id` | UUID | khoá ngoại tới `github_connections(id)` |
| `github_repo_id` | BIGINT | id repo trên GitHub |
| `full_name`, `default_branch`, `html_url` | VARCHAR | lấy từ GitHub, cập nhật lại sau mỗi lần đồng bộ |
| `is_private` | BOOLEAN | |
| `status` | VARCHAR(20) | `CONNECTED`, `SYNCING`, `ERROR`, `DISCONNECTED` |
| `last_synced_at` | timestamptz | thời điểm đồng bộ thành công gần nhất |
| `created_at` | timestamptz | |

Ràng buộc duy nhất `(workspace_id, github_repo_id)`; index theo `workspace_id` và `connection_id`.

## 5. Luồng chính

1. Developer mở trang Repository Management; frontend gọi `GET /api/github/repos/available`.
2. Developer chọn repo; frontend gọi `POST /api/workspaces/ws-{userId}/repositories`.
3. Repo hiện trong `GET /api/workspaces/ws-{userId}/repositories` với trạng thái `CONNECTED`, sẵn sàng đồng bộ (FR-GH-03).
4. Không cần nữa thì gỡ bằng `DELETE /api/repositories/{id}`.

## 6. Luồng lỗi

| Tình huống | Kết quả |
|---|---|
| Chưa kết nối GitHub, hoặc kết nối không còn `ACTIVE` | `409 GITHUB_NOT_CONNECTED` |
| Token GitHub không còn hợp lệ | `401 GITHUB_REAUTH_REQUIRED`, kết nối chuyển `INVALID` |
| `githubRepoIds` rỗng | `400 VALIDATION_ERROR`, "githubRepoIds: phải chọn ít nhất 1 repository" |
| Repo không nằm trong danh sách GitHub App được cấp quyền | `400 BAD_REQUEST`, "Repository <id> không nằm trong danh sách repo mà GitHub App được phép truy cập." |
| Workspace không phải `ws-{userId}` | `403 FORBIDDEN`, "Workspace này không thuộc người dùng đã xác thực." |
| Xem hoặc gỡ repo thuộc kết nối của người khác | `403 FORBIDDEN`, "Repository này không thuộc kết nối GitHub của bạn." |
| Repo không tồn tại | `404 NOT_FOUND`, "Không tìm thấy repository <id>" |
| `id` không phải UUID | `400 BAD_REQUEST` |
| GitHub lỗi khi liệt kê repo | `502 GITHUB_API_ERROR` |

## 7. Quy tắc nghiệp vụ

- Mỗi người dùng chỉ thấy và thay đổi repo trong workspace cá nhân `ws-{userId}` của mình.
- Chỉ repo mà GitHub App được cấp quyền mới thêm được vào workspace.
- Một repo chỉ được liên kết với một workspace một lần; thêm lại không thay đổi gì.
- Gỡ repo chỉ xoá liên kết trong LivingDocs, không ảnh hưởng tới GitHub.
- Giới hạn hiện tại: nếu một request vừa có repo hợp lệ vừa có repo không được cấp quyền, các repo hợp lệ đứng trước repo lỗi vẫn được lưu rồi request mới báo `400`.

## 8. Tiêu chí chấp nhận

- Chỉ thêm được repo mà GitHub App được cấp quyền; thêm trùng không tạo bản ghi mới.
- Repo mới thêm có trạng thái `CONNECTED` và `lastSyncedAt = null`.
- Danh sách repo của workspace sắp theo tên; người dùng chưa kết nối GitHub nhận danh sách rỗng.
- Người khác không xem, thêm vào, hoặc gỡ được repo của workspace không phải của mình (`403`).
- Sau khi ngắt kết nối GitHub, liệt kê repo có thể thêm trả `409 GITHUB_NOT_CONNECTED`.

## 9. Kiểm thử

`GitHubIntegrationFlowTest` (`@SpringBootTest` + MockMvc + database H2, GitHub giả lập bằng `@MockitoBean GitHubClient`), phần quản lý repo trong test `fullFlow` và `revokedTokenOnGitHub_marksConnectionInvalid`:

- GitHub trả 2 repo thì `GET /api/github/repos/available` trả 2 phần tử.
- `POST /api/workspaces/ws-user-flow/repositories` với `{"githubRepoIds":[101,101]}` trả `201`, đúng 1 repo, `status = CONNECTED`, đúng `defaultBranch`.
- Thêm repo không được cấp quyền (`[999]`) trả `400`.
- Người dùng khác xem danh sách, thêm repo vào `ws-user-flow`, xem chi tiết hoặc gỡ repo đều bị `403`; chủ repo gỡ được (`204`), sau đó xem chi tiết bị `404`.
- Sau khi ngắt kết nối GitHub, liệt kê repo có thể thêm trả `409 GITHUB_NOT_CONNECTED`.
- GitHub trả 401 khi liệt kê repo thì API trả `401 GITHUB_REAUTH_REQUIRED` và kết nối chuyển `INVALID`.
