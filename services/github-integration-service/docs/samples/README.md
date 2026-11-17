# Dữ liệu mẫu và hướng dẫn chạy test: đồng bộ repository (LD-63)

Theo kế hoạch Sprint 2: *"Các thành viên còn lại cung cấp dữ liệu mẫu và hướng dẫn chạy test cho Nhân"*.

Dữ liệu được tạo bằng **chính code đồng bộ** (`GitHubRepositoryFetcher`) chạy trên repo của nhóm, `LivingDocs-Team/Livingdocs`, nhánh `main`, commit `51006a4`. Kết quả khớp với lần chạy trên GitHub thật: 106 file, cùng kích thước file.
`githubRepoId`, `sizeKb` và `pushedAt` chỉ là **giá trị minh hoạ**.

| File | Dùng cho | Nội dung |
|---|---|---|
| `sync-snapshot.sample.json` | Minh, Nhân | Kết quả đồng bộ đầy đủ (`RepositorySnapshot`): 60 file java/python. **Nội dung file được rút gọn 160 ký tự** cho dễ đọc |
| `sync-api-response.sample.json` | **Khôi** (frontend), Nhân | Response của `POST /api/repositories/{id}/sync` và `GET .../sync/latest`: không có nội dung file, có cờ `analyzable` |
| `sync-errors.sample.json` | **Khôi**, Nhân | Response lỗi thật cho 9 mã lỗi: 400 / 401 / 403 / 404 / 409 / 429 / 503 |
| `analysis-input.sample.json` | **Lâm** (LD-395), Nhân | Body gửi sang service phân tích code (`AnalysisInput.from(snapshot)`), rút gọn còn 3 file thật (2 python, 1 java) **kèm nội dung đầy đủ**: `scope`, `target`, `files[{path, language, content}]` |

## Chạy test

Cần: JDK 21 và IntelliJ (không cần Docker, không cần mạng).

**Cách 1: IntelliJ**
1. Mở thư mục `services/github-integration-service`.
2. Chuột phải vào `src/test/java`, chọn **Run 'All Tests'**.
3. Kết quả đúng: **68 passed, 1 ignored**.

**Cách 2: dòng lệnh** (cần cài Maven):
```bash
cd services/github-integration-service
mvn test
```

| Test | Kiểm tra gì |
|---|---|
| `GitHubRepositoryFetcherTest` (25) | Đồng bộ thành công, các cảnh báo, các lỗi 401 / 403 / 404 / 409 / 422 / 429 / 5xx / mất mạng (GitHub giả) |
| `FileSelectionRulesTest` (5) | Nhận diện ngôn ngữ, bỏ qua `node_modules` / `target`…, chặn đường dẫn bất thường |
| `AnalysisInputTest` (2) | Dữ liệu gửi sang service phân tích: chỉ lấy file có nội dung, đúng tên field (`scope`, `target`, `files`) |
| `GitHubClientRepositoryApiTest` (7) | Đọc đúng JSON của GitHub và mã lỗi (HTTP server giả) |
| `RepositorySyncApiTest` (8) | API đồng bộ: thành công, `/sync/latest`, `/analysis-input`, `403`, `404`, `400`, nhánh không tồn tại, repo bị xoá, token hỏng, rate limit `429` |
| `GitHubIntegrationFlowTest`, `TokenEncryptorTest`, `OAuthStateStoreTest` (12) | Luồng kết nối GitHub và quản lý repo (Sprint 1) |
| `GitHubConnectionControllerTest` (6) | Callback GitHub: trả JSON, hoặc chuyển về frontend (`?github=connected` / `?github=error&reason=...`), người dùng bấm Cancel |
| `CorsConfigTest` (3) | Frontend cổng 3000 / 5173 gọi được API, địa chỉ lạ bị chặn |
| `GitHubRepositoryFetcherLiveTest` (bỏ qua mặc định) | Chạy với **GitHub thật**: đặt biến môi trường `GITHUB_LIVE_TEST=true` (tuỳ chọn `GITHUB_LIVE_REPO=owner/repo`). Không cần token với repo public, giới hạn 60 lần gọi/giờ |

## Tái hiện lỗi nhanh (chạy app rồi gọi API trên Swagger)

| Muốn thấy lỗi | Cách làm |
|---|---|
| `BRANCH_NOT_FOUND` (404) | Gọi đồng bộ với body `{"branch": "khong-co"}` |
| `INVALID_REQUEST` (400) | Gọi đồng bộ với body `{"maxFiles": 0}` |
| `REPOSITORY_NOT_FOUND` (404) | Gỡ GitHub App khỏi repo trên GitHub, rồi đồng bộ lại |
| `TOKEN_INVALID` (401) | Thu hồi quyền app trên GitHub (Settings → Applications), rồi đồng bộ lại |
| `EMPTY_REPOSITORY` (409) | Tạo một repo trống, cài app cho repo đó, thêm vào workspace rồi đồng bộ |
