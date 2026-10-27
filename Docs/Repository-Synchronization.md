# Đồng bộ repository (Repository Synchronization)

| Mục | Nội dung |
|---|---|
| Người làm | Đặng Lê Hiển Hải (TV2), phần API làm cùng Minh |
| Jira | Story LD-24; task LD-63 (Sprint 2) |
| Code | `services/github-integration-service`, package `com.livingdocs.github` (`sync`, `service`, `controller`, `client`, `dto`) |
| Phụ thuộc | GitHub Account Connection (nền tảng, `GitHubClient`, `GitHubApiException`, `GitHubConnectionService.getActiveConnection/findConnection/markInvalid`), Repository Management (`ConnectedRepository`, `RepositoryStatus`) |

## 1. Mục tiêu

Chủ repo yêu cầu đồng bộ một repo đã thêm vào workspace. Hệ thống lấy code mới nhất của repo từ GitHub **theo đúng một commit**, chọn các file nguồn Java và Python, tải nội dung, kiểm tra dữ liệu, cập nhật trạng thái repo và giữ kết quả lần gần nhất trong bộ nhớ để hiển thị và để gửi sang phân tích code.

## 2. Gọi GitHub (thêm vào `client/GitHubClient`)

Tất cả dùng `apiClient` (header `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`), Bearer token nếu có (token rỗng thì gọi ẩn danh, chỉ đọc được repo public), bọc trong `call()` để lỗi thành `GitHubApiException`.

| Hàm | Lời gọi | Kiểu trả về |
|---|---|---|
| `getRepositoryDetails(token, owner, repo)` | `GET /repos/{owner}/{repo}` | `GitHubRepoDetails` |
| `getCommit(token, owner, repo, ref)` | `GET /repos/{owner}/{repo}/commits/{ref}` (repo rỗng: GitHub trả 409) | `GitHubCommit` |
| `getTree(token, owner, repo, treeSha)` | `GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1` | `GitHubTree` |
| `getBlob(token, owner, repo, blobSha)` | `GET /repos/{owner}/{repo}/git/blobs/{sha}` | `GitHubBlob` |
| `getLanguages(token, owner, repo)` | `GET /repos/{owner}/{repo}/languages` | `Map<String, Long>` (giữ thứ tự, `LinkedHashMap`; null thành map rỗng) |
| `listCommits(token, owner, repo, ref, limit)` | `GET /repos/{owner}/{repo}/commits?sha={ref}&per_page={n}`, n = limit giới hạn trong 1..100 | `List<GitHubCommit>` (null thành rỗng) |

Record (đều có `@JsonIgnoreProperties(ignoreUnknown = true)`, tên JSON snake_case qua `@JsonProperty`):

- `GitHubRepoDetails(Long id, String name, String full_name, Owner owner, String description, boolean private, boolean archived, boolean disabled, String default_branch, String html_url, String language, Long size, Instant pushed_at)`, `Owner(String login)`.
- `GitHubCommit(String sha, String html_url, Detail commit, Account author)`, `Detail(String message, Person author, Person committer, TreeRef tree)`, `Person(String name, String email, Instant date)`, `TreeRef(String sha)`, `Account(String login)`.
- `GitHubTree(String sha, boolean truncated, List<Entry> tree)`, `Entry(String path, String mode, String type, String sha, Long size)`; `type` là `blob`, `tree` hoặc `commit`.
- `GitHubBlob(String sha, Long size, String encoding, String content)`.

## 3. Mô hình dữ liệu (`sync/`)

**`SyncOptions`** (record): `String branch` (null = nhánh mặc định), `boolean includeContent`, `int maxFiles`, `long maxFileSizeBytes`, `int recentCommitLimit`, `Set<String> languages`.

- Hằng số: `DEFAULT_MAX_FILES = 200`, `MAX_FILES_LIMIT = 1000`, `DEFAULT_MAX_FILE_SIZE_BYTES = 200_000`, `DEFAULT_RECENT_COMMITS = 20`, `ANALYZER_LANGUAGES = Set.of("java", "python")`.
- Constructor kiểm tra: `maxFiles` ngoài 1..1000, `maxFileSizeBytes < 1`, `recentCommitLimit` ngoài 0..100 thì ném `RepositorySyncException(INVALID_REQUEST, ...)`. `branch` toàn khoảng trắng thành null. `languages` rỗng thành `ANALYZER_LANGUAGES`, còn lại trim và viết thường.
- `defaults()` = `(null, true, 200, 200_000, 20, ANALYZER_LANGUAGES)`; có `withBranch`, `withIncludeContent`, `withMaxFiles`, `withMaxFileSizeBytes`.

**`SyncErrorCode`** (enum, kèm `HttpStatus httpStatus()` và `boolean retryable()` = đúng với `RATE_LIMITED`, `GITHUB_UNAVAILABLE`):

| Mã | HTTP | Ý nghĩa |
|---|---|---|
| `INVALID_REQUEST` | 400 | Tham số đồng bộ sai |
| `INVALID_REPOSITORY` | 400 | Tên repo sai dạng `owner/repo` |
| `TOKEN_INVALID` | 401 | Token GitHub hết hạn hoặc bị thu hồi |
| `ACCESS_DENIED` | 403 | GitHub App không có quyền, hoặc repo bị GitHub vô hiệu hoá |
| `REPOSITORY_NOT_FOUND` | 404 | Repo bị xoá, đổi tên, hoặc chưa cài app |
| `BRANCH_NOT_FOUND` | 404 | Nhánh không tồn tại |
| `EMPTY_REPOSITORY` | 409 | Repo chưa có commit |
| `RATE_LIMITED` | 429 | Hết lượt gọi GitHub API |
| `GITHUB_UNAVAILABLE` | 503 | Mất mạng, timeout, GitHub lỗi 5xx |
| `UNEXPECTED_GITHUB_RESPONSE` | 502 | GitHub trả dữ liệu sai |

**`RepositorySyncException extends RuntimeException`**: `SyncErrorCode code`, `Instant retryAt` (chỉ có khi `RATE_LIMITED`); constructor `(code, message)` và `(code, message, retryAt, cause)`.

**`SyncWarning(String code, String message)`**: cảnh báo không làm hỏng đồng bộ.

**`RepositorySnapshot`** (record): `RepositoryInfo repository`, `String branch`, `CommitInfo headCommit`, `Map<String, Long> languages`, `List<SourceFile> files` (sắp theo path), `List<CommitInfo> recentCommits`, `SyncStats stats`, `List<SyncWarning> warnings`, `Instant fetchedAt`. Compact constructor copy thành bản không sửa được (languages giữ thứ tự). Hàm `analyzableFiles()` trả các file có nội dung.

- `RepositoryInfo(Long githubRepoId, String fullName, String owner, String name, String description, boolean privateRepo, boolean archived, String defaultBranch, String htmlUrl, String primaryLanguage, Long sizeKb, Instant pushedAt)`.
- `CommitInfo(String sha, String message, String authorName, String authorLogin, Instant committedAt, String htmlUrl)`. **Không lưu email** tác giả.
- `SourceFile(String path, String sha, long size, String language, String content, SkipReason skipReason)`, `hasContent()` = `content != null`.
- `SkipReason`: `NOT_REQUESTED` (không yêu cầu tải nội dung), `TOO_LARGE`, `BINARY`, `UNAVAILABLE`.
- `SyncStats(int totalFilesInRepo, int filesSelected, int filesWithContent, int filesIgnored, boolean treeTruncated, boolean fileLimitReached)`.

## 4. Lọc file

**`LanguageDetector.detect(path)`**: lấy tên file sau dấu `/` cuối, đuôi là phần sau dấu chấm cuối cùng. Path null hoặc rỗng, không có dấu chấm, dấu chấm cuối nằm ở đầu tên (kiểu `.gitignore`) hoặc ở cuối tên (kiểu `weird.`) thì trả null. Đuôi (viết thường) sang ngôn ngữ: `java`→java, `py`→python, `js`/`jsx`/`mjs`/`cjs`→javascript, `ts`/`tsx`→typescript, `kt`/`kts`→kotlin, `go`→go, `rb`→ruby, `php`→php, `cs`→csharp, `c`/`h`→c, `cpp`/`cc`/`cxx`/`hpp`→cpp, `rs`→rust, `swift`→swift, `scala`→scala, `sql`→sql. Đuôi khác trả null.

**`PathFilter`**:

- `isSafe(path)`: false nếu null, rỗng, bắt đầu bằng `/`, chứa `\`, có đoạn rỗng, `.` hoặc `..` (tách theo `/`, giữ đoạn rỗng), hoặc có ký tự điều khiển.
- `isIgnored(path)`: true nếu không an toàn; hoặc một thư mục trong đường dẫn (không xét tên file, so sánh viết thường) thuộc `ALWAYS_IGNORED` = `.git`, `.github`, `.idea`, `.vscode`, `.gradle`, `.mvn`, `node_modules`, `bower_components`, `venv`, `.venv`, `__pycache__`, `.pytest_cache`, `.tox`, `site-packages`, `.next`, `.nuxt`; hoặc thuộc `BUILD_OUTPUT` = `target`, `build`, `dist`, `out`, `bin`, `obj`, `vendor`, `coverage` **khi chưa đi qua thư mục `src`** (để giữ `src/main/java/com/acme/build/Builder.java`); hoặc tên file kết thúc `.min.js` hay `.bundle.js`.

## 5. Lấy dữ liệu: `sync/GitHubRepositoryFetcher` (`@Service`)

`RepositorySnapshot fetch(String accessToken, String fullName, SyncOptions options)` (options null thì dùng `defaults()`):

1. **Kiểm tra tên**: khớp regex `^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$` và phần repo khác `.`, `..`; sai thì `INVALID_REPOSITORY` (không gọi GitHub).
2. **Thông tin repo** (bắt buộc): `getRepositoryDetails`. Thiếu `id` hoặc `full_name` thì `UNEXPECTED_GITHUB_RESPONSE`. `disabled` thì `ACCESS_DENIED`. `archived` thì cảnh báo `ARCHIVED_REPOSITORY`. Nhánh = `options.branch` hoặc `default_branch`; rỗng thì `EMPTY_REPOSITORY`. Từ đây dùng `owner/repo` theo `full_name` GitHub trả về (repo có thể đã đổi tên).
3. **Commit mới nhất** (bắt buộc): `getCommit(..., branch)`. Thiếu `sha` hoặc `commit.tree.sha` thì `UNEXPECTED_GITHUB_RESPONSE`.
4. **Cây thư mục** (bắt buộc): `getTree(..., commit.tree.sha)`. Null thì `UNEXPECTED_GITHUB_RESPONSE`. `truncated` thì cảnh báo `TREE_TRUNCATED`.
5. **Chọn file**: lấy các entry `type = "blob"` có path, bỏ symlink (`mode = "120000"`), sắp theo path. Với từng file:
   - Không an toàn (`PathFilter.isSafe` sai): bỏ qua, đếm `unsafe`.
   - Không nhận diện được ngôn ngữ, ngôn ngữ không thuộc `options.languages`, hoặc `PathFilter.isIgnored`: bỏ qua.
   - Đã đủ `maxFiles`: bỏ qua, đánh dấu `limitReached`.
   - `includeContent = false`: thêm file với `NOT_REQUESTED`. `size > maxFileSizeBytes`: thêm với `TOO_LARGE`.
   - Còn lại tải nội dung `getBlob(blob sha)`:
     - Lỗi GitHub: dịch lỗi (mục 6). Nếu là `TOKEN_INVALID`, `RATE_LIMITED`, `GITHUB_UNAVAILABLE` hoặc `ACCESS_DENIED` thì dừng cả lần đồng bộ (ném lỗi). Lỗi khác: file `UNAVAILABLE` kèm cảnh báo `FILE_UNAVAILABLE` "`<path>`: `<message>`".
     - Giải mã: `encoding` null hoặc `base64` thì dùng `Base64.getMimeDecoder()` (nội dung GitHub có xuống dòng); encoding khác thì lấy bytes UTF-8. Không giải mã được thì `UNAVAILABLE` + cảnh báo "GitHub trả về nội dung không đọc được."
     - Có byte 0 trong 8000 byte đầu thì `BINARY`.
     - Còn lại: chuỗi UTF-8, bỏ ký tự BOM `﻿` ở đầu nếu có.
   - Cảnh báo cuối bước: `UNSAFE_PATHS_SKIPPED` ("n file có đường dẫn bất thường đã bị bỏ qua.") nếu có; `FILE_LIMIT_REACHED` nếu chạm `maxFiles`; `NO_SOURCE_FILES` nếu không chọn được file nào; tối đa 10 cảnh báo `FILE_UNAVAILABLE`, phần còn lại gộp thành `MORE_FILES_UNAVAILABLE` ("Còn n file khác không tải được.").
6. **Thông tin phụ** (không bắt buộc): `getLanguages` lỗi thì cảnh báo `LANGUAGES_UNAVAILABLE`, dùng map rỗng. Nếu `recentCommitLimit > 0` thì `listCommits`, lỗi thì cảnh báo `COMMITS_UNAVAILABLE`. Riêng lỗi `TOKEN_INVALID` hoặc `RATE_LIMITED` ở bước này vẫn ném ra.
7. **Kết quả**: `SyncStats(tổng số blob, số file chọn, số file có nội dung, số file bỏ qua, truncated, limitReached)`; `RepositoryInfo` lấy từ chi tiết repo (owner lấy `owner.login`, không có thì phần trước `/`); `CommitInfo` lấy `sha`, `commit.message`, `commit.author.name`, `author.login`, ngày của author (không có thì của committer), `html_url`; `fetchedAt = now`.
8. **Kiểm tra** bằng `SnapshotVerifier.verify(tênĐãYêuCầu, snapshot)` rồi ghi log và trả về.

**`SnapshotVerifier`** (lỗi thì ném `UNEXPECTED_GITHUB_RESPONSE` "Dữ liệu đồng bộ không hợp lệ: ..."):

- Repo phải có `githubRepoId` và `fullName`. `fullName` khác tên đã yêu cầu (không phân biệt hoa thường) thì thêm cảnh báo `REPOSITORY_RENAMED` ("Repository đã đổi tên từ A thành B...").
- Phải có tên nhánh; SHA commit khớp `^[0-9a-f]{40}([0-9a-f]{24})?$`.
- Mỗi file: path an toàn, không trùng, SHA hợp lệ, có ngôn ngữ, size ≥ 0, và có nội dung khi và chỉ khi `skipReason` null.
- `stats.filesSelected` = số file, `stats.filesWithContent` = số file có nội dung, `totalFilesInRepo ≥ filesSelected`.

## 6. Dịch lỗi GitHub sang `RepositorySyncException`

Xét theo thứ tự:

| Điều kiện | Mã |
|---|---|
| Lỗi mạng (`isNetworkError`) | `GITHUB_UNAVAILABLE` |
| `isRateLimited` | `RATE_LIMITED`, `retryAt = e.retryAt()` |
| HTTP 401 | `TOKEN_INVALID` |
| HTTP 403 | `ACCESS_DENIED` ("hãy cài app cho repo này và cấp quyền Contents (read)") |
| HTTP 404 hoặc 422 khi đang đọc commit của nhánh | `BRANCH_NOT_FOUND` |
| HTTP 404 | `REPOSITORY_NOT_FOUND` |
| HTTP 409 | `EMPTY_REPOSITORY` |
| HTTP ≥ 500 | `GITHUB_UNAVAILABLE` |
| Còn lại | `UNEXPECTED_GITHUB_RESPONSE` |

Thông điệp ghi rõ bước đang làm (đọc thông tin repository, đọc commit mới nhất của nhánh, đọc danh sách file, tải nội dung file, đọc thống kê ngôn ngữ, đọc lịch sử commit).

## 7. Xử lý nghiệp vụ: `service/RepositorySyncService` (`@Service`)

Phụ thuộc: `ConnectedRepositoryRepository`, `GitHubConnectionService`, `GitHubRepositoryFetcher`. Kết quả gần nhất: `Map<UUID, RepositorySnapshot> latestResults = new ConcurrentHashMap<>()`. Method `sync` **không** đặt `@Transactional` cho cả hàm: mỗi lần lưu repo là một transaction ngắn, để trạng thái `SYNCING` thấy được ngay.

**`sync(userId, repositoryId, options)`**:

1. Tìm repo của người dùng: không có thì `ApiException.notFound("Không tìm thấy repository <id>")`; kết nối của người dùng khác `connectionId` của repo thì `ApiException.forbidden("Repository này không thuộc kết nối GitHub của bạn.")`.
2. `connection = connectionService.getActiveConnection(userId)` (tự làm mới token).
3. Ghi nhớ trạng thái cũ (nếu đang `SYNCING` do lần trước bị dừng giữa chừng thì coi là `CONNECTED`), đặt `SYNCING`, lưu.
4. `snapshot = fetcher.fetch(token, repo.fullName, options)`.
5. Thành công: cập nhật `fullName`, `defaultBranch`, `privateRepo`, `htmlUrl` theo GitHub, `status = CONNECTED`, `lastSyncedAt = snapshot.fetchedAt`, lưu, `latestResults.put(repositoryId, snapshot)`, trả snapshot.
6. `RepositorySyncException`: nếu `TOKEN_INVALID` thì `connectionService.markInvalid(connection)`. Trạng thái repo = `ERROR` nếu mã thuộc {`REPOSITORY_NOT_FOUND`, `ACCESS_DENIED`, `INVALID_REPOSITORY`}, ngược lại trả về trạng thái cũ. Lưu rồi ném lại lỗi.
7. `RuntimeException` khác: trả về trạng thái cũ, lưu, ném lại.

**`latest(userId, repositoryId)`**: kiểm tra chủ repo như bước 1; chưa có kết quả thì `ApiException.notFound("Repository này chưa được đồng bộ lần nào (hoặc service vừa khởi động lại). Hãy gọi POST /api/repositories/<id>/sync trước.")`.

Trong `GlobalExceptionHandler` thêm handler cho `RepositorySyncException`: HTTP lấy từ `code.httpStatus()`, body `ErrorResponse(status, code.name(), message, now)`; nếu có `retryAt` thì thêm header `Retry-After` = số giây còn lại (tối thiểu 1); lỗi 5xx thì ghi log cảnh báo.

## 8. API: `controller/RepositorySyncController`

`@RestController`, `@Tag(name = "Repository Sync")`. Header `X-User-Id`, `id` là UUID.

| Method | Path | Body | Kết quả |
|---|---|---|---|
| POST | `/api/repositories/{id}/sync` | Không bắt buộc: `{"branch": "develop", "includeContent": true, "maxFiles": 50}` | `200` `SyncResultResponse` |
| GET | `/api/repositories/{id}/sync/latest` | | `200` `SyncResultResponse` của lần gần nhất |

- `dto/SyncRequest(String branch, Boolean includeContent, Integer maxFiles)` với `toOptions()`: bắt đầu từ `SyncOptions.defaults()`, field nào khác null thì áp vào (branch có trim). Body null thì dùng `defaults()`.
- `dto/SyncResultResponse(RepositoryInfo repository, String branch, CommitInfo headCommit, Map<String, Long> languages, List<FileItem> files, SyncStats stats, List<SyncWarning> warnings, Instant syncedAt)`, `FileItem(String path, String language, long size, boolean analyzable, String skipReason)`; `static from(RepositorySnapshot)`. **Không kèm nội dung file** (nội dung chỉ có ở API của chức năng Repository Analysis Input).
- Swagger: khai báo request body không bắt buộc với 2 ví dụ: `{}` và `{"branch": "develop", "maxFiles": 50}`.

Ví dụ response rút gọn:

```json
{"repository": {"githubRepoId": 101, "fullName": "LivingDocs-Team/Livingdocs", "owner": "LivingDocs-Team",
  "name": "Livingdocs", "privateRepo": false, "archived": false, "defaultBranch": "main", "...": "..."},
 "branch": "main",
 "headCommit": {"sha": "<40 ký tự>", "message": "...", "authorName": "...", "authorLogin": "...",
  "committedAt": "...", "htmlUrl": "..."},
 "languages": {"Java": 152340, "Python": 20110},
 "files": [{"path": "app/main.py", "language": "python", "size": 4210, "analyzable": true, "skipReason": null},
           {"path": "big/Generated.java", "language": "java", "size": 350000, "analyzable": false, "skipReason": "TOO_LARGE"}],
 "stats": {"totalFilesInRepo": 106, "filesSelected": 60, "filesWithContent": 60, "filesIgnored": 46,
  "treeTruncated": false, "fileLimitReached": false},
 "warnings": [], "syncedAt": "2026-10-13T16:39:13Z"}
```

## 9. Lỗi

Lỗi có dạng `{status, code, message, timestamp}`.

| Mã | HTTP | Khi nào | Trạng thái repo sau đó |
|---|---|---|---|
| `INVALID_REQUEST` | 400 | `maxFiles` ngoài 1..1000 | Không đổi (không gọi GitHub) |
| `BAD_REQUEST` | 400 | Body sai JSON hoặc sai kiểu, `id` không phải UUID | Không đổi |
| `INVALID_REPOSITORY` | 400 | Tên repo sai dạng | `ERROR` |
| `TOKEN_INVALID` | 401 | Token hỏng | Giữ nguyên, kết nối chuyển `INVALID` |
| `ACCESS_DENIED` | 403 | Không có quyền, repo bị khoá | `ERROR` |
| `FORBIDDEN` | 403 | Repo không phải của người dùng | Không đổi |
| `REPOSITORY_NOT_FOUND` | 404 | Repo không còn trên GitHub | `ERROR` |
| `BRANCH_NOT_FOUND` | 404 | Nhánh không tồn tại | Giữ nguyên |
| `NOT_FOUND` | 404 | Repo không có trong hệ thống; xem kết quả khi chưa đồng bộ | Không đổi |
| `EMPTY_REPOSITORY` | 409 | Repo chưa có commit | Giữ nguyên |
| `GITHUB_NOT_CONNECTED` | 409 | Chưa kết nối GitHub hoặc kết nối không còn `ACTIVE` | Không đổi |
| `RATE_LIMITED` | 429 | Hết lượt gọi API, có header `Retry-After` | Giữ nguyên |
| `UNEXPECTED_GITHUB_RESPONSE` | 502 | GitHub trả dữ liệu sai | Giữ nguyên |
| `GITHUB_UNAVAILABLE` | 503 | Mất mạng, GitHub lỗi 5xx | Giữ nguyên |

## 10. Test cần có

- `GitHubRepositoryFetcherTest` (25, Mockito mock `GitHubClient`): lấy đúng thông tin repo, commit, file đã lọc và sắp xếp, nội dung (bỏ BOM), thống kê, ngôn ngữ, commit gần nhất; `includeContent = false` thì không tải nội dung; tôn trọng `maxFiles`; chọn nhánh khác; cảnh báo repo archived, repo đổi tên, cây bị cắt, không có file nguồn, đường dẫn bất thường, một file không tải được (các file khác vẫn tải), không lấy được thống kê ngôn ngữ; `recentCommitLimit = 0` thì không gọi API lịch sử commit; tên repo sai thì không gọi GitHub; 404 repo, 401, 403, repo bị vô hiệu hoá, rate limit (có thời điểm thử lại), rate limit giữa lúc tải file (dừng đồng bộ), repo rỗng 409, nhánh không tồn tại 422, mất mạng, GitHub 5xx, commit trả về sai dạng bị `SnapshotVerifier` chặn, tham số sai.
- `FileSelectionRulesTest` (5): nhận diện ngôn ngữ theo đuôi (`APP/MAIN.PY` là python, `README.md`, `.gitignore`, `Makefile`, `weird.` là null); bỏ qua thư viện và thư mục build; giữ code thật (`src/main/java/com/acme/build/Builder.java`, `scripts/build.py`); chặn đường dẫn bất thường; `SyncOptions` chuẩn hoá đầu vào.
- `GitHubClientRepositoryApiTest` (7, HTTP server giả): đọc đúng JSON chi tiết repo; đọc commit, tree, blob, languages, danh sách commit; 404 giữ mã lỗi; nhận diện rate limit qua header; 403 không kèm rate limit thì không phải rate limit; nhận diện 401; không có token thì không gửi header `Authorization`.
- `RepositorySyncApiTest` (8, `@SpringBootTest` + MockMvc + H2, `@MockitoBean GitHubClient`, mỗi test dùng user và workspace riêng): đồng bộ thành công, response không kèm nội dung, trạng thái và `lastSyncedAt` được cập nhật; `/sync/latest` và `/sync/latest/analysis-input` trả kết quả lần gần nhất; người khác bị `403`, repo không tồn tại `404`; body sai `400` và không gọi GitHub; nhánh không tồn tại `404` và giữ trạng thái; repo bị xoá trên GitHub thì repo `ERROR`; token bị thu hồi thì kết nối `INVALID`; rate limit thì `429` kèm `Retry-After`, giữ trạng thái.
- `GitHubRepositoryFetcherLiveTest`: chỉ chạy khi có biến môi trường `GITHUB_LIVE_TEST=true` (`@EnabledIfEnvironmentVariable`), đồng bộ repo thật (`GITHUB_LIVE_REPO`, mặc định `LivingDocs-Team/Livingdocs`, token lấy từ `GITHUB_TOKEN` nếu có) với `maxFiles = 25`, kiểm tra SHA 40 ký tự, có file và có file phân tích được.

## 11. Tiêu chí chấp nhận

- Đồng bộ thành công: repo `CONNECTED`, `lastSyncedAt` có giá trị, response có commit SHA 40 ký tự, danh sách file không kèm nội dung.
- Mọi dữ liệu lấy theo cùng một commit; chỉ file Java và Python ngoài thư mục bị bỏ qua mới được chọn.
- Lỗi GitHub trả đúng mã trong mục 9; lỗi tạm thời (`RATE_LIMITED`, `GITHUB_UNAVAILABLE`) không đổi trạng thái repo.
- Chạy với GitHub thật trên repo nhóm (13/10/2026): 106 file, lấy đủ nội dung 60/60 file Java và Python.
