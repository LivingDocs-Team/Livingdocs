# LivingDocs — Đặc tả tái tạo chức năng LD-63: Repository Synchronization

> Tài liệu độc lập được trích xuất từ snapshot `Livingdocs-LD-63.zip`, branch `LD-63-Repository-Synchronization`. Mục tiêu: cung cấp đủ ngữ cảnh nghiệp vụ, kiến trúc, hợp đồng dữ liệu và quy tắc xử lý để AI có thể tái tạo chức năng mà không phải suy diễn từ các branch khác.

## 1. Mục tiêu và phạm vi

Chức năng đồng bộ repository lấy snapshot của một repository GitHub thuộc workspace của người dùng. Snapshot được lấy nhất quán theo commit mới nhất của nhánh được chọn và gồm:
- Thông tin repository và nhánh.
- Commit HEAD.
- Cây file của repository.
- Nội dung các file mã nguồn Java/Python được hỗ trợ.
- Thống kê ngôn ngữ, một số commit gần đây, thống kê số lượng file và cảnh báo.

Chức năng phục vụ bước phân tích code tiếp theo. API dành cho giao diện không trả nội dung file lớn; endpoint `analysis-input` tạo payload có nội dung file để gửi cho analyzer.

**Không thuộc phạm vi của LD-63:** GitHub OAuth/đăng nhập, webhook push/pull_request, đồng bộ nền, lưu lịch sử snapshot lâu dài, Kafka events, chức năng phân tích AST và sinh tài liệu AI.

## 2. Vị trí mã nguồn

Trong repository:
- `services/github-integration-service/src/main/java/com/livingdocs/github/sync/GitHubRepositoryFetcher.java`: gọi GitHub API và tạo snapshot.
- `.../sync/SyncOptions.java`: tham số đồng bộ.
- `.../sync/RepositorySnapshot.java`: mô hình snapshot và các file có thể phân tích.
- `.../sync/PathFilter.java`: lọc file và đường dẫn.
- `.../sync/LanguageDetector.java`: nhận diện ngôn ngữ theo đường dẫn.
- `.../sync/AnalysisInput.java`: chuyển snapshot thành payload cho analyzer.
- `.../sync/RepositorySyncException.java`, `SyncErrorCode.java`, `SyncWarning.java`: lỗi và cảnh báo.
- `.../service/RepositorySyncService.java`: điều phối quyền sở hữu repo, trạng thái, token và kết quả đồng bộ.
- `.../controller/RepositorySyncController.java`: REST endpoints.
- `.../exception/GlobalExceptionHandler.java`: chuẩn hóa lỗi thành JSON.
- `.../client/GitHubClient.java`: HTTP client gọi GitHub.
- `.../entity/ConnectedRepository.java`: dữ liệu repository thuộc workspace.

## 3. Công nghệ và phụ thuộc

- Java 21, Spring Boot 3.5, Spring Web, Spring Data JPA.
- GitHub REST API.
- PostgreSQL cho dữ liệu kết nối/repository; test dùng H2 và GitHub mock.
- OAuth token được lấy từ GitHub connection service, không đưa token vào response.
- Người dùng hiện được nhận diện bằng header `X-User-Id`; đây là cơ chế tạm thời trong snapshot.

## 4. Luồng nghiệp vụ chính

1. Người dùng chọn repository đã thêm vào workspace và yêu cầu đồng bộ.
2. Frontend gọi `POST /api/repositories/{id}/sync` với `X-User-Id`; body có thể bỏ trống.
3. Controller chuyển request đến `RepositorySyncService`.
4. Service xác minh repository tồn tại và thuộc người dùng hiện tại. Nếu không thuộc người dùng, trả `403`.
5. Service lấy access token GitHub. Nếu token bị thu hồi/hết hạn, đánh dấu connection `INVALID` và trả lỗi phù hợp.
6. Trạng thái repository chuyển `SYNCING`.
7. `GitHubRepositoryFetcher` lấy thông tin repository, commit nhánh, recursive tree, nội dung file hỗ trợ, thống kê ngôn ngữ và recent commits.
8. Fetcher lọc file không phù hợp, kiểm tra kích thước và đường dẫn, sắp xếp file theo `path`, tạo `RepositorySnapshot`.
9. Khi thành công, service cập nhật `CONNECTED`, `lastSyncedAt`, `defaultBranch` và `fullName` nếu repository đổi tên.
10. Kết quả gần nhất được giữ trong bộ nhớ của service.
11. Frontend nhận metadata snapshot không có `content`. Khi bước phân tích cần code, backend gọi `GET .../sync/latest/analysis-input` để lấy payload có nội dung.

### Sơ đồ tương tác

```text
Frontend
  -> RepositorySyncController
  -> RepositorySyncService
      -> xác minh user/repository
      -> lấy GitHub access token
      -> GitHubRepositoryFetcher
          -> GitHub REST API
          -> PathFilter / LanguageDetector
          -> RepositorySnapshot
      -> cập nhật repository status
      -> cache snapshot mới nhất trong memory
  <- SyncResultResponse (không có file content)

Analyzer integration:
  -> GET /sync/latest/analysis-input
  <- { scope, target, files: [{ path, language, content }] }
```

## 5. REST API

Tất cả endpoint đồng bộ yêu cầu `X-User-Id` và kiểm tra quyền sở hữu repository.

| Method | Endpoint | Ý nghĩa |
|---|---|---|
| `POST` | `/api/repositories/{id}/sync` | Bắt đầu đồng bộ repository |
| `GET` | `/api/repositories/{id}/sync/latest` | Lấy metadata của lần đồng bộ gần nhất |
| `GET` | `/api/repositories/{id}/sync/latest/analysis-input` | Lấy payload có nội dung file để chuyển cho analyzer |

Body `POST /sync` không bắt buộc. Ví dụ:

```json
{
  "branch": "develop",
  "includeContent": true,
  "maxFiles": 50
}
```

Body rỗng hoặc `{}` dùng nhánh mặc định và các giá trị mặc định. `maxFiles` hợp lệ trong khoảng `1..1000`; sai trả `400 INVALID_REQUEST`.

### Response contract

`RepositorySnapshot` có các nhóm dữ liệu:
- `repository`: GitHub repo id, full name, owner, name, description, private/archived, default branch, URL, primary language, size, pushedAt.
- `branch`: nhánh thực tế được đồng bộ.
- `headCommit`: SHA, message, author name/login, committedAt, URL.
- `languages`: map ngôn ngữ sang số byte.
- `files`: `path`, `sha`, `size`, `language`, `content`, `skipReason`.
- `recentCommits`: các commit gần nhất.
- `stats`: `totalFilesInRepo`, `filesSelected`, `filesWithContent`, `filesIgnored`, `treeTruncated`, `fileLimitReached`.
- `warnings`: danh sách mã và thông điệp cảnh báo.
- `fetchedAt`: thời điểm đồng bộ.

`files` luôn sắp xếp theo `path`. File có `content != null` mới là file phân tích được. API trả cho frontend (`SyncResultResponse`) không chứa nội dung file; nội dung chỉ có trong `analysis-input`.

### Payload phân tích

`AnalysisInput.from(snapshot)` chỉ chọn `analyzableFiles()` và tạo cấu trúc:

```json
{
  "scope": "repository",
  "target": "owner/repository",
  "files": [
    {
      "path": "src/example.py",
      "language": "python",
      "content": "..."
    }
  ]
}
```

`language` dùng chữ thường (`java`, `python`). `target` là full repository name. Không dùng đường dẫn local vì analyzer chạy ở service/container độc lập.

## 6. Quy tắc lọc file

- Chỉ tải nội dung Java và Python theo cấu hình mặc định.
- Bỏ qua thư mục/phần sinh tự động hoặc môi trường: `node_modules`, `venv`, `__pycache__`, `.git`, `.idea`, `target`, `build`, `dist` (trừ trường hợp nằm trong `src` theo quy tắc lọc của code).
- Bỏ qua `*.min.js`, file nhị phân, file lớn hơn giới hạn mặc định 200,000 bytes.
- Chặn đường dẫn bất thường như `../` hoặc đường dẫn tuyệt đối `/`.
- File không tải nội dung có thể có `skipReason`: `NOT_REQUESTED`, `TOO_LARGE`, `BINARY`, `UNAVAILABLE`.
- Danh sách file được sắp xếp ổn định theo `path`.

## 7. Tùy chọn đồng bộ

| Tùy chọn | Mặc định | Quy tắc |
|---|---:|---|
| `branch` | `null` | `null` nghĩa là nhánh mặc định |
| `includeContent` | `true` | `false` chỉ lấy danh sách/metadata |
| `maxFiles` | `200` | Tối đa `1000` |
| `maxFileSizeBytes` | `200000` | File vượt giới hạn không tải nội dung |
| `recentCommitLimit` | `20` | Khoảng hợp lệ `0..100` |
| `languages` | `java`, `python` | Ngôn ngữ được lấy nội dung |

## 8. Cảnh báo không làm thất bại đồng bộ

| Code | Ý nghĩa |
|---|---|
| `ARCHIVED_REPOSITORY` | Repository đã archive |
| `REPOSITORY_RENAMED` | Repository đổi tên |
| `TREE_TRUNCATED` | GitHub trả cây file chưa đầy đủ |
| `FILE_LIMIT_REACHED` | Đạt `maxFiles` |
| `NO_SOURCE_FILES` | Không tìm thấy file Java/Python phù hợp |
| `FILE_UNAVAILABLE` / `MORE_FILES_UNAVAILABLE` | Một hoặc nhiều file không tải được |
| `UNSAFE_PATHS_SKIPPED` | Đã bỏ qua đường dẫn không an toàn |
| `LANGUAGES_UNAVAILABLE` | Không lấy được thống kê ngôn ngữ |
| `COMMITS_UNAVAILABLE` | Không lấy được danh sách commit gần đây |

Cảnh báo được trả trong snapshot; bản thân cảnh báo không đồng nghĩa request thất bại.

## 9. Xử lý lỗi

Lỗi dùng `RepositorySyncException` và được `GlobalExceptionHandler` chuyển thành JSON dạng:

```json
{
  "status": 404,
  "code": "REPOSITORY_NOT_FOUND",
  "message": "Human-readable message",
  "timestamp": "ISO-8601"
}
```

| Code | HTTP | Nguyên nhân / hành vi |
|---|---:|---|
| `INVALID_REQUEST` | 400 | Tham số không hợp lệ |
| `INVALID_REPOSITORY` | 400 | Tên repo sai định dạng `owner/repo` |
| `TOKEN_INVALID` | 401 | Token hết hạn/bị thu hồi; đánh dấu GitHub connection `INVALID` |
| `ACCESS_DENIED` | 403 | App không có quyền truy cập |
| `REPOSITORY_NOT_FOUND` | 404 | Repo bị xóa/đổi tên/chưa cài app |
| `BRANCH_NOT_FOUND` | 404 | Nhánh không tồn tại |
| `EMPTY_REPOSITORY` | 409 | Repo chưa có commit |
| `RATE_LIMITED` | 429 | Hết quota; giữ thông tin `Retry-After`/thời điểm thử lại |
| `GITHUB_UNAVAILABLE` | 503 | Timeout, mất mạng hoặc GitHub 5xx |
| `UNEXPECTED_GITHUB_RESPONSE` | 502 | GitHub trả dữ liệu không đúng định dạng |

Lỗi không retryable không tự động lặp lại. `RATE_LIMITED` và `GITHUB_UNAVAILABLE` có thể retry theo thời điểm/điều kiện được trả về.

## 10. Trạng thái repository

| Thời điểm | Trạng thái |
|---|---|
| Đang gọi GitHub | `SYNCING` |
| Đồng bộ thành công | `CONNECTED` |
| `REPOSITORY_NOT_FOUND`, `ACCESS_DENIED`, `INVALID_REPOSITORY` | `ERROR` |
| Lỗi khác | Giữ trạng thái trước đó |
| Token hỏng | GitHub connection chuyển `INVALID` |

Khi thành công, cập nhật `lastSyncedAt`, `defaultBranch`, và `fullName` nếu repo đã đổi tên.

## 11. Giới hạn hiện tại phải giữ nguyên khi tái tạo

- Snapshot mới nhất chỉ nằm trong memory; restart service làm mất kết quả và phải sync lại.
- Tải nội dung file tuần tự, mỗi file cần một lần gọi GitHub API; repository khoảng 100 file nguồn có thể mất 10–30 giây.
- Đồng bộ hiện chạy đồng bộ trong request, chưa có background job.
- Chưa có webhook push/pull_request, HMAC signature, Kafka event, hay lưu lịch sử snapshot vào database.
- Người dùng hiện được nhận diện bằng `X-User-Id`, chưa thay bằng JWT.

## 12. Kiểm thử và tiêu chí chấp nhận

Tái tạo tối thiểu các test sau:
1. Snapshot thành công có repo, branch, HEAD commit, file, language stats, recent commits.
2. Nhánh tùy chỉnh được dùng đúng.
3. `includeContent=false` không tải nội dung.
4. `maxFiles` và file-size limit được áp dụng.
5. File được sắp xếp theo path; BOM được xử lý.
6. Bỏ qua thư mục/file không hợp lệ, binary, file quá lớn và unsafe path.
7. Warning archived/renamed/tree truncated/no source/file unavailable/language unavailable.
8. Xử lý 401, 403, 404, empty repo, branch missing, 429, timeout, 5xx, dữ liệu GitHub sai.
9. Endpoint kiểm tra quyền sở hữu; người khác nhận 403.
10. `POST sync` cập nhật trạng thái `SYNCING` rồi `CONNECTED`; lỗi tương ứng cập nhật status.
11. `/sync/latest` trả 404 khi chưa có snapshot.
12. `/analysis-input` chỉ chứa file có nội dung và có đúng `scope`, `target`, `files`.

## 13. Hướng dẫn cho AI tái tạo code

- Tái tạo theo đúng các package/class ở mục 2; không dồn fetcher, service và controller vào một class.
- Dùng GitHub REST API; mọi dữ liệu của snapshot phải cùng commit SHA.
- Giữ phân tách response frontend (metadata) và payload phân tích (nội dung code).
- Giữ chính xác tên endpoint, header, field, enum/error code và default values ở tài liệu này.
- Không tự thêm database persistence, webhook, Kafka, async jobs hay JWT vì đó là các phần chưa có trong snapshot LD-63.
- Khi thiếu chi tiết implementation không được mô tả ở đây, ưu tiên đọc source files nêu ở mục 2 thay vì tự bịa hành vi.
