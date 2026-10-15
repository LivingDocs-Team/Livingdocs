# github-integration-service

Service của **TV2**, phụ trách 2 Epic:

- **Epic 2: GitHub Account Connection.** Kết nối tài khoản GitHub qua GitHub App (OAuth), xem trạng thái, ngắt kết nối. Token được mã hoá AES-256-GCM trước khi lưu.
- **Epic 3: Repository Management.** Liệt kê repo GitHub, thêm repo vào workspace, xem danh sách và chi tiết, đồng bộ thủ công, gỡ repo.

Công nghệ: Java 21, Spring Boot 3.5, PostgreSQL, Flyway, Swagger (springdoc).

## API

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/github/authorize-url` | Tạo link kết nối GitHub (`authorizeUrl`) và link cài app (`installUrl`) |
| GET | `/api/github/callback` | GitHub gọi về sau khi người dùng cho phép (Redirect URI) |
| GET | `/api/github/connection` | Xem trạng thái kết nối |
| DELETE | `/api/github/connection` | Ngắt kết nối, thu hồi token |
| GET | `/api/github/repos/available` | Liệt kê repo mà GitHub App được phép truy cập |
| POST | `/api/workspaces/{workspaceId}/repositories` | Thêm repo vào workspace, body: `{"githubRepoIds":[123,456]}` |
| GET | `/api/workspaces/{workspaceId}/repositories` | Danh sách repo (trạng thái, nhánh mặc định, lần đồng bộ cuối) |
| GET | `/api/repositories/{id}` | Chi tiết repo |
| POST | `/api/repositories/{id}/sync` | Đồng bộ repo với GitHub (LD-63): thông tin repo, commit, danh sách file, nội dung file java/python |
| GET | `/api/repositories/{id}/sync/latest` | Kết quả lần đồng bộ gần nhất |
| GET | `/api/repositories/{id}/sync/latest/analysis-input` | Dữ liệu gửi sang service phân tích code (LD-328) |
| DELETE | `/api/repositories/{id}` | Gỡ repo khỏi workspace |

> Tạm thời người dùng được xác định bằng header **`X-User-Id`**. Khi service đăng nhập của TV1 xong, header này sẽ được thay bằng JWT.

Swagger UI: http://localhost:8082/swagger-ui.html

## Chạy trên máy

Cần cài: JDK 21, Docker Desktop, IntelliJ IDEA.

1. Bật database:
   ```bash
   docker compose up -d
   ```
2. Copy `.env.example` thành `.env` rồi điền Client ID, Client secret của GitHub App và `TOKEN_ENCRYPTION_KEY`.
   **Không commit file `.env`.**
3. Tạo khoá mã hoá bằng PowerShell, rồi dán kết quả vào `TOKEN_ENCRYPTION_KEY`:
   ```powershell
   $b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b)
   ```
4. Mở thư mục này bằng IntelliJ và chạy `GithubIntegrationServiceApplication`.
5. Mở http://localhost:8082/actuator/health. Nếu thấy `{"status":"UP"}` là chạy được.

## Chạy test

Test dùng database H2 trong bộ nhớ và một GitHub giả (mock), nên không cần Docker:

```bash
mvn test
```

## Thử luồng kết nối thật

1. Cài GitHub App vào tài khoản của bạn và chọn vài repo: https://github.com/apps/livingdocs-dev-hai/installations/new
2. Gọi `GET /api/github/authorize-url` (có header `X-User-Id: demo-user`), rồi mở `authorizeUrl` trong trình duyệt và bấm **Authorize**.
3. GitHub tự gọi về `/api/github/callback`. Nếu thấy `"Kết nối GitHub thành công"` là xong.
4. Gọi `GET /api/github/repos/available`, rồi `POST /api/workspaces/ws-1/repositories`.

## Đồng bộ repository (LD-63)

`sync/GitHubRepositoryFetcher` lấy dữ liệu một repo từ GitHub theo commit mới nhất của nhánh: thông tin repo, commit, danh sách file, nội dung file java/python, thống kê ngôn ngữ và các commit gần nhất. Nó cũng chuyển lỗi GitHub thành `RepositorySyncException` với mã lỗi rõ ràng (`REPOSITORY_NOT_FOUND`, `TOKEN_INVALID`, `RATE_LIMITED`…).

Cấu trúc dữ liệu, bảng lỗi và cách gọi: xem [docs/repository-sync-contract.md](docs/repository-sync-contract.md).

Dữ liệu mẫu (cho frontend, test, service phân tích) và hướng dẫn chạy test: xem [docs/samples](docs/samples/README.md).

Chạy thử với GitHub thật (repo public, không cần token): chạy `GitHubRepositoryFetcherLiveTest` với biến môi trường `GITHUB_LIVE_TEST=true` (tuỳ chọn thêm `GITHUB_LIVE_REPO=owner/repo`).

## Chưa làm (để sprint sau)

- Webhook (`push`, `pull_request`) và kiểm tra chữ ký HMAC
- Kéo Pull Request và commit về database, gửi event Kafka cho TV3 và TV4
- Thông báo cho người dùng khi token hỏng (hiện tại mới đánh dấu trạng thái `INVALID`)
- Thay header `X-User-Id` bằng JWT của TV1, chuyển nơi lưu OAuth state sang Redis
- Lưu kết quả đồng bộ vào database (hiện chỉ giữ lần gần nhất trong bộ nhớ) và chạy đồng bộ ở nền cho repo lớn
