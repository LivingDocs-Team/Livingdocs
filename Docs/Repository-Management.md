# Quản lý repository (Repository Management)

| Mục | Nội dung |
|---|---|
| Người làm | Đặng Lê Hiển Hải (TV2) |
| Jira | Story LD-23; task LD-58 (Sprint 1, cùng PR với LD-53), LD-23 (Sprint 3) |
| Code | `services/github-integration-service`, package `com.livingdocs.github` |
| Phụ thuộc | GitHub Account Connection (nền tảng service, `GitHubClient`, `GitHubConnectionService`, `ApiException`, `GlobalExceptionHandler`) |

## 1. Mục tiêu

Người dùng đã kết nối GitHub chọn các repository mà GitHub App được cấp quyền để đưa vào workspace của mình trong LivingDocs, xem danh sách và chi tiết các repo đã thêm, và gỡ repo. Chỉ repo đã thêm mới được đồng bộ và sinh tài liệu.

## 2. Dữ liệu

Bảng `repositories`, nằm cùng migration `V1__init_github_integration.sql` với bảng `github_connections`:

```sql
CREATE TABLE repositories (
    id              UUID PRIMARY KEY,
    workspace_id    VARCHAR(100) NOT NULL,
    connection_id   UUID         NOT NULL REFERENCES github_connections (id),
    github_repo_id  BIGINT       NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    default_branch  VARCHAR(255),
    is_private      BOOLEAN      NOT NULL DEFAULT FALSE,
    html_url        VARCHAR(500),
    status          VARCHAR(20)  NOT NULL,  -- CONNECTED / SYNCING / ERROR / DISCONNECTED
    last_synced_at  TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_repositories_workspace_repo UNIQUE (workspace_id, github_repo_id)
);
CREATE INDEX idx_repositories_workspace ON repositories (workspace_id);
CREATE INDEX idx_repositories_connection ON repositories (connection_id);
```

- `entity/RepositoryStatus`: enum `CONNECTED` (sẵn sàng), `SYNCING` (đang đồng bộ), `ERROR` (repo không còn truy cập được), `DISCONNECTED` (người dùng đã ngắt kết nối GitHub).
- `entity/ConnectedRepository` (`@Entity @Table(name = "repositories")`): `UUID id` (`@GeneratedValue(strategy = GenerationType.UUID)`), `String workspaceId`, `UUID connectionId`, `Long githubRepoId`, `String fullName`, `String defaultBranch`, `boolean privateRepo` (cột `is_private`, getter `isPrivateRepo()`), `String htmlUrl`, `RepositoryStatus status` (`@Enumerated(EnumType.STRING)` + `@JdbcTypeCode(SqlTypes.VARCHAR)`), `Instant lastSyncedAt`, `Instant createdAt` (không cập nhật, gán trong `@PrePersist`). Có getter, setter.
- `repository/ConnectedRepositoryRepository extends JpaRepository<ConnectedRepository, UUID>`:
  - `List<ConnectedRepository> findByWorkspaceIdAndConnectionIdOrderByFullNameAsc(String workspaceId, UUID connectionId)`
  - `List<ConnectedRepository> findByConnectionId(UUID connectionId)` (dùng khi ngắt kết nối GitHub)
  - `boolean existsByWorkspaceIdAndConnectionIdAndGithubRepoId(String workspaceId, UUID connectionId, Long githubRepoId)`

## 3. Gọi GitHub: liệt kê repo được cấp quyền

Trong `client/GitHubClient`, hằng số `PER_PAGE = 100`, `MAX_PAGES = 10`:

- `List<GitHubRepo> listAccessibleRepositories(String accessToken)`:
  1. `GET /user/installations?per_page=100` (Bearer token) lấy danh sách cài đặt GitHub App: `record Installations(@JsonProperty("total_count") Integer totalCount, List<Installation> installations)`, `record Installation(Long id)`. Rỗng thì trả danh sách rỗng.
  2. Với mỗi installation, gọi `GET /user/installations/{id}/repositories?per_page=100&page={p}` với `p` từ 1 tới 10: `record InstallationRepos(@JsonProperty("total_count") Integer totalCount, List<GitHubRepo> repositories)`. Dừng khi trang rỗng hoặc ít hơn 100 repo.
- `record GitHubRepo(Long id, @JsonProperty("full_name") String fullName, @JsonProperty("private") boolean privateRepo, @JsonProperty("default_branch") String defaultBranch, @JsonProperty("html_url") String htmlUrl)`.
- Các record đều có `@JsonIgnoreProperties(ignoreUnknown = true)`. Lỗi đi qua hàm `call()` chung (thành `GitHubApiException`).

## 4. Xử lý nghiệp vụ: `service/RepositoryManagementService` (`@Service`)

Phụ thuộc: `GitHubConnectionService`, `GitHubClient`, `ConnectedRepositoryRepository`.

- **`fetchAccessibleRepos(userId)`** (private): `connection = connectionService.getActiveConnection(userId)`, gọi `listAccessibleRepositories(connection.getAccessToken())`. Nếu `GitHubApiException.isUnauthorized()` thì `connectionService.markInvalid(connection)` rồi ném `ApiException.githubReauthRequired()`; lỗi khác ném tiếp (thành `502 GITHUB_API_ERROR`).
- **`listAvailable(userId)`**: map mỗi `GitHubRepo` thành `AvailableRepositoryResponse(githubRepoId, fullName, privateRepo, defaultBranch, htmlUrl)`.
- **`addRepositories(userId, workspaceId, githubRepoIds)`** (`@Transactional(noRollbackFor = ApiException.class)`):
  1. Kiểm tra workspace cá nhân (bên dưới).
  2. `connection = getActiveConnection(userId)`; lấy repo được cấp quyền, đưa vào `Map<Long, GitHubRepo>` theo `id`.
  3. Duyệt `githubRepoIds` đã bỏ trùng (`distinct`, giữ thứ tự). Id không có trong map thì `ApiException.badRequest("Repository <id> không nằm trong danh sách repo mà GitHub App được phép truy cập.")`. Đã có bản ghi cùng `(workspaceId, connectionId, githubRepoId)` thì bỏ qua.
  4. Tạo `ConnectedRepository`: `workspaceId`, `connectionId`, `githubRepoId`, `fullName`, `defaultBranch`, `privateRepo`, `htmlUrl` lấy từ GitHub, `status = CONNECTED`, `lastSyncedAt = null`; lưu và thêm vào kết quả.
  5. Trả danh sách `RepositoryResponse` của các repo vừa thêm.
- **`listByWorkspace(userId, workspaceId)`** (`readOnly`): kiểm tra workspace cá nhân; chưa có kết nối GitHub (`findConnection` rỗng) thì trả danh sách rỗng; ngược lại `findByWorkspaceIdAndConnectionIdOrderByFullNameAsc`.
- **`get(userId, id)`** (`readOnly`): tìm repo, không có thì `ApiException.notFound("Không tìm thấy repository <id>")`; kiểm tra chủ repo; trả `RepositoryResponse`.
- **`disconnect(userId, id)`** (`@Transactional`): tìm repo, kiểm tra chủ repo, xoá bản ghi.
- **Kiểm tra chủ repo**: lấy kết nối của `userId` (bất kể trạng thái); không có, hoặc `connection.getId()` khác `repo.getConnectionId()` thì `ApiException.forbidden("Repository này không thuộc kết nối GitHub của bạn.")`.
- **Kiểm tra workspace cá nhân** (bổ sung ở LD-396): `workspaceId` phải bằng `"ws-" + userId`, ngược lại `ApiException.forbidden("Workspace này không thuộc người dùng đã xác thực.")`.

## 5. API: `controller/RepositoryController`

`@RestController`, `@Tag(name = "Repository Management")`. Mọi API cần header `X-User-Id`.

| Method | Path | Body | Kết quả |
|---|---|---|---|
| GET | `/api/github/repos/available` | | `200` danh sách `AvailableRepositoryResponse` |
| POST | `/api/workspaces/{workspaceId}/repositories` | `{"githubRepoIds": [101, 202]}` | `201` danh sách `RepositoryResponse` vừa thêm |
| GET | `/api/workspaces/{workspaceId}/repositories` | | `200` danh sách `RepositoryResponse`, sắp theo `fullName` |
| GET | `/api/repositories/{id}` | | `200` `RepositoryResponse` (`id` là UUID) |
| DELETE | `/api/repositories/{id}` | | `204` |

DTO (`dto/`):

- `AddRepositoriesRequest(@NotEmpty(message = "phải chọn ít nhất 1 repository") List<Long> githubRepoIds)`; controller nhận bằng `@Valid @RequestBody`.
- `AvailableRepositoryResponse(Long githubRepoId, String fullName, boolean privateRepo, String defaultBranch, String htmlUrl)`.
- `RepositoryResponse(UUID id, String workspaceId, Long githubRepoId, String fullName, String defaultBranch, boolean privateRepo, String htmlUrl, String status, Instant lastSyncedAt, Instant createdAt)` kèm `static RepositoryResponse from(ConnectedRepository r)` (status dùng `name()`).

Ví dụ response của `GET /api/workspaces/ws-42/repositories`:

```json
[{"id": "5b1c6f0e-7d3a-4c2b-9a8e-0f1e2d3c4b5a", "workspaceId": "ws-42", "githubRepoId": 101,
  "fullName": "LivingDocs-Team/Livingdocs", "defaultBranch": "main", "privateRepo": false,
  "htmlUrl": "https://github.com/LivingDocs-Team/Livingdocs", "status": "CONNECTED",
  "lastSyncedAt": null, "createdAt": "2026-10-11T08:00:00Z"}]
```

## 6. Luồng sử dụng

1. Người dùng mở màn hình Repository; frontend gọi `GET /api/github/repos/available`.
2. Người dùng chọn repo, frontend gọi `POST /api/workspaces/ws-{userId}/repositories`.
3. Repo hiện trong `GET /api/workspaces/ws-{userId}/repositories` với trạng thái `CONNECTED`, sẵn sàng đồng bộ.
4. Không cần nữa thì `DELETE /api/repositories/{id}`.

## 7. Lỗi

| Tình huống | Kết quả |
|---|---|
| Chưa kết nối GitHub, hoặc kết nối không còn `ACTIVE` | `409 GITHUB_NOT_CONNECTED` |
| Token GitHub không còn hợp lệ | `401 GITHUB_REAUTH_REQUIRED`, kết nối chuyển `INVALID` |
| `githubRepoIds` rỗng | `400 VALIDATION_ERROR` |
| Repo không nằm trong danh sách GitHub App được cấp quyền | `400 BAD_REQUEST` |
| Workspace không phải `ws-{userId}` | `403 FORBIDDEN` |
| Xem hoặc gỡ repo thuộc kết nối khác | `403 FORBIDDEN` |
| Repo không tồn tại | `404 NOT_FOUND` |
| `id` không phải UUID | `400 BAD_REQUEST` |
| GitHub lỗi khi liệt kê repo | `502 GITHUB_API_ERROR` |

**Giới hạn hiện tại:** vì `noRollbackFor = ApiException.class`, nếu một request vừa có repo hợp lệ vừa có repo không được cấp quyền thì các repo hợp lệ đứng trước repo lỗi vẫn được lưu, sau đó request báo `400`.

## 8. Test cần có

`GitHubIntegrationFlowTest` (`@SpringBootTest` + MockMvc + H2, `@MockitoBean GitHubClient`), phần quản lý repo:

- GitHub trả 2 repo thì `GET /api/github/repos/available` trả 2 phần tử.
- `POST /api/workspaces/ws-user-flow/repositories` (người dùng `user-flow`) với `{"githubRepoIds":[101,101]}` trả `201`, đúng 1 repo, `status = CONNECTED`, đúng `defaultBranch`.
- `POST` với repo không được cấp quyền (`[999]`) trả `400`.
- Danh sách workspace có đúng 1 repo.
- Người dùng khác xem danh sách, thêm repo vào `ws-user-flow`, hoặc xem chi tiết repo đều bị `403`.
- Người khác gỡ repo bị `403`; chủ repo gỡ được (`204`), sau đó xem chi tiết bị `404`.
- Sau khi ngắt kết nối GitHub, liệt kê repo có thể thêm trả `409 GITHUB_NOT_CONNECTED`.
- GitHub trả 401 khi liệt kê repo thì API trả `401 GITHUB_REAUTH_REQUIRED` và kết nối chuyển `INVALID`.

## 9. Tiêu chí chấp nhận

- Chỉ thêm được repo mà GitHub App được cấp quyền; thêm trùng không tạo bản ghi mới.
- Repo mới thêm có trạng thái `CONNECTED` và `lastSyncedAt = null`.
- Danh sách repo của workspace sắp theo tên; chưa kết nối GitHub thì là danh sách rỗng.
- Chỉ chủ repo xem chi tiết và gỡ được repo.
