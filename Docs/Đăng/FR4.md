# FR-GH-04 Cung cấp dữ liệu mã nguồn cho Code Analyzer

| Mục | Nội dung |
|---|---|
| Feature Jira | LD-24 Repository Synchronization (epic LD-6 GitHub Integration) |
| Task đã làm | LD-63 (dữ liệu cho phân tích, file mẫu và hướng dẫn test); LD-23: thống nhất định dạng với Code Analyzer theo contract LD-395 |
| Người thực hiện | Lê Hiền Hải Đăng |
| Thành phần | GitHub Integration Service (cổng 8082): `sync/AnalysisInput`, endpoint trong `controller/RepositorySyncController` |
| Tác nhân | Bước sinh tài liệu của GitHub Integration Service (LD-396, gọi Code Analyzer rồi AI Service); người kiểm thử qua Swagger |
| Phụ thuộc | FR-GH-03 (kết quả đồng bộ gần nhất) |

## 1. Mô tả

Từ kết quả đồng bộ gần nhất của một repo, tạo dữ liệu đúng định dạng mà **Code Analyzer** nhận ở `POST /api/v1/analyze-repo`. Code Analyzer chạy riêng và không có code của repo trên máy, nên nội dung file phải gửi kèm. Kết quả phân tích sau đó được chuyển sang AI Service (`POST /generate`) để sinh tài liệu.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-GH-04.1 | Tạo dữ liệu `{"scope", "target", "files"}` từ kết quả đồng bộ gần nhất của repo, không gọi lại GitHub. |
| FR-GH-04.2 | `scope` luôn là `"repository"`; `target` là tên đầy đủ của repo theo GitHub, ví dụ `LivingDocs-Team/Livingdocs` (Code Analyzer bắt buộc có `target`). |
| FR-GH-04.3 | `files` chỉ gồm file đã tải được nội dung, giữ thứ tự theo đường dẫn; mỗi phần tử `{"path", "language", "content"}`. File `TOO_LARGE`, `BINARY`, `UNAVAILABLE`, `NOT_REQUESTED` không có trong `files`. |
| FR-GH-04.4 | `language` viết thường (`java`, `python`), giống cách Code Analyzer nhận diện. |
| FR-GH-04.5 | Dữ liệu không chứa token, email hay thông tin cá nhân. |
| FR-GH-04.6 | Chỉ chủ repo được lấy dữ liệu (`403` với người khác). Chưa đồng bộ lần nào hoặc service vừa khởi động lại thì `404` kèm hướng dẫn đồng bộ trước. |
| FR-GH-04.7 | Đồng bộ thành công nhưng không có file nào có nội dung thì trả `200` với `files` rỗng. |
| FR-GH-04.8 | Body trả về gửi thẳng được sang Code Analyzer mà không cần sửa. Bước sinh tài liệu `POST /api/repositories/{id}/documentation/generate` (LD-396) dùng lại đúng hàm tạo dữ liệu này. |

## 3. API

| Method | Endpoint | Kết quả | Yêu cầu |
|---|---|---|---|
| GET | `/api/repositories/{id}/sync/latest/analysis-input` | `200` dữ liệu cho Code Analyzer từ lần đồng bộ gần nhất | FR-GH-04.1 – 04.7 |

Endpoint cần header `X-User-Id` như các API khác của service (trình duyệt đi qua Backend BFF). Ví dụ response (file mẫu đầy đủ: `services/github-integration-service/docs/samples/analysis-input.sample.json`, 3 file thật của repo nhóm):

```json
{
  "scope": "repository",
  "target": "LivingDocs-Team/Livingdocs",
  "files": [
    {"path": "app/analyzer.py", "language": "python", "content": "import ast\n..."},
    {"path": "backend/src/main/java/com/cnpm/backend/dto/LoginRequest.java", "language": "java", "content": "\npackage com.cnpm.backend.dto;\n..."}
  ]
}
```

## 4. Luồng chính

1. Developer đồng bộ repo (FR-GH-03, `POST /api/repositories/{id}/sync`).
2. Lấy `GET /api/repositories/{id}/sync/latest/analysis-input`; dữ liệu lấy từ bộ nhớ, không gọi lại GitHub.
3. Gửi nguyên body sang Code Analyzer `POST /api/v1/analyze-repo`; Code Analyzer trả `{"scope", "target", "files": [...]}` gồm lớp, hàm và endpoint của từng file.
4. Gửi kết quả đó sang AI Service `POST /generate` để sinh tài liệu Markdown (phần của Linh, FR-AI-01).

Từ LD-396, bước 2–4 chạy tự động khi Developer bấm Generate documentation.

## 5. Luồng lỗi

| Tình huống | Kết quả |
|---|---|
| Chưa đồng bộ lần nào, hoặc service vừa khởi động lại | `404 NOT_FOUND`, "Repository này chưa được đồng bộ lần nào (hoặc service vừa khởi động lại). Hãy gọi POST /api/repositories/{id}/sync trước." |
| Repo không phải của người dùng | `403 FORBIDDEN` |
| Repo không tồn tại | `404 NOT_FOUND` |
| `id` không phải UUID | `400 BAD_REQUEST` |
| Đồng bộ thành công nhưng không file nào có nội dung | `200` với `files` rỗng |

## 6. Quy tắc nghiệp vụ

- Dữ liệu cho phân tích luôn lấy từ lần đồng bộ thành công gần nhất, nên mọi file thuộc cùng một commit.
- Chỉ gửi file có nội dung; file bị bỏ qua khi đồng bộ không được gửi sang Code Analyzer.
- Không gửi thông tin cá nhân hay bí mật sang service khác.

## 7. Tiêu chí chấp nhận

- Body trả về gửi thẳng được sang Code Analyzer.
- Chỉ file có nội dung mới có trong `files`.
- Đã chạy thử cả chuỗi ngày 20/10/2026: gửi `analysis-input.sample.json` sang Code Analyzer nhận `target = LivingDocs-Team/Livingdocs` và 3 file trạng thái `ok`; gửi tiếp kết quả sang AI Service thì job hoàn thành và trả tài liệu Markdown bắt đầu bằng `# LivingDocs-Team/Livingdocs`.

## 8. Kiểm thử

| Test | Số test | Nội dung |
|---|---|---|
| `sync/AnalysisInputTest` | 2 | Repo `acme/shop` có 3 file, một file `TOO_LARGE` không có nội dung: kết quả có `scope = "repository"`, `target = "acme/shop"` và đúng 2 file có nội dung; JSON đúng từng tên trường mà Code Analyzer nhận |
| `RepositorySyncApiTest` (`latestAndAnalysisInput_returnLastSyncResult`) | 1 | Trước khi đồng bộ, xem kết quả trả `404`; sau khi đồng bộ, `/sync/latest` không kèm nội dung file, còn `/sync/latest/analysis-input` trả đúng file `src/App.java`, `language = "java"` và nội dung |
