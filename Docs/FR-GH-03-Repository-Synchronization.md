# FR-GH-03 — Đồng bộ repository từ GitHub

| Mục | Nội dung |
|---|---|
| Story / Task Jira | LD-24; LD-63 — Repository Synchronization |
| Người thực hiện | Nhân (phối hợp với Đăng và các thành viên liên quan) |
| Thành phần | GitHub Integration Service: `sync/`, `client/GitHubClient`, `service/RepositorySyncService`, `controller/RepositorySyncController`; Backend BFF là caller nội bộ |
| Tác nhân | Người dùng đã đăng nhập, thông qua Backend BFF |
| Phụ thuộc | GitHub Account Connection; Repository Management; GitHub App/token; RepositorySnapshot |
| Mục tiêu | Lấy snapshot nhất quán của repository tại một commit, chọn file nguồn có thể phân tích, trả metadata/trạng thái và cung cấp dữ liệu để phân tích code |

## 1. Mô tả

Người dùng yêu cầu đồng bộ một repository đã được thêm vào workspace của chính họ. Hệ thống xác thực quyền sở hữu, đọc repository và commit từ GitHub, lấy cây file tại đúng commit đó, chọn file theo giới hạn cấu hình, tải nội dung file được hỗ trợ, thu thập thống kê/ngôn ngữ/commit gần đây và trả kết quả đồng bộ.

Kết quả snapshot gần nhất được giữ trong bộ nhớ theo implementation hiện tại; không được giả định dữ liệu này tồn tại sau khi service khởi động lại.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-GH-03.1 | Chỉ xử lý request nội bộ đã được Backend BFF xác thực. Mọi API đồng bộ phải nhận danh tính người dùng do Backend truyền qua `X-User-Id`; không tin `userId` do browser tự gửi. |
| FR-GH-03.2 | Chỉ chủ sở hữu repository được xem hoặc đồng bộ repo đó. Nếu repository không thuộc GitHub connection của user hiện tại, trả `403 FORBIDDEN`; không trả snapshot hoặc nội dung file. |
| FR-GH-03.3 | `POST /api/repositories/{id}/sync` nhận body tùy chọn. Body vắng mặt hoặc `{}` dùng nhánh mặc định, `includeContent=true`, `maxFiles=200`; giới hạn kích thước file mặc định 200.000 byte và 20 commit gần đây. |
| FR-GH-03.4 | Cho phép chọn `branch`, `includeContent`, `maxFiles`, `maxFileSizeBytes`, `recentCommitLimit`, `languages`. Chuẩn hóa branch toàn khoảng trắng thành `null`; chuẩn hóa ngôn ngữ thành chữ thường; danh sách ngôn ngữ rỗng dùng mặc định `java`, `python`. |
| FR-GH-03.5 | Từ chối tham số không hợp lệ: `maxFiles` ngoài `1..1000`, `maxFileSizeBytes < 1`, `recentCommitLimit` ngoài `0..100`, hoặc tên repository không đúng dạng `owner/repo`. |
| FR-GH-03.6 | Lấy metadata repository, commit của branch/ref, tree đệ quy tại SHA của commit đó, blob nội dung, ngôn ngữ và danh sách commit gần đây. Các file phải được xác định từ cùng một commit snapshot. |
| FR-GH-03.7 | Phân loại file theo phần mở rộng và sắp xếp danh sách file theo `path`. Hỗ trợ phát hiện: `java`, `python`, `javascript`, `typescript`, `kotlin`, `go`, `ruby`, `php`, `csharp`, `c`, `cpp`, `rust`, `swift`, `scala`, `sql`. Không tự gán ngôn ngữ cho file không nhận diện được. |
| FR-GH-03.8 | Không tải nội dung file vượt `maxFileSizeBytes`, file nhị phân hoặc file không tải được. Gán `SkipReason` tương ứng: `TOO_LARGE`, `BINARY`, `UNAVAILABLE`; khi không yêu cầu tải nội dung, dùng `NOT_REQUESTED`. |
| FR-GH-03.9 | `RepositorySnapshot` chứa repository metadata, branch, head commit, thống kê ngôn ngữ, file đã chọn theo path, commit gần đây, thống kê đồng bộ, cảnh báo và thời điểm UTC. Dữ liệu snapshot không bị sửa ngoài ý muốn sau khi tạo. |
| FR-GH-03.10 | Trạng thái chuyển sang `SYNCING` khi bắt đầu. Thành công chuyển sang `CONNECTED` và cập nhật `lastSyncedAt`, `defaultBranch`, `fullName` nếu đổi tên. Với `REPOSITORY_NOT_FOUND`, `ACCESS_DENIED`, `INVALID_REPOSITORY`, chuyển sang `ERROR`; với lỗi khác giữ trạng thái trước đó trừ khi contract hiện tại quy định khác. |
| FR-GH-03.11 | `POST /sync` và `GET /sync/latest` chỉ trả metadata, thống kê, warnings và cờ `analyzable`; không trả nội dung source code. Nội dung chỉ được gửi qua endpoint `analysis-input` có kiểm tra quyền. |
| FR-GH-03.12 | `GET /api/repositories/{id}/sync/latest` trả snapshot gần nhất. Nếu chưa đồng bộ hoặc snapshot không còn sau restart, trả `404` yêu cầu đồng bộ trước. |
| FR-GH-03.13 | Nếu tree bị `truncated`, đạt giới hạn file hoặc thiếu một phần metadata/nội dung, trả kết quả kèm cảnh báo; không báo dữ liệu đầy đủ khi có phần bị thiếu. |
| FR-GH-03.14 | Ánh xạ lỗi GitHub: `INVALID_REQUEST` 400; `INVALID_REPOSITORY` 400; `TOKEN_INVALID` 401; `ACCESS_DENIED` 403; `REPOSITORY_NOT_FOUND` 404; `BRANCH_NOT_FOUND` 404; `EMPTY_REPOSITORY` 409; `RATE_LIMITED` 429; `GITHUB_UNAVAILABLE` 503; `UNEXPECTED_GITHUB_RESPONSE` 502. Chỉ `RATE_LIMITED` và `GITHUB_UNAVAILABLE` được đánh dấu có thể thử lại. |
| FR-GH-03.15 | Với `RATE_LIMITED`, nếu GitHub cung cấp thời điểm thử lại thì trả retry metadata và header `Retry-After` theo contract. Không retry vô hạn. |
| FR-GH-03.16 | Không lưu email tác giả commit trong snapshot. Chỉ giữ trường cần thiết như SHA, message, tên/login tác giả, thời điểm và URL. Không ghi token/secret vào log hoặc response. |

## 3. API

| Method | Endpoint | Mục đích |
|---|---|---|
| POST | `/api/repositories/{id}/sync` | Đồng bộ repository, trả metadata |
| GET | `/api/repositories/{id}/sync/latest` | Lấy kết quả đồng bộ gần nhất |
| GET | `/api/repositories/{id}/sync/latest/analysis-input` | Lấy nội dung file cho phân tích, sau khi kiểm tra quyền |

Lỗi API dùng cấu trúc chung, ví dụ:

```json
{
  "status": 404,
  "code": "REPOSITORY_NOT_FOUND",
  "message": "Không tìm thấy repository",
  "timestamp": "2026-10-12T15:20:00Z"
}
```

## 4. Luồng chính

1. Backend BFF xác thực session, gắn service credential và `X-User-Id`.
2. GitHub Integration xác minh credential, tìm repository và xác nhận ownership.
3. Đặt trạng thái `SYNCING`, đọc repository/branch/commit/tree từ GitHub.
4. Lọc và sắp xếp file, tải nội dung trong giới hạn, thu thập metadata và warnings.
5. Lưu snapshot gần nhất trong bộ nhớ, cập nhật `CONNECTED` và thời điểm đồng bộ.
6. Trả metadata không chứa source code.

## 5. Luồng lỗi

| Trường hợp | HTTP | Hành vi |
|---|---:|---|
| Tham số sai | 400 | Từ chối trước khi đồng bộ |
| Token hết hạn/bị thu hồi | 401 | Báo cần kết nối lại |
| Không có quyền repo | 403 | Không tiết lộ nội dung |
| Repo/branch không tồn tại | 404 | Trả mã lỗi cụ thể |
| Repository không có commit | 409 | Báo repository rỗng |
| GitHub rate limit | 429 | Trả `Retry-After` nếu có |
| Timeout/mạng/GitHub 5xx | 503 | Có thể thử lại có giới hạn |
| Response GitHub sai cấu trúc | 502 | Không xử lý dữ liệu sai |

## 6. Quy tắc nghiệp vụ

- Snapshot hiện được lưu trong bộ nhớ; không giả định tồn tại qua restart.
- File gửi sang Code Analyzer phải có `content`; không dùng đường dẫn máy chạy service thay cho nội dung file.
- Không expose source code trong endpoint snapshot thông thường.
- Không bỏ qua kiểm tra ownership chỉ để test chạy được.
- Tái sử dụng DTO/enum/exception hiện có khi phù hợp.

## 7. Tiêu chí chấp nhận

- **AC-GH-03.1:** Sync repository hợp lệ trả metadata đúng repo/branch/head commit, file sắp theo path, có thống kê và không chứa `content`.
- **AC-GH-03.2:** `maxFiles=0` hoặc `maxFiles=1001` bị từ chối bằng lỗi 400.
- **AC-GH-03.3:** User khác gọi sync/latest cho repo không thuộc mình nhận 403.
- **AC-GH-03.4:** Repo rỗng trả `EMPTY_REPOSITORY`/409; branch sai trả `BRANCH_NOT_FOUND`/404; rate limit trả 429 và retry metadata nếu có.
- **AC-GH-03.5:** File binary, quá lớn hoặc tải thất bại được đánh dấu skip reason/warning; không nằm trong danh sách file có thể phân tích.
- **AC-GH-03.6:** Unit/API tests dùng GitHub giả; có test cho 401, 403, 404, 409, 422 từ GitHub, 429, timeout, 5xx và malformed response.
