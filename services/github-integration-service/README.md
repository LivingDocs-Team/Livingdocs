# github-integration-service

Service của **TV2**, phụ trách 2 Epic:

- **Epic 2: GitHub Account Connection.** Kết nối tài khoản GitHub qua GitHub App (OAuth), xem trạng thái, ngắt kết nối. Token được mã hoá AES-256-GCM trước khi lưu.
- **Epic 3: Repository Management.** Liệt kê repo GitHub, thêm repo vào workspace, xem danh sách và chi tiết, đồng bộ thủ công, gỡ repo.

Công nghệ: Java 21, Spring Boot 3.5, PostgreSQL, Flyway, Swagger (springdoc).

## API

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/github/authorize-url` | Tạo link kết nối GitHub (`authorizeUrl`) và link cài app (`installUrl`) |
| GET | `/api/github/callback` | GitHub gọi về sau khi người dùng cho phép (Redirect URI). Có `FRONTEND_URL` thì chuyển người dùng về frontend |
| GET | `/api/github/connection` | Xem trạng thái kết nối |
| DELETE | `/api/github/connection` | Ngắt kết nối, thu hồi token |
| GET | `/api/github/repos/available` | Liệt kê repo mà GitHub App được phép truy cập |
| POST | `/api/workspaces/{workspaceId}/repositories` | Thêm repo vào workspace, body: `{"githubRepoIds":[123,456]}` |
| GET | `/api/workspaces/{workspaceId}/repositories` | Danh sách repo (trạng thái, nhánh mặc định, lần đồng bộ cuối) |
| GET | `/api/repositories/{id}` | Chi tiết repo |
| POST | `/api/repositories/{id}/sync` | Đồng bộ repo với GitHub (LD-63): thông tin repo, commit, danh sách file, nội dung file java/python |
| GET | `/api/repositories/{id}/sync/latest` | Kết quả lần đồng bộ gần nhất |
| GET | `/api/repositories/{id}/sync/latest/analysis-input` | Dữ liệu gửi sang service phân tích code (`POST /api/v1/analyze-repo`, LD-395) |
| DELETE | `/api/repositories/{id}` | Gỡ repo khỏi workspace |
| GET | `/api/repositories/{id}/pull-requests` | Pull Request đã nhận của repo (LD-68), cập nhật gần nhất trước |
| GET | `/api/repositories/{id}/commits` | Commit đã nhận của repo (LD-68), mới nhất trước |
| POST | `/api/github/webhook` | GitHub gọi khi có `push` / `pull_request` (LD-68). Không qua Backend, xác thực bằng chữ ký `X-Hub-Signature-256` |

> Browser không gọi service này trực tiếp. Backend BFF xác minh session, lấy user ID từ principal phía server và gửi request kèm `GITHUB_INTEGRATION_INTERNAL_SECRET`. GitHub Integration từ chối request thiếu/sai credential. Chi tiết: [Backend BFF authentication contract](docs/backend-bff-authentication.md).

Các endpoint API được mô tả trong OpenAPI; cổng service chỉ bind loopback cho OAuth callback và request nội bộ. Swagger UI không mở cho browser.

**Frontend gọi API:** xem [docs/frontend-api-guide.md](docs/frontend-api-guide.md) (cấu hình proxy, CORS, luồng kết nối GitHub, bảng lỗi).

## Chạy trên máy

Cần cài: JDK 21, Docker Desktop, IntelliJ IDEA.

1. Bật database (dịch vụ `github-db` trong `compose.yaml` ở thư mục gốc, cổng `127.0.0.1:5433`):
   ```bash
   docker compose -f ../../compose.yaml up -d github-db
   ```
2. Copy `.env.example` thành `.env` rồi điền Client ID, Client secret của GitHub App, `TOKEN_ENCRYPTION_KEY` và `GITHUB_INTEGRATION_INTERNAL_SECRET`.
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

CI (job **GitHub Integration Service Test** trong `.github/workflows/ci.yml`) chạy toàn bộ test này ở mỗi lần push và pull request, rồi chạy thêm `GitHubRepositoryFetcherLiveTest` với GitHub thật. Báo cáo kiểm thử (LD-391): [docs/github-test-report.md](docs/github-test-report.md).

## Thử luồng kết nối thật

1. Cài GitHub App vào tài khoản của bạn và chọn vài repo: https://github.com/apps/livingdocs-dev-hai/installations/new
2. Đăng nhập qua Backend rồi gọi `GET /api/github/authorize-url` qua Backend BFF; mở `authorizeUrl` trong trình duyệt và bấm **Authorize**.
3. GitHub tự gọi về `/api/github/callback`. Nếu thấy `"Kết nối GitHub thành công"` là xong. (Nếu đã đặt `FRONTEND_URL` trong `.env` thì trình duyệt chuyển về trang đó kèm `?github=connected&login=...`.)
4. Gọi `GET /api/github/repos/available`, rồi `POST /api/workspaces/ws-1/repositories`.

## Đồng bộ repository (LD-63)

`sync/GitHubRepositoryFetcher` lấy dữ liệu một repo từ GitHub theo commit mới nhất của nhánh: thông tin repo, commit, danh sách file, nội dung file java/python, thống kê ngôn ngữ và các commit gần nhất. Nó cũng chuyển lỗi GitHub thành `RepositorySyncException` với mã lỗi rõ ràng (`REPOSITORY_NOT_FOUND`, `TOKEN_INVALID`, `RATE_LIMITED`…).

Cấu trúc dữ liệu, bảng lỗi và cách gọi: xem [docs/repository-sync-contract.md](docs/repository-sync-contract.md).

Dữ liệu mẫu (cho frontend, test, service phân tích) và hướng dẫn chạy test: xem [docs/samples](docs/samples/README.md).

Chạy thử với GitHub thật (repo public, không cần token): chạy `GitHubRepositoryFetcherLiveTest` với biến môi trường `GITHUB_LIVE_TEST=true` (tuỳ chọn thêm `GITHUB_LIVE_REPO=owner/repo`).

## Nhận Pull Request và commit (LD-68)

Hai nguồn, cùng ghi vào bảng `github_pull_requests` và `github_commits` (migration `V4`):

- **Webhook** `POST /api/github/webhook`: kiểm chữ ký bằng `GITHUB_WEBHOOK_SECRET`, chỉ nhận event `push` và `pull_request` của repo đã thêm vào workspace. GitHub gửi lại cùng `X-GitHub-Delivery` thì trả `DUPLICATE`, không ghi lần hai. Push tag hoặc xoá nhánh không tạo commit.
- **Lấy bù khi đồng bộ**: mỗi lần `POST /api/repositories/{id}/sync` thành công thì lưu các commit gần nhất của nhánh và 30 Pull Request cập nhật gần nhất, để không mất dữ liệu khi webhook bị lỡ (service tắt, mạng lỗi). Không lấy được danh sách PR thì chỉ ghi log, lần đồng bộ vẫn thành công.

Mỗi commit (theo SHA) và mỗi Pull Request (theo số) chỉ có một dòng cho mỗi repo. Event Pull Request cũ đến muộn không ghi đè dữ liệu mới hơn. Gỡ repo khỏi workspace thì xoá luôn PR và commit của repo đó.

**Cấu hình webhook cho GitHub App** (người quản lý app `livingdocs-dev-hai`):

1. Tạo một chuỗi ngẫu nhiên làm secret và điền vào `GITHUB_WEBHOOK_SECRET` trong `.env` (không commit).
2. Khi chạy trên máy, GitHub không gọi được `localhost`, nên dùng kênh chuyển tiếp: mở https://smee.io/new, lấy URL rồi chạy
   ```bash
   npx smee-client --url https://smee.io/<kenh-cua-ban> --target http://localhost:8082/api/github/webhook
   ```
3. Trong trang cài đặt GitHub App: bật **Webhook → Active**, điền **Webhook URL** (URL smee ở bước 2) và **Webhook secret** (giống bước 1).
4. Mục **Permissions & events → Subscribe to events**: chọn **Push** và **Pull request**. App đã có quyền đọc Contents và Pull requests nên không cần thêm quyền.
5. Mục **Advanced** của app hiện lần gửi `ping`; service trả `{"status":"PONG"}` là cấu hình đúng.

## Chưa làm (để sprint sau)

- Phát hiện file và code entity thay đổi từ commit / Pull Request đã nhận (LD-116), gửi event cho TV3 và TV4
- Thông báo cho người dùng khi token hỏng (hiện tại mới đánh dấu trạng thái `INVALID`)
- Duy trì credential service-to-service trong secret manager phù hợp với môi trường triển khai
- Lưu kết quả đồng bộ vào database (hiện chỉ giữ lần gần nhất trong bộ nhớ) và chạy đồng bộ ở nền cho repo lớn
