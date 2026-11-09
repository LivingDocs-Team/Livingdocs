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
| GET | `/api/repositories/{id}/source-changes` | Thay đổi mã nguồn đã phát hiện (LD-116): file Java/Python và code entity thay đổi, cho bước cập nhật tài liệu (LD-128) |
| POST | `/api/repositories/{id}/source-changes/{changeId}/retry` | Chạy lại một source change `FAILED` |

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

## Phát hiện thay đổi mã nguồn (LD-116)

Sau khi webhook được lưu (LD-68), service chạy nền bước phát hiện thay đổi cho:

- mỗi **commit mới trên nhánh mặc định** của repo (commit trên nhánh khác vẫn được lưu nhưng không phát hiện, vì tài liệu đi theo nhánh mặc định và thay đổi trên nhánh khác được xét qua Pull Request);
- mỗi **Pull Request đang mở có commit head mới** (`opened`, `synchronize`).

Các bước:

1. Lấy file thay đổi từ GitHub: `GET /repos/{owner}/{repo}/commits/{sha}` hoặc `GET /repos/{owner}/{repo}/pulls/{number}/files`. Chỉ giữ file Java/Python theo đúng quy tắc chọn file khi đồng bộ (`LanguageDetector`, `PathFilter`).
2. Tải nội dung file sau thay đổi (blob). Nội dung trước thay đổi được dựng lại từ nội dung sau và `patch` của GitHub (`change/UnifiedDiff`), nên không cần gọi thêm GitHub.
3. Gửi nội dung trước và sau sang Code Analyzer (`POST /api/v1/analyze-repo`), so khoảng dòng `lineno`–`end_lineno` của từng class, method, function, endpoint với các dòng được thêm/xoá trong diff (`change/ChangedEntityDetector`): entity chỉ có ở bản sau là `ADDED`, có ở cả hai bản là `MODIFIED`, chỉ có ở bản trước là `REMOVED`.
4. Lưu thành **source change** trạng thái `PENDING` (bảng `source_changes`, `source_change_files`, `source_change_entities`, migration `V3`). Commit / Pull Request không có file mã nguồn nào thay đổi thì không lưu.

Lỗi GitHub hoặc Code Analyzer được lưu thành `FAILED` kèm `errorCode` (`GITHUB_UNAVAILABLE`, `RATE_LIMITED`, `TOKEN_INVALID`, `ACCESS_DENIED`, `REPOSITORY_NOT_FOUND`, `ANALYZER_UNAVAILABLE`, `GITHUB_NOT_CONNECTED`...). Gọi `POST .../source-changes/{changeId}/retry` để chạy lại.

File không tìm được code entity vẫn có trong danh sách, kèm `skippedReason`: `PATCH_UNAVAILABLE` (GitHub không gửi diff vì file quá lớn), `FILE_TOO_LARGE` (trên 200.000 byte), `NOT_ANALYZED` (analyzer báo file rỗng, lỗi cú pháp hoặc không hỗ trợ), `TOO_MANY_FILES` (quá 50 file mã nguồn trong một thay đổi).

**Dữ liệu cho LD-128** (`GET /api/repositories/{id}/source-changes`, mới nhất trước, tối đa 50):

```json
[{
  "id": "4f1c...", "trigger": "COMMIT", "commitSha": "a1b2...", "pullRequestNumber": null,
  "status": "PENDING", "errorCode": null, "errorMessage": null,
  "createdAt": "2026-11-06T05:00:00Z", "updatedAt": "2026-11-06T05:00:00Z",
  "files": [{
    "path": "src/main/java/acme/Invoice.java", "previousPath": null, "change": "MODIFIED",
    "language": "java", "additions": 4, "deletions": 4, "skippedReason": null,
    "entities": [
      {"kind": "METHOD", "name": "Invoice.total", "change": "MODIFIED", "startLine": 2, "endLine": 4},
      {"kind": "METHOD", "name": "Invoice.tax", "change": "ADDED", "startLine": 6, "endLine": 8},
      {"kind": "METHOD", "name": "Invoice.discount", "change": "REMOVED", "startLine": 6, "endLine": 8}
    ]
  }]
}]
```

`startLine`/`endLine` là dòng trong file sau thay đổi; với `REMOVED` là dòng trong file trước thay đổi. Cách đánh dấu một source change đã được cập nhật tài liệu sẽ thống nhất với LD-128.

## Chưa làm (để sprint sau)

- Tìm tài liệu bị ảnh hưởng bởi source change (LD-122) và cách đánh dấu source change đã cập nhật tài liệu (cùng LD-128)
- Thông báo cho người dùng khi token hỏng (hiện tại mới đánh dấu trạng thái `INVALID`)
- Duy trì credential service-to-service trong secret manager phù hợp với môi trường triển khai
- Lưu kết quả đồng bộ vào database (hiện chỉ giữ lần gần nhất trong bộ nhớ) và chạy đồng bộ ở nền cho repo lớn
