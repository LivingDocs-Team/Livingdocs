# Báo cáo kiểm thử GitHub Integration và CI/CD (LD-391)

Người làm: Đăng (TV2). Phạm vi: `services/github-integration-service` (kết nối GitHub, quản lý repo, đồng bộ repo) và CI của service này.

## 1. Tóm tắt

| Hạng mục | Kết quả |
|---|---|
| Test tự động (GitHub giả, database H2) | **68 test**, chạy bằng "Run All Tests" hoặc `mvn test` |
| Test với GitHub thật, tự động | `GitHubRepositoryFetcherLiveTest`, chạy trong CI ở mỗi lần push và pull request |
| Test tay trên Swagger với GitHub thật (13/10) | Đạt: đồng bộ 106 file, 60/60 file java/python có nội dung, lỗi sai nhánh trả 404 đúng mã |
| Chuỗi GitHub → service phân tích → ai-service (19/10) | Đạt, sau khi sửa lỗi của service phân tích trên `main` (mục 6) |
| CI | Thêm job **GitHub Integration Service Test** vào `.github/workflows/ci.yml` |

## 2. Cách chạy

| Cách | Lệnh / thao tác | Kết quả đúng |
|---|---|---|
| IntelliJ | Chuột phải `src/test/java` → **Run 'All Tests'** | 68 passed, 1 ignored (test GitHub thật) |
| Dòng lệnh | `mvn test` trong thư mục service | `Tests run: 69, Failures: 0, Errors: 0, Skipped: 1` |
| GitHub thật | Chạy `GitHubRepositoryFetcherLiveTest` với biến môi trường `GITHUB_LIVE_TEST=true` | In ra repo, commit, danh sách file; test passed |
| CI | Push lên nhánh `LD-*` hoặc mở pull request vào `main` | Job **GitHub Integration Service Test** xanh |

Job CI gồm 3 bước:

1. `mvn verify`: build service và chạy toàn bộ test (không cần Docker, không gọi GitHub thật).
2. Chạy `GitHubRepositoryFetcherLiveTest` với GitHub thật trên chính repo của nhóm, dùng `GITHUB_TOKEN` có sẵn của GitHub Actions (chỉ có quyền đọc).
3. Tải báo cáo test (`surefire-reports`) lên phần Artifacts của lần chạy, kể cả khi test lỗi.

## 3. Test tự động

| Class | Số test | Kiểm tra gì |
|---|---|---|
| `GitHubRepositoryFetcherTest` | 25 | Đồng bộ thành công, các cảnh báo và mọi lỗi GitHub (mục 4), dùng GitHub giả |
| `GitHubClientRepositoryApiTest` | 7 | Đọc đúng JSON thật của GitHub, nhận diện 401 / 404 / rate limit qua header, không gửi token khi không có |
| `RepositorySyncApiTest` | 8 | API đồng bộ qua HTTP: thành công, `/sync/latest`, `/analysis-input`, 403, 404, 400, sai nhánh, repo bị xoá, token hỏng, 429 + `Retry-After` |
| `GitHubIntegrationFlowTest` | 4 | Cả luồng: kết nối → trạng thái → liệt kê repo → thêm → đồng bộ → gỡ → ngắt kết nối; state OAuth giả; thiếu header; token bị thu hồi |
| `GitHubConnectionControllerTest` | 6 | Callback GitHub: trả JSON, chuyển về frontend khi thành công / lỗi, người dùng bấm Cancel |
| `CorsConfigTest` | 3 | Frontend cổng 3000 và 5173 gọi được API, địa chỉ lạ bị chặn |
| `TokenEncryptorTest` | 5 | Mã hoá token AES-GCM, khoá sai độ dài hoặc thiếu khoá |
| `OAuthStateStoreTest` | 3 | State chỉ dùng 1 lần, state lạ, state hết hạn |
| `FileSelectionRulesTest` | 5 | Nhận diện ngôn ngữ, bỏ qua thư viện và file build, chặn đường dẫn bất thường |
| `AnalysisInputTest` | 2 | Dữ liệu gửi service phân tích: chỉ file có nội dung, đúng tên trường (`repo_name`, `files`) |
| `GitHubRepositoryFetcherLiveTest` | 1 | GitHub thật (tắt mặc định, CI bật) |

## 4. Các lỗi GitHub đã kiểm thử

| Tình huống | GitHub trả | Service trả | Trạng thái sau đó | Test |
|---|---|---|---|---|
| Tên repo sai dạng `owner/repo` | (không gọi GitHub) | 400 `INVALID_REPOSITORY` | repo `ERROR` | `invalidRepositoryName_failsWithoutCallingGitHub` |
| Repo bị xoá, đổi chủ, chưa cài app | 404 | 404 `REPOSITORY_NOT_FOUND` | repo `ERROR` | `repositoryNotFound`, `repositoryGoneOnGitHub_marksRepositoryError` |
| Token hết hạn hoặc bị thu hồi | 401 | 401 `TOKEN_INVALID` | kết nối `INVALID` | `tokenInvalid`, `revokedToken_marksConnectionInvalid`, `unauthorized_isDetected` |
| App không có quyền với repo | 403 | 403 `ACCESS_DENIED` | repo `ERROR` | `accessDenied`, `forbiddenWithoutRateLimit_isNotRateLimited` |
| Repo bị GitHub khoá | 403 | 403 `ACCESS_DENIED` | repo `ERROR` | `disabledRepository_isAccessDenied` |
| Hết lượt gọi API | 403 hoặc 429, `x-ratelimit-remaining: 0` | 429 `RATE_LIMITED` + header `Retry-After` | giữ nguyên | `rateLimited_reportsRetryTime`, `rateLimitedWhileDownloading_stopsSync`, `rateLimit_isDetectedFromHeaders`, `rateLimited_is429WithRetryAfter_andKeepsStatus` |
| Repo trống | 409 | 409 `EMPTY_REPOSITORY` | giữ nguyên | `emptyRepository` |
| Nhánh không tồn tại | 422 | 404 `BRANCH_NOT_FOUND` | giữ nguyên | `branchNotFound`, `branchNotFound_is404_andKeepsStatus` |
| Mất mạng, timeout | (không phản hồi) | 503 `GITHUB_UNAVAILABLE` | giữ nguyên | `networkError_isGitHubUnavailable` |
| GitHub lỗi | 5xx | 503 `GITHUB_UNAVAILABLE` | giữ nguyên | `gitHubServerError_isGitHubUnavailable` |
| GitHub trả dữ liệu sai | 200 | 502 `UNEXPECTED_GITHUB_RESPONSE` | giữ nguyên | `malformedCommitFromGitHub_isRejectedByVerifier` |
| Token bị thu hồi khi liệt kê repo | 401 | 401 `GITHUB_REAUTH_REQUIRED` | kết nối `INVALID` | `revokedTokenOnGitHub_marksConnectionInvalid` |
| State OAuth giả hoặc hết hạn | | 400 `BAD_REQUEST` | | `callbackWithInvalidState_isRejected`, `OAuthStateStoreTest` |
| Người dùng bấm Cancel trên GitHub | `?error=access_denied` | 400 `GITHUB_ACCESS_DENIED` (hoặc chuyển về frontend) | | `userCancelledOnGitHub_*` |
| Người khác đồng bộ repo của mình | | 403 `FORBIDDEN` | | `otherUser_isForbidden_unknownRepository_isNotFound` |
| Tham số đồng bộ sai | | 400 `INVALID_REQUEST` / `BAD_REQUEST` | không gọi GitHub | `invalidOptions_areRejected`, `invalidInput_isBadRequest_andDoesNotCallGitHub` |

Cảnh báo (đồng bộ vẫn thành công) cũng có test: repo archived, repo đổi tên, danh sách file bị GitHub cắt bớt, không có file nguồn, đường dẫn bất thường, một file không tải được, không lấy được thống kê ngôn ngữ.

## 5. Kiểm thử với GitHub thật

**Tự động (CI):** `GitHubRepositoryFetcherLiveTest` đồng bộ repo của nhóm (tối đa 25 file nguồn) và kiểm tra: commit có SHA 40 ký tự, có danh sách file, có file phân tích được (java/python kèm nội dung).

**Bằng tay trên Swagger (13/10/2026)**, GitHub App `livingdocs-dev-hai`, repo `d3r-bbb/Livingdocs` (`githubRepoId` 1417486696):

| Bước | Kết quả |
|---|---|
| Kết nối GitHub (`/authorize-url` → Authorize → `/callback`) | "Kết nối GitHub thành công" |
| `GET /api/github/repos/available` | Thấy repo đã cấp quyền cho app |
| `POST /api/workspaces/{id}/repositories` | `201`, trạng thái `CONNECTED` |
| `POST /api/repositories/{id}/sync` | `200`: 106 file, 60/60 file java/python có nội dung |
| `GET .../sync/latest/analysis-input` | Đủ nội dung file để gửi service phân tích |
| `POST .../sync` với `{"branch": "khong-co"}` | `404 BRANCH_NOT_FOUND` |
| `GET /api/repositories/{id}` | `CONNECTED`, `lastSyncedAt` = 2026-10-13T16:39:13Z |

## 6. Kiểm thử liên service: GitHub → service phân tích → ai-service (19/10/2026)

Đầu vào: `docs/samples/analysis-input.sample.json` (3 file thật của repo nhóm, đúng dạng `GET .../analysis-input`).

**Phát hiện trên `main` (commit `7850180`):**

- `POST /api/v1/analyze-repo` của service phân tích trả **500**: `AttributeError: type object 'ASTAnalyzer' has no attribute 'parse_code'` (thiếu cả `FileReader.detect_language`). Vì vậy job CI **AI Service Integration Test** đang lỗi ở `test_analyzer_to_ai_service_pipeline`, kể cả với pull request không sửa gì service phân tích.
- Service phân tích đọc tên repo ở trường `repo_name`, còn body của mình trước đây chỉ có `target`, nên kết quả bị đặt tên `default_repo`. Đã sửa phía mình: gửi cả `repo_name` và `target`.

**Trạng thái:** bản sửa cho service phân tích (thêm 2 hàm còn thiếu, nhận cả `repo_name` lẫn `target`, cập nhật 1 test cũ) đã gửi Lâm, chờ merge. Đã chạy thử với bản sửa:

| Kiểm tra | Kết quả |
|---|---|
| Test của service phân tích (`tests/`) | 13 passed, 1 skipped (test giao diện cần Playwright) |
| Test của ai-service | 65 passed, 3 skipped |
| Test liên service (`pytest -m live`) | 2 passed |
| Gửi `analysis-input.sample.json` → service phân tích → `/generate` | Service phân tích trả `target` = `LivingDocs-Team/Livingdocs`, 3 file `ok`; ai-service trả job `completed`, tài liệu Markdown bắt đầu bằng `# LivingDocs-Team/Livingdocs` |

## 7. CI hiện tại

| Job | Kiểm tra | Ghi chú |
|---|---|---|
| Backend Build and Test | Backend đăng nhập (Java, PostgreSQL) | |
| Frontend Build and Test | Lint, build | |
| **GitHub Integration Service Test** | 68 test + test GitHub thật + báo cáo test | **Mới (LD-391)** |
| AI Service Build and Test | Test của ai-service | |
| AI Service Integration Test | Service phân tích + ai-service chạy thật | Đang lỗi trên `main` cho đến khi merge bản sửa ở mục 6 |

Đề xuất: sau khi bản sửa service phân tích được merge, thêm test của service phân tích (`tests/`) vào CI để lỗi như mục 6 bị chặn ngay ở pull request.

## 8. Chưa kiểm thử được

- Luồng OAuth với GitHub thật trong CI (cần người bấm Authorize). Đã test tay ở mục 5.
- Webhook và đồng bộ chạy nền: chưa làm.
- Kết quả đồng bộ chỉ giữ trong bộ nhớ, khởi động lại service thì phải đồng bộ lại.
- Chạy cả chuỗi từ giao diện: frontend vẫn dùng dữ liệu mẫu (hướng dẫn nối API: [frontend-api-guide.md](frontend-api-guide.md)).
