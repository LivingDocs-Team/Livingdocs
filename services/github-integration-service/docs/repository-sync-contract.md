# LD-63 Repository Synchronization: hợp đồng dữ liệu

Tài liệu này để Đăng, Minh, Khôi và Nhân thống nhất **dữ liệu đồng bộ lấy được từ GitHub**, **cấu trúc trả về** và **các lỗi có thể xảy ra**.

| Người | Phần việc | Nằm ở đâu |
|---|---|---|
| **Đăng** | Lấy thông tin repo từ GitHub, xử lý lỗi GitHub, kiểm tra dữ liệu trả về | `sync/GitHubRepositoryFetcher` (đã xong, có test) |
| **Minh** | API bắt đầu đồng bộ và trả kết quả, kiểm tra input, phản hồi API | controller / service gọi `GitHubRepositoryFetcher` |
| **Khôi** | Frontend hiển thị kết quả và lỗi | dùng JSON ở mục 3 và bảng lỗi ở mục 4 |
| **Nhân** | Test thành công và thất bại | các kịch bản ở mục 7 |

---

## 1. Lấy được gì từ GitHub

Mọi dữ liệu đều lấy theo **cùng một commit** (commit mới nhất của nhánh), nên luôn nhất quán.

| Dữ liệu | GitHub API | Ghi chú |
|---|---|---|
| Thông tin repo (tên, mô tả, nhánh mặc định, private, archived, ngôn ngữ chính) | `GET /repos/{owner}/{repo}` | Repo đổi tên thì tự dùng tên mới và cảnh báo `REPOSITORY_RENAMED` |
| Commit mới nhất của nhánh | `GET /repos/{owner}/{repo}/commits/{branch}` | Mặc định là nhánh mặc định của repo |
| Danh sách toàn bộ file | `GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1` | Chỉ 1 lần gọi cho cả repo |
| Nội dung từng file nguồn | `GET /repos/{owner}/{repo}/git/blobs/{sha}` | Chỉ tải file **java** và **python** (ngôn ngữ service phân tích code hỗ trợ) |
| Thống kê ngôn ngữ | `GET /repos/{owner}/{repo}/languages` | Lỗi thì chỉ cảnh báo |
| Các commit gần nhất | `GET /repos/{owner}/{repo}/commits?sha={branch}` | Mặc định 20 commit, lỗi thì chỉ cảnh báo |

**Tự động bỏ qua:** `node_modules`, `venv`, `__pycache__`, `.git`, `.idea`, `target` / `build` / `dist` (nằm ngoài `src`), file `*.min.js`, file nhị phân, file lớn hơn 200 KB, và đường dẫn bất thường như `../` hoặc `/`.

---

## 2. Cách gọi (cho Minh)

```java
@Service
public class RepositorySyncService {           // Minh đặt tên tuỳ ý
    private final GitHubRepositoryFetcher fetcher;
    private final GitHubConnectionService connectionService;
    // ...

    public RepositorySnapshot sync(String userId, UUID repositoryId, SyncOptions options) {
        ConnectedRepository repo = /* tìm repo theo id + kiểm tra repo thuộc user */;
        GitHubConnection connection = connectionService.getActiveConnection(userId); // tự refresh token
        try {
            RepositorySnapshot snapshot = fetcher.fetch(connection.getAccessToken(), repo.getFullName(), options);
            // gợi ý: cập nhật repo.defaultBranch, repo.lastSyncedAt = snapshot.fetchedAt(), status = CONNECTED
            return snapshot;
        } catch (RepositorySyncException e) {
            if (e.getCode() == SyncErrorCode.TOKEN_INVALID) {
                connectionService.markInvalid(connection);  // để giao diện nhắc người dùng kết nối lại
            }
            // gợi ý: repo.status = ERROR (trừ khi lỗi tạm thời: e.getCode().retryable())
            throw e;  // GlobalExceptionHandler tự trả JSON lỗi + mã HTTP đúng (mục 4)
        }
    }
}
```

`SyncOptions` (tạo bằng `SyncOptions.defaults()` rồi `.withBranch(..)`, `.withIncludeContent(..)`, `.withMaxFiles(..)`):

| Tuỳ chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `branch` | `null` = nhánh mặc định | Nhánh cần đồng bộ |
| `includeContent` | `true` | Có tải nội dung file không. Màn hình chỉ cần danh sách file thì để `false` cho nhanh |
| `maxFiles` | 200 (tối đa 1000) | Số file nguồn tối đa |
| `maxFileSizeBytes` | 200 000 | File lớn hơn sẽ có `skipReason = TOO_LARGE` |
| `recentCommitLimit` | 20 (0..100) | Số commit gần nhất |
| `languages` | `java`, `python` | Ngôn ngữ cần lấy |

Tham số sai (ví dụ `maxFiles = 0`) sẽ ném `INVALID_REQUEST` (HTTP 400).

---

## 3. Cấu trúc trả về: `RepositorySnapshot`

```json
{
  "repository": {
    "githubRepoId": 101, "fullName": "LivingDocs-Team/Livingdocs", "owner": "LivingDocs-Team",
    "name": "Livingdocs", "description": "BLCK", "privateRepo": false, "archived": false,
    "defaultBranch": "main", "htmlUrl": "https://github.com/LivingDocs-Team/Livingdocs",
    "primaryLanguage": "Java", "sizeKb": 2048, "pushedAt": "2026-10-12T08:30:00Z"
  },
  "branch": "main",
  "headCommit": {
    "sha": "6b6c07f…(40 ký tự)", "message": "Merge pull request #8 …",
    "authorName": "Dang Le Hien Hai", "authorLogin": "d3r-bbb",
    "committedAt": "2026-10-11T02:10:00Z", "htmlUrl": "https://github.com/…/commit/6b6c07f…"
  },
  "languages": { "Java": 152340, "Python": 20110, "JavaScript": 8100 },
  "files": [
    { "path": "ai-service/app/generator.py", "sha": "…", "size": 4210, "language": "python",
      "content": "\"\"\"Generators…", "skipReason": null },
    { "path": "backend/src/main/java/com/cnpm/backend/entity/User.java", "sha": "…", "size": 1830,
      "language": "java", "content": "package com.cnpm…", "skipReason": null },
    { "path": "big/Generated.java", "sha": "…", "size": 350000, "language": "java",
      "content": null, "skipReason": "TOO_LARGE" }
  ],
  "recentCommits": [ { "sha": "…", "message": "…", "authorName": "…", "authorLogin": "…", "committedAt": "…", "htmlUrl": "…" } ],
  "stats": {
    "totalFilesInRepo": 118, "filesSelected": 64, "filesWithContent": 63,
    "filesIgnored": 54, "treeTruncated": false, "fileLimitReached": false
  },
  "warnings": [ { "code": "ARCHIVED_REPOSITORY", "message": "…" } ],
  "fetchedAt": "2026-10-12T15:20:00Z"
}
```

- `files` luôn **sắp xếp theo `path`**. File có `content != null` là file **phân tích được**; trong Java có sẵn `snapshot.analyzableFiles()`.
- `skipReason`: `NOT_REQUESTED` (không yêu cầu tải nội dung), `TOO_LARGE`, `BINARY`, `UNAVAILABLE` (GitHub không trả được file đó).
- **Không** có token hay email tác giả trong dữ liệu trả về.
- Nội dung file có thể nặng (tối đa khoảng 200 file × 200 KB). Gợi ý cho Minh: API cho frontend nên trả **không kèm `content`**, còn nội dung chỉ dùng nội bộ để gửi sang bước phân tích.

### Cảnh báo (`warnings`): đồng bộ vẫn thành công

| code | Ý nghĩa |
|---|---|
| `ARCHIVED_REPOSITORY` | Repo đã lưu trữ (chỉ đọc) |
| `REPOSITORY_RENAMED` | Repo đã đổi tên; nên cập nhật `fullName` trong DB |
| `TREE_TRUNCATED` | Repo quá lớn, GitHub chỉ trả một phần danh sách file |
| `FILE_LIMIT_REACHED` | Đã đủ `maxFiles`, còn file chưa lấy |
| `NO_SOURCE_FILES` | Không có file java/python nào |
| `FILE_UNAVAILABLE` / `MORE_FILES_UNAVAILABLE` | Một vài file không tải được nội dung |
| `UNSAFE_PATHS_SKIPPED` | Có đường dẫn bất thường bị bỏ qua |
| `LANGUAGES_UNAVAILABLE` / `COMMITS_UNAVAILABLE` | Không lấy được thông tin phụ |

---

## 4. Lỗi: `RepositorySyncException`

`GlobalExceptionHandler` đã tự chuyển lỗi thành JSON. Minh **không cần** tự bắt lỗi trong controller:

```json
{ "status": 404, "code": "REPOSITORY_NOT_FOUND",
  "message": "Không tìm thấy repository LivingDocs-Team/abc (repo đã bị xoá, đổi tên, hoặc GitHub App chưa được cài cho repo này).",
  "timestamp": "2026-10-12T15:20:00Z" }
```

| code | HTTP | Khi nào | Gợi ý cho frontend (Khôi) | Thử lại? |
|---|---|---|---|---|
| `INVALID_REQUEST` | 400 | Tham số đồng bộ sai | Báo lỗi nhập liệu | ❌ |
| `INVALID_REPOSITORY` | 400 | Tên repo sai dạng `owner/repo` | Báo lỗi nhập liệu | ❌ |
| `TOKEN_INVALID` | 401 | Token GitHub hết hạn hoặc bị thu hồi | Nút **"Kết nối lại GitHub"** | ❌ |
| `ACCESS_DENIED` | 403 | GitHub App không có quyền với repo, hoặc repo bị khoá | Hướng dẫn cài app cho repo | ❌ |
| `REPOSITORY_NOT_FOUND` | 404 | Repo bị xoá, đổi tên, hoặc chưa cài app | Gợi ý gỡ repo khỏi workspace | ❌ |
| `BRANCH_NOT_FOUND` | 404 | Nhánh không tồn tại | Cho chọn nhánh khác | ❌ |
| `EMPTY_REPOSITORY` | 409 | Repo chưa có commit | "Repo trống, chưa có gì để đồng bộ" | ❌ |
| `RATE_LIMITED` | 429 | Hết lượt gọi GitHub API (có header `Retry-After`) | "Thử lại sau X phút" | ✅ |
| `GITHUB_UNAVAILABLE` | 503 | Mất mạng, timeout, GitHub lỗi 5xx | Nút **"Thử lại"** | ✅ |
| `UNEXPECTED_GITHUB_RESPONSE` | 502 | GitHub trả dữ liệu lạ hoặc sai | "Có lỗi, vui lòng thử lại" | ❌ |

Trong Java dùng `e.getCode().httpStatus()`, `e.getCode().retryable()` và `e.getRetryAt()`.

---

## 5. Chuyển sang bước phân tích code và sinh tài liệu

```
RepositorySnapshot.analyzableFiles()
   │  với mỗi file:  POST /api/v1/analyze   { "code": file.content, "language": file.language }   ← service phân tích (app/)
   ▼
kết quả phân tích từng file (path, language, classes, functions…)
   │  POST /generate { "scope": "repository", "target": repository.fullName, "files": [...] }      ← ai-service
   ▼
tài liệu Markdown
```

Giá trị `language` (`"java"`, `"python"`) đã viết thường, **khớp đúng** với tham số mà `/api/v1/analyze` cần.

---

## 6. Gợi ý API (Minh quyết định)

| Method | Endpoint | Gợi ý |
|---|---|---|
| POST | `/api/repositories/{id}/sync` | Body `{ "branch"?: "...", "includeContent"?: true }`. Endpoint này đã có từ LD-58 nhưng mới chỉ cập nhật thông tin repo; Minh thay phần xử lý bằng `fetcher.fetch(...)` |
| GET | `/api/repositories/{id}/sync/latest` | Kết quả lần đồng bộ gần nhất (bỏ `content` cho nhẹ) |

Header `X-User-Id` vẫn dùng như các API hiện tại cho đến khi có JWT của TV1.

**Thời gian:** nội dung file được tải lần lượt, mỗi file 1 lần gọi GitHub. Repo khoảng 100 file nguồn mất chừng 10–30 giây. Nếu thấy chậm, API có thể chạy đồng bộ ở nền: trả `202 Accepted` kèm mã lần đồng bộ, frontend hỏi lại trạng thái. Repo mẫu nhỏ thì gọi thẳng (trả `200`) là được.

---

## 7. Kịch bản test (cho Nhân)

Đã có sẵn trong `GitHubRepositoryFetcherTest` (GitHub giả, không cần mạng):

- ✅ **Thành công:** đúng thông tin repo, commit, danh sách file đã lọc và sắp xếp, nội dung file (bỏ BOM), thống kê, ngôn ngữ, commit gần nhất; chọn nhánh khác; không tải nội dung; giới hạn `maxFiles`.
- ⚠️ **Cảnh báo:** repo archived, repo đổi tên, cây thư mục bị cắt, không có file nguồn, đường dẫn bất thường, một file không tải được, không lấy được thống kê ngôn ngữ.
- ❌ **Lỗi:** tên repo sai (không gọi GitHub), 404, 401, 403, repo bị khoá, rate limit (có thời điểm thử lại), rate limit giữa chừng, repo rỗng (409), nhánh không tồn tại (422), mất mạng, GitHub 5xx, dữ liệu GitHub sai.

`GitHubClientRepositoryApiTest` kiểm tra việc đọc JSON thật của GitHub và nhận diện mã lỗi bằng một HTTP server giả.

**Chạy thử với GitHub thật** (repo public, không cần token): chạy `GitHubRepositoryFetcherLiveTest` với biến môi trường `GITHUB_LIVE_TEST=true`. Kết quả JSON thật sẽ in ra màn hình.
