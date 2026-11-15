# FR-GH-06 Phát hiện thay đổi mã nguồn

| Mục | Nội dung |
|---|---|
| Feature Jira | epic LD-8 Automatic Documentation Update |
| Task đã làm | LD-116 (LD-117 Detect Source Code Changes, LD-118 Process Repository Commits, LD-119 Process Pull Request Changes, LD-120 Identify Changed Code Entities, LD-121 Test Source Change Detection); PR #87 vào nhánh LD-68, LD-401 gộp vào `main` (PR #86) |
| Người thực hiện | Lê Hiền Hải Đăng |
| Thành phần | GitHub Integration Service: package `change/` (`SourceChangeListener`, `SourceChangeRequest`, `UnifiedDiff`, `CodeAnalyzerClient`, `ChangedEntityDetector`, `CodeEntity`, `ChangedEntity`, `SourceChangeException`), `service/SourceChangeService`, `controller/SourceChangeController`, entity `SourceChange`, `SourceChangeFile`, `SourceChangeEntity`, migration `V6__source_changes.sql`, hàm `getCommitFiles`, `listPullRequestChangedFiles` trong `client/GitHubClient` |
| Tác nhân | FR-GH-05 (webhook đã lưu); Code Analyzer (`POST /api/v1/analyze-repo`, cổng 8000); bước cập nhật tài liệu đọc kết quả qua API (FR-GH-07, LD-128 của Linh) |
| Phụ thuộc | FR-GH-05 (commit và Pull Request nhận từ webhook), FR-GH-03 (quy tắc chọn file Java/Python), FR-GH-01 (token GitHub) |

## 1. Mô tả

Sau khi webhook được lưu (FR-GH-05), service chạy nền bước phát hiện thay đổi cho mỗi commit mới trên nhánh mặc định và mỗi Pull Request đang mở có commit head mới. Service lấy danh sách file thay đổi từ GitHub, chỉ giữ file Java/Python, dựng lại nội dung trước và sau thay đổi, gửi cả hai bản sang Code Analyzer rồi so khoảng dòng của từng class, method, function, endpoint với các dòng được thêm/xoá trong diff để biết entity nào được thêm, sửa hoặc xoá. Kết quả được lưu thành một **source change** để bước tìm tài liệu bị ảnh hưởng (FR-GH-07) và bước cập nhật tài liệu (LD-128) đọc qua API. Lỗi GitHub hoặc Code Analyzer được lưu lại kèm mã lỗi để người dùng chạy lại.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-GH-06.1 | Phát hiện cho commit mới trên **nhánh mặc định** của repo (commit trên nhánh khác vẫn được lưu ở FR-GH-05 nhưng không phát hiện, vì tài liệu đi theo nhánh mặc định và thay đổi trên nhánh khác được xét qua Pull Request). |
| FR-GH-06.2 | Phát hiện cho Pull Request **đang mở** có commit head mới (`opened`, `synchronize`). Đóng hoặc merge Pull Request không phát hiện lại. |
| FR-GH-06.3 | Chạy nền (2 luồng) sau khi transaction lưu webhook đã commit, để webhook trả về ngay. Lỗi bất ngờ của bước nền chỉ ghi log, không ảnh hưởng webhook. |
| FR-GH-06.4 | Lấy file thay đổi: commit thì `GET /repos/{owner}/{repo}/commits/{sha}` (GitHub trả tối đa 300 file); Pull Request thì `GET /repos/{owner}/{repo}/pulls/{number}/files` (100 file mỗi trang, tối đa 10 trang). Chỉ giữ file Java/Python theo đúng quy tắc chọn file khi đồng bộ (FR-GH-03): nhận diện ngôn ngữ theo đuôi, bỏ thư viện, thư mục build và công cụ. |
| FR-GH-06.5 | Loại thay đổi của file theo GitHub: `added` → `ADDED`, `removed` → `REMOVED`, `renamed` → `RENAMED` (kèm `previousPath`), còn lại → `MODIFIED`; kèm số dòng thêm và xoá. |
| FR-GH-06.6 | Nội dung sau thay đổi tải từ blob theo SHA của file. Nội dung trước thay đổi **dựng lại từ nội dung sau và `patch`** của GitHub (`UnifiedDiff`), không gọi thêm GitHub. File `ADDED` không có bản trước; file `REMOVED` không có bản sau. |
| FR-GH-06.7 | Không tìm entity cho file (vẫn liệt kê file, kèm `skippedReason`): quá 50 file mã nguồn trong một thay đổi → `TOO_MANY_FILES` (từ file thứ 51); GitHub không gửi `patch` (file quá lớn) → `PATCH_UNAVAILABLE`; file lớn hơn 200.000 byte → `FILE_TOO_LARGE`; không giải mã được nội dung, hoặc Code Analyzer báo file rỗng, lỗi cú pháp, không hỗ trợ → `NOT_ANALYZED`. |
| FR-GH-06.8 | Gửi các bản trước và bản sau sang Code Analyzer (`POST /api/v1/analyze-repo`, scope `file`, target `owner/repo`), mỗi bên một lần; không có file nào để phân tích thì không gọi. Entity lấy từ kết quả: class (theo `kind` của analyzer: `CLASS`, `INTERFACE`, `ENUM`, `RECORD`, `ANNOTATION`), method (tên `Class.method`), function, endpoint (tên `GET /path`), kèm khoảng dòng `lineno`–`end_lineno`; entity không có khoảng dòng bị bỏ qua. |
| FR-GH-06.9 | Xác định entity thay đổi (`ChangedEntityDetector`): entity ở bản sau có dòng được **thêm** nằm trong khoảng dòng của nó là `ADDED` (nếu không có ở bản trước) hoặc `MODIFIED`; entity ở bản trước có dòng bị **xoá** nằm trong khoảng dòng của nó là `REMOVED` (nếu không còn ở bản sau) hoặc `MODIFIED`. Entity không bị chạm tới thì không báo. `startLine`/`endLine` là dòng ở bản sau; với `REMOVED` là dòng ở bản trước. |
| FR-GH-06.10 | Lưu kết quả thành source change trạng thái `PENDING`. Mỗi (repo, loại kích hoạt `COMMIT`/`PULL_REQUEST`, SHA) chỉ có một source change; chạy lại thì thay toàn bộ danh sách file. Commit hoặc Pull Request không có file mã nguồn nào thay đổi thì không lưu (chạy lại mà không còn file nào thì xoá source change cũ). |
| FR-GH-06.11 | Lỗi GitHub, Code Analyzer hoặc kết nối GitHub được lưu thành source change `FAILED` kèm `errorCode`, `errorMessage` (≤ 500 ký tự) và không có file. |
| FR-GH-06.12 | Xem: `GET /api/repositories/{id}/source-changes` trả tối đa 50 source change, mới nhất trước. Chạy lại: `POST /api/repositories/{id}/source-changes/{changeId}/retry` chỉ cho source change `FAILED` (khác thì `409 SOURCE_CHANGE_NOT_FAILED`); chạy lại mà không còn file mã nguồn nào thì `204`. Chỉ người xem được repo mới xem hoặc chạy lại được (`403` / `404`). |

## 3. API

Trình duyệt và các service khác gọi qua Backend (BFF), xem [README](README.md).

| Method | Endpoint | Kết quả | Yêu cầu |
|---|---|---|---|
| GET | `/api/repositories/{id}/source-changes` | `200` danh sách source change | FR-GH-06.12 |
| POST | `/api/repositories/{id}/source-changes/{changeId}/retry` | `200` source change sau khi chạy lại; `204` khi không còn file mã nguồn; `409 SOURCE_CHANGE_NOT_FAILED` | FR-GH-06.11, 06.12 |

Ví dụ response rút gọn (FR-GH-07 thêm các trường tài liệu bị ảnh hưởng vào cùng response):

```json
[{"id": "4f1c...", "trigger": "COMMIT", "commitSha": "<40 ký tự hex>", "pullRequestNumber": null,
  "status": "PENDING", "errorCode": null, "errorMessage": null,
  "createdAt": "2026-11-06T05:00:00Z", "updatedAt": "2026-11-06T05:00:00Z",
  "files": [{"path": "src/main/java/acme/Invoice.java", "previousPath": null, "change": "MODIFIED",
    "language": "java", "additions": 4, "deletions": 4, "skippedReason": null,
    "entities": [
      {"kind": "METHOD", "name": "Invoice.total", "change": "MODIFIED", "startLine": 2, "endLine": 4},
      {"kind": "METHOD", "name": "Invoice.tax", "change": "ADDED", "startLine": 6, "endLine": 8},
      {"kind": "METHOD", "name": "Invoice.discount", "change": "REMOVED", "startLine": 6, "endLine": 8}]}]}]
```

## 4. Dữ liệu

Migration `V6__source_changes.sql`:

| Bảng | Cột chính | Ràng buộc |
|---|---|---|
| `source_changes` | `repository_id`, `trigger_type` (`COMMIT` / `PULL_REQUEST`), `commit_sha` (commit, hoặc commit head của Pull Request), `pr_number`, `status` (`PENDING` / `FAILED`), `error_code`, `error_message` (≤ 500), `created_at`, `updated_at` | Duy nhất theo (`repository_id`, `trigger_type`, `commit_sha`); xoá theo repo |
| `source_change_files` | `source_change_id`, `path`, `previous_path`, `change_type` (`ADDED` / `MODIFIED` / `REMOVED` / `RENAMED`), `language`, `additions`, `deletions`, `skipped_reason` | Xoá theo source change |
| `source_change_entities` | `file_id`, `kind`, `name` (≤ 500), `change_type` (`ADDED` / `MODIFIED` / `REMOVED`), `start_line`, `end_line` | Xoá theo file |

## 5. Luồng chính

1. FR-GH-05 lưu một commit mới trên nhánh mặc định, hoặc một Pull Request đang mở có head mới; sau khi transaction commit, bước phát hiện chạy nền.
2. Lấy token GitHub của chủ kết nối (tự làm mới nếu cần), lấy danh sách file thay đổi, giữ file Java/Python.
3. Với từng file: tải nội dung sau thay đổi, dựng lại nội dung trước từ `patch`, ghi lý do bỏ qua nếu có.
4. Gửi bản sau và bản trước sang Code Analyzer, so khoảng dòng entity với diff, ghi các entity thay đổi.
5. Lưu source change `PENDING` (hoặc `FAILED` nếu có lỗi). Bước tìm tài liệu bị ảnh hưởng (FR-GH-07) chạy tiếp ngay sau đó.
6. Người dùng hoặc service khác xem danh sách qua `GET .../source-changes`; source change `FAILED` được chạy lại qua `POST .../retry`.

## 6. Luồng lỗi

Lỗi trong lúc phát hiện không trả về cho ai (bước chạy nền), mà được lưu vào source change `FAILED`:

| `errorCode` | Khi nào |
|---|---|
| `GITHUB_UNAVAILABLE` | Mất mạng, quá thời gian chờ, GitHub lỗi 5xx |
| `RATE_LIMITED` | Hết lượt gọi GitHub API |
| `TOKEN_INVALID` | GitHub trả 401 |
| `ACCESS_DENIED` | GitHub trả 403 |
| `REPOSITORY_NOT_FOUND` | GitHub trả 404 hoặc 422 (repo hoặc commit không còn) |
| `UNEXPECTED_GITHUB_RESPONSE` | GitHub trả lỗi khác |
| `ANALYZER_UNAVAILABLE` | Code Analyzer không gọi được hoặc trả dữ liệu sai |
| `GITHUB_NOT_CONNECTED` (và mã khác của FR-GH-01) | Chủ repo chưa kết nối GitHub hoặc cần kết nối lại |

Lỗi khi gọi API:

| Mã | HTTP | Khi nào |
|---|---|---|
| `SOURCE_CHANGE_NOT_FAILED` | 409 | Chạy lại source change không ở trạng thái `FAILED` |
| `NOT_FOUND` | 404 | Repo không có, hoặc source change không thuộc repo |
| `FORBIDDEN` | 403 | Không có quyền xem repo |

Mã lỗi GitHub dùng chung với bảng lỗi đồng bộ (FR-GH-03) để frontend dùng chung thông báo.

## 7. Quy tắc nghiệp vụ

- Chỉ file Java/Python ngoài thư viện và thư mục build được xét, giống khi đồng bộ.
- Tối đa 50 file mã nguồn được phân tích trong một thay đổi; file lớn hơn 200.000 byte không tải.
- Một entity chỉ được báo khi diff chạm vào khoảng dòng của nó; đổi comment ngoài entity không tạo entity thay đổi.
- Không lưu source change rỗng.
- Lỗi được lưu lại thay vì bị bỏ qua, để người dùng chạy lại khi GitHub hoặc Code Analyzer hoạt động trở lại.

## 8. Tiêu chí chấp nhận

- Push lên nhánh mặc định thay đổi `Invoice.java` (sửa `total()`, thay `discount()` bằng `tax()`): source change `PENDING` có 1 file `MODIFIED` và entity `Invoice` `MODIFIED`, `Invoice.total` `MODIFIED`, `Invoice.tax` `ADDED`, `Invoice.discount` `REMOVED`; `README.md` không được liệt kê.
- Commit trên nhánh khác không được phát hiện; Pull Request mở mới được phát hiện, đóng thì không.
- GitHub lỗi: source change `FAILED`, `errorCode = GITHUB_UNAVAILABLE`; chạy lại khi GitHub hoạt động thì thành `PENDING` có đủ entity; chạy lại lần nữa thì `409`.
- Nội dung trước thay đổi dựng lại từ nội dung sau và `patch` khớp đúng file gốc.

## 9. Kiểm thử

Test nằm trong `services/github-integration-service/src/test/java/com/livingdocs/github/`, chạy bằng `mvn verify` (job CI **GitHub Integration Service Test**).

| Test | Số test | Nội dung |
|---|---|---|
| `SourceChangeDetectionTest` | 8 | `@SpringBootTest` + MockMvc + H2, GitHub và Code Analyzer giả: commit trên nhánh mặc định được phát hiện sau webhook, đủ entity thay đổi; commit trên nhánh khác được lưu nhưng không phát hiện; Pull Request mở có head mới được phát hiện, đóng thì không; commit không có file mã nguồn thì không lưu; lỗi GitHub lưu thành `FAILED` và chạy lại phát hiện được; Code Analyzer lỗi lưu thành `FAILED`; file không có `patch` được liệt kê không kèm entity; người khác không xem và chạy lại được |
| `change/ChangedEntityDetectorTest` | 3 | Phân loại `ADDED`, `MODIFIED`, `REMOVED`; entity ngoài các dòng thay đổi không được báo; xoá một trong hai method trùng tên là sửa (`MODIFIED`) |
| `change/UnifiedDiffTest` | 4 | Dòng thêm dùng số dòng mới, dòng xoá dùng số dòng cũ; dòng xoá chỉ tính khi nằm trong khoảng; dựng lại nội dung cũ từ nội dung mới và patch; file thêm mới và file bị xoá |
| `change/CodeAnalyzerClientTest` | 1 | Đọc class, method, function, endpoint kèm khoảng dòng từ kết quả Code Analyzer |
