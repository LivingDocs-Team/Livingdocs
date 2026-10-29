# FR-GH-04 — Chuẩn hóa dữ liệu đầu vào cho Code Analyzer

| Mục | Nội dung |
|---|---|
| Story / Task Jira | LD-63; contract phân tích liên quan LD-395 |
| Người thực hiện | Nhân tham gia tích hợp luồng đồng bộ và phân tích |
| Thành phần | GitHub Integration Service: `sync/AnalysisInput.java`, `RepositorySyncController` |
| Tác nhân | GitHub Integration Service gọi Code Analyzer |
| Phụ thuộc | FR-GH-03; Code Analyzer `POST /api/v1/analyze-repo` |
| Mục tiêu | Chuyển snapshot thành request JSON đúng schema mà Code Analyzer có thể xử lý trực tiếp |

## 1. Mô tả

Hệ thống chuyển snapshot đồng bộ gần nhất thành `AnalysisInput`. Vì Code Analyzer chạy như service riêng, request phải mang nội dung file trong JSON. Không dùng đường dẫn file cục bộ và không đưa token, email hoặc thông tin xác thực vào payload.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-GH-04.1 | `AnalysisInput` có đúng ba trường cấp cao: `scope`, `target`, `files`. `scope` luôn là `"repository"`; `target` là tên đầy đủ `owner/repo`; `files` là danh sách `FileInput`. |
| FR-GH-04.2 | Mỗi `FileInput` chỉ có `path`, `language`, `content`. `language` viết thường, ví dụ `java` hoặc `python`; `content` là nội dung file thực lấy từ GitHub. |
| FR-GH-04.3 | Chỉ lấy `SourceFile` có nội dung. Bỏ qua file `NOT_REQUESTED`, `TOO_LARGE`, `BINARY`, `UNAVAILABLE` và giữ thứ tự file theo snapshot. |
| FR-GH-04.4 | Nếu không có snapshot gần nhất, trả 404 và yêu cầu sync trước. Nếu repo không thuộc user hoặc không tồn tại, trả 403/404 tương ứng. |
| FR-GH-04.5 | JSON phải tương thích với Code Analyzer: không đổi `target` thành `repo_name`, không đổi `files[].path/language/content`, không tự thêm field chưa được contract chấp nhận. |
| FR-GH-04.6 | Payload không chứa access token, client secret, service secret, email tác giả commit hoặc thông tin người dùng không cần thiết. |

## 3. API

`GET /api/repositories/{id}/sync/latest/analysis-input`

Ví dụ response:

```json
{
  "scope": "repository",
  "target": "LivingDocs-Team/Livingdocs",
  "files": [
    {
      "path": "src/main.py",
      "language": "python",
      "content": "def main():\n    return 0\n"
    }
  ]
}
```

## 4. Luồng chính

1. Xác thực caller nội bộ và user sở hữu repository.
2. Đọc snapshot gần nhất.
3. Chuyển các file có nội dung thành `FileInput`.
4. Trả JSON đúng schema để caller gửi sang Code Analyzer.

## 5. Luồng lỗi

- Không có snapshot: `404`, yêu cầu sync trước.
- User không sở hữu repository: `403`.
- Repository không tồn tại: `404`.
- File bị skip hoặc không có nội dung: loại khỏi `files`, không tạo content giả.

## 6. Tiêu chí chấp nhận

- **AC-GH-04.1:** Snapshot có hai file có nội dung và một file `TOO_LARGE` thì `files` chỉ có hai file có nội dung.
- **AC-GH-04.2:** `scope`, `target`, thứ tự file và tên field khớp contract.
- **AC-GH-04.3:** JSON trả về có thể gửi thẳng tới `POST /api/v1/analyze-repo` mà không cần đổi field.
- **AC-GH-04.4:** Không có snapshot trả 404; user không sở hữu repo trả 403.
