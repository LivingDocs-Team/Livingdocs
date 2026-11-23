# FR-BE—01 Repository Synchronization

| Mục | Nội dung |
|---|---|
| Story Jira | LD-63 Repository Synchronization |
| Task đã làm | LD-64 – LD-67 |
| Người thực hiện | Nguyễn Lê Minh |
| Thành phần | GitHub Integration Service: `sync/*` (`GitHubRepositoryFetcher`, `SyncOptions`, `RepositorySnapshot`, `PathFilter`, `LanguageDetector`, `AnalysisInput`, `RepositorySyncException`, `SyncErrorCode`, `SyncWarning`), `service/RepositorySyncService`, `controller/RepositorySyncController`, `exception/GlobalExceptionHandler`, `client/GitHubClient`, `entity/ConnectedRepository` |
| Tác nhân | Frontend gọi API sync; Analyzer gọi `analysis-input` |

## 1. Mô tả

Chức năng đồng bộ lấy snapshot của một repository GitHub thuộc workspace người dùng. Snapshot được lấy nhất quán theo commit mới nhất của nhánh được chọn và gồm thông tin repository, nhánh, commit HEAD, cây file, nội dung file Java/Python được hỗ trợ, thống kê ngôn ngữ, một số commit gần đây, thống kê số file và cảnh báo. Chức năng phục vụ bước phân tích code tiếp theo. API dành cho frontend không trả nội dung file lớn; endpoint `analysis-input` tạo payload có nội dung file để gửi cho analyzer.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-BE—01.1 | Nhận yêu cầu `POST /api/repositories/{id}/sync` với header `X-User-Id`; body có thể bỏ trống/rỗng/`{}`. |
| FR-BE—01.2 | Xác minh repository tồn tại và thuộc người dùng hiện tại; sai quyền trả `403 ACCESS_DENIED`; không tồn tại trả `404 REPOSITORY_NOT_FOUND`. |
| FR-BE—01.3 | Lấy GitHub access token từ connection service; token hết hạn/bị thu hồi đánh dấu connection `INVALID` và trả `401 TOKEN_INVALID`. Không đưa token vào response. |
| FR-BE—01.4 | Chuyển trạng thái repository sang `SYNCING` khi bắt đầu; `CONNECTED` khi thành công; `ERROR` với `REPOSITORY_NOT_FOUND`/`ACCESS_DENIED`/`INVALID_REPOSITORY`; lỗi khác giữ nguyên trạng thái trước. |
| FR-BE—01.5 | Fetcher lấy repository info, commit HEAD của nhánh, recursive tree, nội dung file Java/Python, thống kê ngôn ngữ và recent commits. Mọi dữ liệu snapshot phải cùng commit SHA. |
| FR-BE—01.6 | Áp dụng `SyncOptions`: `branch` mặc định `null` (nhánh default), `includeContent` mặc định `true`, `maxFiles` mặc định `200` (≤ 1000), `maxFileSizeBytes` mặc định `200000`, `recentCommitLimit` mặc định `20` (0..100), `languages` mặc định `java`, `python`. |
| FR-BE—01.7 | Lọc file: bỏ qua thư mục sinh tự động/môi trường (`node_modules`, `venv`, `__pycache__`, `.git`, `.idea`, `target`, `build`, `dist` — trừ khi nằm trong `src` theo quy tắc code), `*.min.js`, file nhị phân, file > `maxFileSizeBytes`, đường dẫn không an toàn (`../`, tuyệt đối `/`). Gắn `skipReason` (`NOT_REQUESTED`, `TOO_LARGE`, `BINARY`, `UNAVAILABLE`). |
| FR-BE—01.8 | Sắp xếp ổn định `files` theo `path`; xử lý BOM khi đọc nội dung. |
| FR-BE—01.9 | Trả `RepositorySnapshot` gồm `repository` (id, fullName, owner, name, description, private/archived, default branch, URL, primary language, size, pushedAt), `branch`, `headCommit` (SHA, message, author name/login, committedAt, URL), `languages` (map ngôn ngữ→byte), `files` (path, sha, size, language, content, skipReason), `recentCommits`, `stats` (`totalFilesInRepo`, `filesSelected`, `filesWithContent`, `filesIgnored`, `treeTruncated`, `fileLimitReached`), `warnings`, `fetchedAt`. |
| FR-BE—01.10 | Trả warning không làm thất bại sync: `ARCHIVED_REPOSITORY`, `REPOSITORY_RENAMED`, `TREE_TRUNCATED`, `FILE_LIMIT_REACHED`, `NO_SOURCE_FILES`, `FILE_UNAVAILABLE`/`MORE_FILES_UNAVAILABLE`, `UNSAFE_PATHS_SKIPPED`, `LANGUAGES_UNAVAILABLE`, `COMMITS_UNAVAILABLE`. |
| FR-BE—01.11 | Khi thành công cập nhật `lastSyncedAt`, `defaultBranch`, và `fullName` nếu repo đã đổi tên. |
| FR-BE—01.12 | Giữ snapshot mới nhất trong bộ nhớ của service (mất khi restart, phải sync lại). |
| FR-BE—01.13 | `GET .../sync/latest` trả metadata snapshot (không có `content`); `GET .../sync/latest/analysis-input` trả `AnalysisInput` có nội dung. |
| FR-BE—01.14 | `AnalysisInput.from(snapshot)` chỉ chọn `analyzableFiles()` (content != null) và tạo `{scope: "repository", target: <full repo name>, files: [{path, language, content}]}`; `language` chữ thường (`java`, `python`). |
| FR-BE—01.15 | Mọi lỗi đi qua `GlobalExceptionHandler` để chuẩn hóa JSON `{status, code, message, timestamp}`. |

## 3. API

| Method | Endpoint | Kết quả | Yêu cầu |
|---|---|---|---|
| POST | `/api/repositories/{id}/sync` | `SyncResultResponse` (metadata snapshot, không `content`) | FR-BE—01.1 – FR-BE—01.12 |
| GET | `/api/repositories/{id}/sync/latest` | Metadata snapshot gần nhất | FR-BE—01.12 – FR-BE—01.13 |
| GET | `/api/repositories/{id}/sync/latest/analysis-input` | `{scope, target, files: [{path, language, content}]}` | FR-BE—01.13 – FR-BE—01.14 |

Body `POST /sync` không bắt buộc. Ví dụ: `{"branch": "develop", "includeContent": true, "maxFiles": 50}`. `maxFiles` ngoài `1..1000` → `400 INVALID_REQUEST`. Mọi endpoint yêu cầu `X-User-Id` và kiểm tra quyền sở hữu repository.

## 4. Luồng chính

1. Frontend gọi `POST /api/repositories/{id}/sync` với `X-User-Id`.
2. Service xác minh repository tồn tại và thuộc user; sai quyền trả `403`.
3. Service lấy access token GitHub; token hỏng → connection `INVALID` + lỗi `TOKEN_INVALID`.
4. Cập nhật trạng thái repository `SYNCING`.
5. `GitHubRepositoryFetcher` gọi GitHub REST API: repo info, commit nhánh, recursive tree, nội dung file hỗ trợ, thống kê ngôn ngữ, recent commits.
6. Fetcher áp dụng `PathFilter`/`LanguageDetector`, kiểm tra kích thước/đường dẫn, sắp xếp file theo `path`, tạo `RepositorySnapshot`.
7. Service cập nhật `CONNECTED`, `lastSyncedAt`, `defaultBranch`, `fullName` (nếu đổi tên); cache snapshot trong memory.
8. Frontend nhận metadata không có `content`.
9. Khi analyzer cần code, backend gọi `GET .../sync/latest/analysis-input` để lấy payload có nội dung.

## 5. Luồng lỗi

| Trường hợp | HTTP | Kết quả |
|---|---|---|
| `maxFiles` ngoài `1..1000` hoặc tham số không hợp lệ | 400 | `INVALID_REQUEST` |
| Tên repo sai định dạng `owner/repo` | 400 | `INVALID_REPOSITORY`; status → `ERROR` |
| Token GitHub hết hạn/bị thu hồi | 401 | `TOKEN_INVALID`; connection → `INVALID` |
| Repository không thuộc user | 403 | `ACCESS_DENIED` |
| App không có quyền truy cập | 403 | `ACCESS_DENIED`; status → `ERROR` |
| Repo bị xóa/đổi tên/chưa cài app | 404 | `REPOSITORY_NOT_FOUND`; status → `ERROR` |
| Nhánh không tồn tại | 404 | `BRANCH_NOT_FOUND` |
| Repo chưa có commit | 409 | `EMPTY_REPOSITORY` |
| Hết quota GitHub | 429 | `RATE_LIMITED` (giữ `Retry-After`/thời điểm retry) |
| Timeout/mất mạng/GitHub 5xx | 503 | `GITHUB_UNAVAILABLE` |
| GitHub trả dữ liệu sai định dạng | 502 | `UNEXPECTED_GITHUB_RESPONSE` |
| `/sync/latest` khi chưa có snapshot | 404 | `REPOSITORY_NOT_FOUND` |

## 6. Quy tắc nghiệp vụ

- Snapshot mới nhất chỉ nằm trong memory; restart service làm mất kết quả và phải sync lại.
- Tải nội dung file tuần tự, mỗi file cần một lần gọi GitHub API; repo ~100 file nguồn có thể mất 10–30 giây.
- Sync chạy đồng bộ trong request, chưa có background job.
- Không thuộc phạm vi LD-63: OAuth/đăng nhập, webhook push/pull_request, đồng bộ nền, lưu lịch sử snapshot, Kafka events, AST analysis, sinh tài liệu AI.
- Người dùng hiện được nhận diện bằng header `X-User-Id` (tạm thời, chưa JWT).
- Lỗi không retryable không tự lặp; `RATE_LIMITED` và `GITHUB_UNAVAILABLE` có thể retry theo thời điểm/điều kiện trả về.
- `REPOSITORY_NOT_FOUND`/`ACCESS_DENIED`/`INVALID_REPOSITORY` → status `ERROR`; lỗi khác giữ nguyên trạng thái trước.
- File có `content != null` mới được coi là file phân tích được.
- Cảnh báo được trả trong snapshot; bản thân cảnh báo không đồng nghĩa request thất bại.

## 7. Tiêu chí chấp nhận

- **AC-BE-01.1:** Snapshot thành công có repo, branch, HEAD commit, file, language stats, recent commits.
- **AC-BE-01.2:** Nhánh tùy chỉnh được dùng đúng; không truyền `branch` → dùng nhánh default.
- **AC-BE-01.3:** `includeContent=false` không tải nội dung.
- **AC-BE-01.4:** `maxFiles` và file-size limit được áp dụng; file vượt giới hạn có `skipReason=TOO_LARGE`.
- **AC-BE-01.5:** File sắp xếp theo `path`; BOM được xử lý.
- **AC-BE-01.6:** Bỏ qua thư mục/file không hợp lệ, binary, file quá lớn và unsafe path.
- **AC-BE-01.7:** Warning archived/renamed/tree truncated/no source/file unavailable/language unavailable xuất hiện đúng.
- **AC-BE-01.8:** Xử lý 401, 403, 404, empty repo, branch missing, 429, timeout, 5xx, dữ liệu GitHub sai → đúng mã lỗi/HTTP.
- **AC-BE-01.9:** Endpoint kiểm tra quyền sở hữu; người khác nhận `403`.
- **AC-BE-01.10:** `POST sync` cập nhật `SYNCING` → `CONNECTED`; lỗi tương ứng cập nhật status.
- **AC-BE-01.11:** `/sync/latest` trả 404 khi chưa có snapshot.
- **AC-BE-01.12:** `/analysis-input` chỉ chứa file có nội dung, đúng `scope`, `target`, `files`.

## 8. Kiểm thử

Test unit/integration của `services/github-integration-service` (H2 + GitHub mock). Workflow LD-376 chạy job "GitHub Integration Service Test" bằng Maven với H2/mock và live test qua `GITHUB_LIVE_TEST=true`, `GITHUB_LIVE_REPO`, `GITHUB_TOKEN`; upload `target/surefire-reports/` với `if: always()`.