# FR-GH-03 Đồng bộ repository từ GitHub

| Mục | Nội dung |
|---|---|
| Feature Jira | LD-24 Repository Synchronization (epic LD-6 GitHub Integration) |
| Task đã làm | LD-63: LD-64 Implement Repository Sync Service, LD-67 Test Repository Synchronization |
| Người thực hiện | Lê Hiền Hải Đăng (LD-64, LD-67). Cùng PR #20, Minh Nguyễn Lê (LD-65, LD-66) sửa giao diện frontend và tách endpoint workspace |
| Thành phần | GitHub Integration Service (cổng 8082): `controller/RepositorySyncController`, `service/RepositorySyncService`, package `sync/` (`GitHubRepositoryFetcher`, `PathFilter`, `LanguageDetector`, `SnapshotVerifier`, `SyncOptions`, `RepositorySnapshot`, `SyncErrorCode`), các hàm đọc repo trong `client/GitHubClient` |
| Tác nhân | Developer (nút **Sync now** trên trang Repository Management, đi qua Backend BFF); GitHub REST API |
| Phụ thuộc | FR-GH-01 (kết nối `ACTIVE`, tự làm mới token), FR-GH-02 (repo phải có trong workspace) |

## 1. Mô tả

Chủ repo yêu cầu đồng bộ một repo đã thêm vào workspace. Hệ thống đọc repo từ GitHub **theo đúng một commit** của nhánh được chọn, chọn các file nguồn Java và Python, tải nội dung, kiểm tra dữ liệu, cập nhật trạng thái repo và giữ kết quả lần gần nhất trong bộ nhớ để hiển thị và để chuyển sang phân tích code (FR-GH-04). Lỗi của một file không làm hỏng cả lần đồng bộ.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-GH-03.1 | Chỉ chủ repo được đồng bộ và xem kết quả đồng bộ: repo không có trong hệ thống thì `404`; repo thuộc kết nối GitHub của người khác thì `403`. |
| FR-GH-03.2 | Trước khi gọi GitHub, lấy kết nối `ACTIVE` của người dùng và làm mới token nếu cần (FR-GH-01.8). |
| FR-GH-03.3 | Body không bắt buộc, gồm `branch` (bỏ trống hoặc toàn khoảng trắng = nhánh mặc định), `includeContent` (mặc định `true`), `maxFiles` (1–1000, mặc định 200). Các giới hạn còn lại cố định: file tối đa 200.000 byte, 20 commit gần nhất, ngôn ngữ `java` và `python`. Tham số sai thì `400 INVALID_REQUEST` và không gọi GitHub. |
| FR-GH-03.4 | Tên repo phải đúng dạng `owner/repo` (owner 1–39 ký tự chữ, số, gạch ngang, không bắt đầu bằng gạch ngang; repo 1–100 ký tự chữ, số, `.`, `_`, `-`, khác `.` và `..`); sai thì `INVALID_REPOSITORY` và không gọi GitHub. |
| FR-GH-03.5 | Đọc thông tin repo: repo bị GitHub vô hiệu hoá thì `ACCESS_DENIED`; repo archived thì vẫn đồng bộ, kèm cảnh báo `ARCHIVED_REPOSITORY`; repo đã đổi tên thì dùng tên mới và cảnh báo `REPOSITORY_RENAMED`. |
| FR-GH-03.6 | Mọi dữ liệu lấy theo một commit: đọc commit mới nhất của nhánh, rồi đọc cây thư mục (đệ quy) theo tree SHA của commit đó, rồi tải nội dung từng file theo blob SHA. Cây bị GitHub cắt bớt thì cảnh báo `TREE_TRUNCATED`. |
| FR-GH-03.7 | Chọn file: chỉ lấy file thường (bỏ symlink), sắp theo đường dẫn; bỏ file có đường dẫn bất thường (cảnh báo `UNSAFE_PATHS_SKIPPED`); bỏ file không nhận diện được ngôn ngữ theo đuôi hoặc không phải Java/Python; bỏ file trong thư mục công cụ và thư viện, thư mục build ngoài `src`, file `.min.js`, `.bundle.js` (xem mục 7). Đủ `maxFiles` thì dừng chọn và cảnh báo `FILE_LIMIT_REACHED`; không chọn được file nào thì cảnh báo `NO_SOURCE_FILES`. |
| FR-GH-03.8 | Nội dung file: `includeContent = false` thì không tải (`NOT_REQUESTED`); file lớn hơn 200.000 byte thì không tải (`TOO_LARGE`); file có byte 0 trong 8000 byte đầu là file nhị phân (`BINARY`); còn lại giải mã Base64 thành UTF-8 và bỏ ký tự BOM ở đầu. |
| FR-GH-03.9 | Một file không tải được thì đánh dấu `UNAVAILABLE` kèm cảnh báo `FILE_UNAVAILABLE` (tối đa 10 cảnh báo, phần còn lại gộp thành `MORE_FILES_UNAVAILABLE`) và các file khác vẫn tiếp tục. Riêng lỗi token, rate limit, mất kết nối GitHub hoặc mất quyền thì dừng cả lần đồng bộ. |
| FR-GH-03.10 | Thông tin phụ: thống kê ngôn ngữ của repo và 20 commit gần nhất (mã, thông điệp, tên và login tác giả, thời điểm, link; **không lưu email**). Không đọc được thì đồng bộ vẫn thành công, kèm cảnh báo `LANGUAGES_UNAVAILABLE` hoặc `COMMITS_UNAVAILABLE`; riêng lỗi token và rate limit vẫn dừng đồng bộ. |
| FR-GH-03.11 | Kiểm tra kết quả trước khi trả về: repo có id và tên; có tên nhánh; SHA commit đúng 40 (hoặc 64) ký tự hex; mỗi file có đường dẫn an toàn, không trùng, SHA hợp lệ, có ngôn ngữ, kích thước ≥ 0, có nội dung khi và chỉ khi không có lý do bỏ qua; thống kê khớp danh sách file. Sai thì `502 UNEXPECTED_GITHUB_RESPONSE`. |
| FR-GH-03.12 | Trạng thái repo: chuyển `SYNCING` ngay khi bắt đầu (thấy được từ request khác). Thành công: `CONNECTED`, cập nhật `lastSyncedAt`, `fullName`, `defaultBranch`, `privateRepo`, `htmlUrl` theo GitHub. Lỗi `REPOSITORY_NOT_FOUND`, `ACCESS_DENIED`, `INVALID_REPOSITORY`: `ERROR`. Lỗi khác: giữ trạng thái trước đó. Lỗi `TOKEN_INVALID`: kết nối GitHub chuyển `INVALID`. |
| FR-GH-03.13 | Giữ kết quả đồng bộ thành công gần nhất của mỗi repo trong bộ nhớ và cho xem lại mà không gọi GitHub. Chưa đồng bộ lần nào hoặc service vừa khởi động lại thì `404` kèm hướng dẫn đồng bộ trước. |
| FR-GH-03.14 | Kết quả trả về không kèm nội dung file: gồm thông tin repo, nhánh, commit mới nhất, thống kê ngôn ngữ, danh sách file (`path`, `language`, `size`, `analyzable`, `skipReason`), thống kê, cảnh báo, thời điểm đồng bộ. Nội dung file chỉ có ở FR-GH-04. |
| FR-GH-03.15 | Lỗi trả theo mã ở mục 6. Khi bị GitHub giới hạn lượt gọi (`RATE_LIMITED`), response có header `Retry-After` là số giây cần chờ (tối thiểu 1). |

## 3. API

Trình duyệt gọi qua Backend (BFF), Backend tự gắn `X-User-Id` và chuyển tiếp header `Retry-After` (xem [README](README.md)).

| Method | Endpoint | Body | Kết quả | Yêu cầu |
|---|---|---|---|---|
| POST | `/api/repositories/{id}/sync` | Không bắt buộc: `{"branch": "develop", "includeContent": true, "maxFiles": 50}` | `200` kết quả đồng bộ | FR-GH-03.1 – 03.12, 03.14 |
| GET | `/api/repositories/{id}/sync/latest` | | `200` kết quả lần gần nhất | FR-GH-03.13, 03.14 |

Ví dụ response rút gọn:

```json
{"repository": {"githubRepoId": 101, "fullName": "LivingDocs-Team/Livingdocs", "owner": "LivingDocs-Team",
  "name": "Livingdocs", "privateRepo": false, "archived": false, "defaultBranch": "main"},
 "branch": "main",
 "headCommit": {"sha": "<40 ký tự hex>", "message": "...", "authorName": "...", "authorLogin": "...",
  "committedAt": "2026-10-13T16:30:00Z", "htmlUrl": "..."},
 "languages": {"Java": 152340, "Python": 20110},
 "files": [{"path": "app/main.py", "language": "python", "size": 4210, "analyzable": true, "skipReason": null},
           {"path": "big/Generated.java", "language": "java", "size": 350000, "analyzable": false, "skipReason": "TOO_LARGE"}],
 "stats": {"totalFilesInRepo": 106, "filesSelected": 60, "filesWithContent": 60, "filesIgnored": 46,
  "treeTruncated": false, "fileLimitReached": false},
 "warnings": [], "syncedAt": "2026-10-13T16:39:13Z"}
```

Lời gọi GitHub (`https://api.github.com`, header `X-GitHub-Api-Version: 2022-11-28`): `GET /repos/{owner}/{repo}`, `GET /repos/{owner}/{repo}/commits/{branch}`, `GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1`, `GET /repos/{owner}/{repo}/git/blobs/{sha}`, `GET /repos/{owner}/{repo}/languages`, `GET /repos/{owner}/{repo}/commits?sha={branch}&per_page=20`. File mẫu: `services/github-integration-service/docs/samples/` (`sync-api-response.sample.json`, `sync-snapshot.sample.json`, `sync-errors.sample.json`).

## 4. Dữ liệu

Kết quả đồng bộ (`RepositorySnapshot`) chỉ giữ trong bộ nhớ của service, mỗi repo một bản mới nhất; mất khi service khởi động lại. Database chỉ lưu trạng thái và `last_synced_at` của repo (bảng `repositories`, xem FR-GH-02).

| Thành phần | Nội dung |
|---|---|
| `repository` | `githubRepoId`, `fullName`, `owner`, `name`, `description`, `privateRepo`, `archived`, `defaultBranch`, `htmlUrl`, `primaryLanguage`, `sizeKb`, `pushedAt` |
| `branch`, `headCommit` | nhánh đã đồng bộ và commit mới nhất (`sha`, `message`, `authorName`, `authorLogin`, `committedAt`, `htmlUrl`) |
| `languages` | số byte theo ngôn ngữ, theo thống kê của GitHub |
| `files` | mỗi file: `path`, `sha`, `size`, `language`, nội dung (không trả ra ở API này), `skipReason` (`NOT_REQUESTED`, `TOO_LARGE`, `BINARY`, `UNAVAILABLE`, hoặc null khi có nội dung) |
| `recentCommits` | tối đa 20 commit gần nhất |
| `stats` | `totalFilesInRepo`, `filesSelected`, `filesWithContent`, `filesIgnored`, `treeTruncated`, `fileLimitReached` |
| `warnings` | `{code, message}`, không làm hỏng lần đồng bộ |

## 5. Luồng chính

1. Developer bấm **Sync now** trên một repo của workspace; frontend gọi `POST /api/repositories/{id}/sync` (body `{}` hoặc chọn nhánh).
2. Service kiểm tra chủ repo, lấy kết nối `ACTIVE`, chuyển repo sang `SYNCING`.
3. Đọc thông tin repo → commit mới nhất của nhánh → cây thư mục tại commit đó → chọn file → tải nội dung → thống kê ngôn ngữ và commit gần đây.
4. Kiểm tra kết quả, chuyển repo về `CONNECTED`, lưu `lastSyncedAt`, giữ kết quả trong bộ nhớ, trả kết quả (không kèm nội dung file).
5. Khi cần, frontend xem lại bằng `GET /api/repositories/{id}/sync/latest`; bước sinh tài liệu lấy dữ liệu cho phân tích theo FR-GH-04.

## 6. Luồng lỗi

Lỗi có dạng `{"status", "code", "message", "timestamp"}`. Thông báo nói rõ bước đang làm (đọc thông tin repository, đọc commit mới nhất, đọc danh sách file, tải nội dung file…).

| Mã | HTTP | Khi nào | Trạng thái repo sau đó |
|---|---|---|---|
| `INVALID_REQUEST` | 400 | `maxFiles` ngoài 1–1000 | Không đổi, không gọi GitHub |
| `BAD_REQUEST` | 400 | Body sai JSON hoặc sai kiểu, `id` không phải UUID | Không đổi |
| `INVALID_REPOSITORY` | 400 | Tên repo sai dạng | `ERROR` |
| `TOKEN_INVALID` | 401 | Token GitHub hết hạn hoặc bị thu hồi | Giữ nguyên, kết nối chuyển `INVALID` |
| `ACCESS_DENIED` | 403 | GitHub App không có quyền đọc, hoặc repo bị vô hiệu hoá | `ERROR` |
| `FORBIDDEN` | 403 | Repo không phải của người dùng | Không đổi |
| `REPOSITORY_NOT_FOUND` | 404 | Repo bị xoá, đổi chủ, hoặc chưa cài app | `ERROR` |
| `BRANCH_NOT_FOUND` | 404 | Nhánh không tồn tại | Giữ nguyên |
| `NOT_FOUND` | 404 | Repo không có trong hệ thống; xem kết quả khi chưa đồng bộ | Không đổi |
| `EMPTY_REPOSITORY` | 409 | Repo chưa có commit | Giữ nguyên |
| `GITHUB_NOT_CONNECTED` | 409 | Chưa kết nối GitHub hoặc kết nối không còn `ACTIVE` | Không đổi |
| `RATE_LIMITED` | 429 | Hết lượt gọi GitHub API; có header `Retry-After` | Giữ nguyên |
| `UNEXPECTED_GITHUB_RESPONSE` | 502 | GitHub trả dữ liệu sai, hoặc kết quả không qua được bước kiểm tra | Giữ nguyên |
| `GITHUB_UNAVAILABLE` | 503 | Mất mạng, quá thời gian chờ, GitHub lỗi 5xx | Giữ nguyên |

`RATE_LIMITED` và `GITHUB_UNAVAILABLE` là lỗi tạm thời, người dùng thử lại sau; các lỗi khác cần người dùng làm gì đó (kết nối lại GitHub, cấp quyền repo cho app, chọn nhánh khác).

## 7. Quy tắc nghiệp vụ

- Chỉ đồng bộ repo đã có trong workspace của chính người dùng.
- Mọi file trong một lần đồng bộ thuộc cùng một commit.
- Chỉ file Java (`.java`) và Python (`.py`) được chọn để phân tích; tối đa 200 file mặc định (tới 1000 khi yêu cầu) và 20 commit gần nhất.
- Luôn bỏ qua file trong thư mục `.git`, `.github`, `.idea`, `.vscode`, `.gradle`, `.mvn`, `node_modules`, `bower_components`, `venv`, `.venv`, `__pycache__`, `.pytest_cache`, `.tox`, `site-packages`, `.next`, `.nuxt`.
- Bỏ qua thư mục build `target`, `build`, `dist`, `out`, `bin`, `obj`, `vendor`, `coverage` khi nằm ngoài thư mục `src` (vì vậy vẫn giữ `src/main/java/com/acme/build/Builder.java`).
- Bỏ qua file `.min.js`, `.bundle.js`, symlink, file lớn hơn 200.000 byte (không tải nội dung) và file nhị phân.
- Đường dẫn bất thường (rỗng, bắt đầu bằng `/`, chứa `\`, đoạn `.` hoặc `..`, ký tự điều khiển) bị bỏ qua kèm cảnh báo; đồng bộ vẫn tiếp tục với các file khác.
- Lỗi GitHub được chuyển thành hành động cho người dùng: kết nối lại GitHub, cấp quyền repo cho app, chọn nhánh khác, hoặc thử lại sau.

## 8. Tiêu chí chấp nhận

- Đồng bộ thành công: repo `CONNECTED`, `lastSyncedAt` có giá trị, response có SHA commit 40 ký tự, danh sách file không kèm nội dung.
- Mọi dữ liệu lấy theo cùng một commit; chỉ file Java và Python ngoài các thư mục bị bỏ qua mới được chọn.
- Lỗi GitHub trả đúng mã ở mục 6; lỗi tạm thời (`RATE_LIMITED`, `GITHUB_UNAVAILABLE`) không đổi trạng thái repo.
- Một file không tải được không làm hỏng cả lần đồng bộ.
- Chạy với GitHub thật trên repo nhóm (13/10/2026): 106 file, lấy đủ nội dung 60/60 file Java và Python; sai nhánh trả `404 BRANCH_NOT_FOUND`.

## 9. Kiểm thử

Test nằm trong `services/github-integration-service/src/test/java/com/livingdocs/github/`, chạy bằng `mvn verify` (job CI **GitHub Integration Service Test**).

| Test | Số test | Nội dung |
|---|---|---|
| `sync/GitHubRepositoryFetcherTest` | 25 | GitHub giả lập bằng Mockito: lấy đúng repo, commit, file đã lọc và sắp xếp, nội dung (bỏ BOM), thống kê, ngôn ngữ, commit gần đây; `includeContent = false`; `maxFiles`; chọn nhánh; các cảnh báo (archived, đổi tên, cây bị cắt, không có file, đường dẫn bất thường, một file lỗi, không có thống kê ngôn ngữ); repo 404, 401, 403, repo bị vô hiệu hoá, rate limit (kể cả giữa lúc tải file), repo rỗng, nhánh không tồn tại, mất mạng, GitHub 5xx, dữ liệu sai bị chặn |
| `sync/FileSelectionRulesTest` | 5 | Nhận diện ngôn ngữ theo đuôi; bỏ thư viện và thư mục build; giữ code thật trong `src`; chặn đường dẫn bất thường; chuẩn hoá tham số đồng bộ |
| `client/GitHubClientRepositoryApiTest` | 8 | HTTP server giả: đọc đúng JSON của repo, commit, tree, blob, languages, danh sách commit; giữ mã lỗi 404; nhận diện rate limit, 401; 403 không kèm rate limit thì không phải rate limit; không đưa nội dung lỗi của GitHub vào thông báo; không có token thì không gửi `Authorization` |
| `RepositorySyncApiTest` | 8 | `@SpringBootTest` + MockMvc + H2: đồng bộ thành công và cập nhật repo; xem lại kết quả và dữ liệu cho phân tích; người khác `403`, repo không có `404`; tham số sai `400` không gọi GitHub; sai nhánh `404` giữ trạng thái; repo bị xoá trên GitHub thì `ERROR`; token bị thu hồi thì kết nối `INVALID`; rate limit `429` kèm `Retry-After`, giữ trạng thái |
| `sync/GitHubRepositoryFetcherLiveTest` | 1 | Đồng bộ repo thật trên GitHub (25 file); chỉ chạy khi có `GITHUB_LIVE_TEST=true`, CI chạy ở mỗi lần push và pull request |
