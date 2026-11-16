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
| GET | `/api/repositories/{id}/source-changes` | Thay đổi mã nguồn đã phát hiện (LD-116): file Java/Python và code entity thay đổi, cùng tài liệu bị ảnh hưởng (LD-122), cho bước cập nhật tài liệu (LD-128) |
| POST | `/api/repositories/{id}/source-changes/{changeId}/retry` | Chạy lại một source change `FAILED`, hoặc chỉ bước tìm tài liệu khi `documentsStatus` là `FAILED` |
| POST | `/api/repositories/{id}/drift/analyze` | Phân tích lệch tài liệu thủ công cho một Pull Request (LD-145), body: `{"pullRequestNumber":7}` |
| GET | `/api/repositories/{id}/drift/reports?pullRequest=7` | Các báo cáo lệch tài liệu của repo, mới nhất trước |
| GET | `/api/drift/reports/{reportId}` | Một báo cáo: findings, tài liệu bị ảnh hưởng, bằng chứng |
| GET | `/api/repositories/{id}/drift/reports/{reportId}?minSeverity=high` | Báo cáo của repo (frontend gọi qua BFF), lọc theo mức độ (LD-156) |
| GET | `/api/repositories/{id}/drift/reports/{reportId}/markdown` | Báo cáo dạng Markdown theo mức độ, để dán làm comment PR |
| GET | `/api/documentation/drift/severity-rules` | Các mức độ (khoảng điểm, ý nghĩa, việc cần làm) và các luật đánh giá |

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

Hai nguồn, cùng ghi vào bảng `github_pull_requests` và `github_commits` (migration `V5`):

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
4. Lưu thành **source change** trạng thái `PENDING` (bảng `source_changes`, `source_change_files`, `source_change_entities`, migration `V6`). Commit / Pull Request không có file mã nguồn nào thay đổi thì không lưu.

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

## Tài liệu bị ảnh hưởng (LD-122)

Ngay sau khi lưu một source change `PENDING`, service hỏi ai-service phần tài liệu đã lưu nào có thể đã cũ:

```
ai-service GET /documents                        tài liệu của repo (target = owner/name), như LD-145
ai-service POST /internal/affected-documents     file + code entity của source change, id các tài liệu đó
  -> lưu vào bảng source_change_documents (migration V8)
```

Luật so khớp là của LD-148 (`ai-service/app/drift_affected.py`), không viết lại ở Java:

- **LD-123, ánh xạ thay đổi với tài liệu:** một phần (theo file) của tài liệu bị ảnh hưởng nếu nó được sinh ra từ file thay đổi (kể cả file bị xoá, đổi tên, hay file LD-116 bỏ qua không tìm được entity), hoặc nếu nó nhắc tới entity, endpoint hay đường dẫn đã thay đổi. Tên phải khớp nguyên từ; entity `ADDED` chỉ tính cho phần của chính file đó.
- **LD-124, tài liệu bị ảnh hưởng:** danh sách `affectedDocuments` của source change, mỗi phần tử là một phần của một tài liệu, kèm phiên bản hiện hành lúc kiểm tra và lý do (`documents changed file …`, ``mentions `…` ``).
- **LD-125, phụ thuộc:** `DIRECT` là phần của chính file thay đổi, `DEPENDENT` là phần mô tả code khác nhưng nhắc tới code đã thay đổi. `DIRECT` đứng trước.
- **LD-126, bằng chứng:** `evidence` của mỗi phần là các chỗ trong tài liệu nhắc tới code đã thay đổi: `target` (entity, endpoint hoặc đường dẫn), `kind`, `line` (dòng trong phần tài liệu) và `excerpt` (đoạn trích dòng đó), theo thứ tự dòng, tối đa 20 chỗ (bảng `source_change_document_evidence`). Phần `DIRECT` không nhắc tên nào thì `evidence` rỗng; lý do là chính file thay đổi, xem `files` của source change.
- **Hiển thị:** frontend, màn hình Repository Management → "PRs & commits" → mục "Source changes", liệt kê tài liệu bị ảnh hưởng của từng source change kèm nhãn Direct / Dependent, lý do và bằng chứng theo dòng.

Repo chưa có tài liệu nào thì không gọi ai-service. Chỉ tài liệu của repo được gửi đi, nên tài liệu của repo khác không bao giờ bị đọc. `documentsStatus`: `PENDING` (đang tìm), `FOUND` (xong, danh sách có thể rỗng), `FAILED` (ai-service lỗi, `documentsErrorCode` = `AI_SERVICE_UNAVAILABLE`; gọi retry để chỉ chạy lại bước này), `null` khi source change `FAILED`.

```json
{"id": "4f1c...", "status": "PENDING", "files": [...],
 "documentsStatus": "FOUND", "documentsErrorCode": null, "documentsErrorMessage": null,
 "affectedDocuments": [
   {"documentId": "9b2e...", "title": "acme/docs", "version": 3,
    "section": "src/main/java/acme/Invoice.java", "documentsFile": "src/main/java/acme/Invoice.java",
    "dependency": "DIRECT", "reasons": ["documents changed file src/main/java/acme/Invoice.java"], "evidence": []},
   {"documentId": "9b2e...", "title": "acme/docs", "version": 3,
    "section": "src/main/java/acme/Checkout.java", "documentsFile": "src/main/java/acme/Checkout.java",
    "dependency": "DEPENDENT", "reasons": ["mentions `Invoice.total`"],
    "evidence": [{"target": "Invoice.total", "kind": "name", "line": 14,
                  "excerpt": "Checkout charges `Invoice.total()` of the cart."}]}
 ]}
```

Bước tiếp theo (LD-128, chưa vào `main`): gọi `POST /documents/{id}/updates` của ai-service cho từng `documentId` trong danh sách.

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
- Báo cáo giữ trong bộ nhớ (cả ở ai-service), mất khi khởi động lại. Chi tiết luật phát hiện:
  [ai-service/README.md](../../ai-service/README.md).

## Chưa làm (để sprint sau)

- Gọi LD-128 cập nhật từng tài liệu bị ảnh hưởng (LD-122) và đánh dấu source change đã cập nhật tài liệu, khi LD-128 vào `main`- Chạy phân tích lệch tài liệu tự động khi webhook nhận `pull_request` (hiện chạy thủ công)
- Gửi event Kafka cho TV3 và TV4 khi nhận Pull Request và commit
- Thông báo cho người dùng khi token hỏng (hiện tại mới đánh dấu trạng thái `INVALID`)
- Duy trì credential service-to-service trong secret manager phù hợp với môi trường triển khai
- Lưu kết quả đồng bộ vào database (hiện chỉ giữ lần gần nhất trong bộ nhớ) và chạy đồng bộ ở nền cho repo lớn
