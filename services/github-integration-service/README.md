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
| POST | `/api/repositories/{id}/drift/analyze` | Phân tích lệch tài liệu thủ công cho một Pull Request (LD-145), body: `{"pullRequestNumber":7}` |
| GET | `/api/repositories/{id}/drift/reports?pullRequest=7` | Các báo cáo lệch tài liệu của repo, mới nhất trước |
| GET | `/api/drift/reports/{reportId}` | Một báo cáo: findings, tài liệu bị ảnh hưởng, bằng chứng |
| GET | `/api/repositories/{id}/drift/reports/{reportId}?minSeverity=high` | Báo cáo của repo (frontend gọi qua BFF), lọc theo mức độ (LD-156) |
| GET | `/api/repositories/{id}/drift/reports/{reportId}/markdown` | Báo cáo dạng Markdown theo mức độ, để dán làm comment PR |
| GET | `/api/documentation/drift/severity-rules` | Các mức độ (khoảng điểm, ý nghĩa, việc cần làm) và các luật đánh giá |
| PUT | `/api/repositories/{id}/drift/reports/{reportId}/findings/{findingId}/resolution` | Xử lý một phát hiện (LD-346): `{"status":"acknowledged\|resolved\|dismissed\|open","note":"..."}`; dismissed bắt buộc có `note`; người thực hiện = user đang đăng nhập |

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

## Phát hiện lệch tài liệu (LD-145)

`service/DriftAnalysisService` phân tích **thủ công** một Pull Request (người dùng nhập số PR):

```
GitHub: PR + file thay đổi kèm diff        GET /repos/{o}/{r}/pulls/{n}, /pulls/{n}/files (nhiều trang)
        merge base của PR                  GET /repos/{o}/{r}/compare/{base}...{head}
        nội dung file .py/.java ở 2 phía   cây thư mục + blob ở merge base và head
code-analyzer: phân tích 2 phiên bản       POST /api/v1/analyze-repo  (-> before / after)
GitHub: README + file .md của repo         ở commit head (bỏ node_modules, target, dist...)
ai-service: POST /drift/analyze            findings Referential / Signature / Semantic, độ nghiêm trọng,
                                           độ tin cậy, bằng chứng (diff, đoạn tài liệu, commit, ticket)
```

Body: `pullRequestNumber` (bắt buộc), `documentIds` (tuỳ chọn; mặc định mọi tài liệu đã lưu **của repo
này**, tài liệu của repo khác bị từ chối kèm cảnh báo), `includeRepositoryDocs` (mặc định `true`).

- Diff của PR tính từ merge base, nên "trước thay đổi" cũng đọc ở merge base (không phải đầu nhánh `main`).
- Tối đa 100 file Python/Java được tải nội dung, 30 file Markdown; file khác chỉ kiểm tra bằng diff.
- code-analyzer lỗi hoặc không tải được một file: vẫn có báo cáo, thay đổi đọc từ diff (độ tin cậy thấp
  hơn), lý do nằm ở đầu `warnings`.
- Lỗi: `400 BAD_REQUEST` thiếu số PR, `404 PULL_REQUEST_NOT_FOUND`, `401 GITHUB_REAUTH_REQUIRED` (token
  bị GitHub từ chối, kết nối bị đánh dấu `INVALID`), `502 AI_SERVICE_FAILED`, `403` báo cáo của người khác.
- Mức độ (LD-156): mỗi finding có `severity_assessment` (luật gốc, các điều chỉnh, mã bằng chứng,
  điểm 0-100). Backend BFF chỉ chuyển tiếp `/api/repositories/**` và `/api/documentation/**`, nên
  frontend dùng các route theo repo ở trên (`/api/drift/reports/{id}` vẫn giữ cho gọi nội bộ).
- AI review và xử lý (LD-346): mỗi finding có `ai_review` (AI xác nhận / phản bác / không chắc, giải
  thích có trích mã bằng chứng, gợi ý đoạn tài liệu cần sửa; không có API key thì giải thích sinh từ
  luật) và `resolution` (open → acknowledged / resolved / dismissed, có lịch sử). Lỗi:
  `400 BAD_REQUEST` trạng thái sai hoặc dismissed thiếu lý do, `404` finding không tồn tại.
- Báo cáo giữ trong bộ nhớ (cả ở ai-service), mất khi khởi động lại. Chi tiết luật phát hiện:
  [ai-service/README.md](../../ai-service/README.md).

## Chưa làm (để sprint sau)

- Webhook (`push`, `pull_request`) và kiểm tra chữ ký HMAC (để phân tích lệch tài liệu tự động khi có PR; hiện chạy thủ công)
- Kéo Pull Request và commit về database, gửi event Kafka cho TV3 và TV4
- Thông báo cho người dùng khi token hỏng (hiện tại mới đánh dấu trạng thái `INVALID`)
- Duy trì credential service-to-service trong secret manager phù hợp với môi trường triển khai
- Lưu kết quả đồng bộ vào database (hiện chỉ giữ lần gần nhất trong bộ nhớ) và chạy đồng bộ ở nền cho repo lớn
