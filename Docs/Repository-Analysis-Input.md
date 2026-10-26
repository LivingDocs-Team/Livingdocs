# Cung cấp dữ liệu mã nguồn cho phân tích code (Repository Analysis Input)

| Mục | Nội dung |
|---|---|
| Người làm | Đặng Lê Hiển Hải (TV2) |
| Jira | Story LD-24; task LD-63 (Sprint 2), LD-23 (Sprint 3: thống nhất định dạng với service phân tích, contract LD-395) |
| Code | `services/github-integration-service`: `sync/AnalysisInput.java`, endpoint trong `controller/RepositorySyncController` |
| Phụ thuộc | Repository Synchronization (`RepositorySnapshot`, `RepositorySyncService.latest`) |

## 1. Mục tiêu

Từ kết quả đồng bộ gần nhất của một repo, tạo sẵn dữ liệu đúng định dạng mà **Code Analyzer** nhận ở `POST /api/v1/analyze-repo`. Code Analyzer chạy riêng, không có code của repo trên máy, nên nội dung file phải gửi kèm trong dữ liệu. Kết quả phân tích sau đó được chuyển tiếp sang AI service (`POST /generate`) để sinh tài liệu.

## 2. Dữ liệu: `sync/AnalysisInput`

```java
public record AnalysisInput(String scope, String target, List<FileInput> files) {
    public AnalysisInput {
        files = files == null ? List.of() : List.copyOf(files);
    }

    public record FileInput(String path, String language, String content) {
    }

    /** Chuyển kết quả đồng bộ thành dữ liệu cho service phân tích. File không có nội dung bị bỏ qua. */
    public static AnalysisInput from(RepositorySnapshot snapshot) {
        List<FileInput> files = snapshot.analyzableFiles().stream()
                .map(f -> new FileInput(f.path(), f.language(), f.content()))
                .toList();
        return new AnalysisInput("repository", snapshot.repository().fullName(), files);
    }
}
```

Quy tắc:

- `scope` luôn là `"repository"`.
- `target` là tên đầy đủ của repo theo GitHub, ví dụ `LivingDocs-Team/Livingdocs`. Code Analyzer bắt buộc có trường này (thiếu thì trả `422`).
- `files` chỉ gồm file đã tải được nội dung (`SourceFile.hasContent()`), giữ thứ tự theo đường dẫn. File `TOO_LARGE`, `BINARY`, `UNAVAILABLE`, `NOT_REQUESTED` không có trong `files`.
- `language` viết thường (`java`, `python`), giống cách Code Analyzer nhận diện.
- JSON dùng đúng tên field của record: `scope`, `target`, `files[].path`, `files[].language`, `files[].content`. Không có token, email hay thông tin cá nhân.

## 3. API

| Method | Path | Kết quả |
|---|---|---|
| GET | `/api/repositories/{id}/sync/latest/analysis-input` | `200` `AnalysisInput` từ lần đồng bộ gần nhất |

Trong `RepositorySyncController`, cần header `X-User-Id`:

```java
@GetMapping("/api/repositories/{id}/sync/latest/analysis-input")
public AnalysisInput analysisInput(@RequestHeader(USER_HEADER) String userId, @PathVariable UUID id) {
    return AnalysisInput.from(syncService.latest(userId, id));
}
```

Ví dụ response (file mẫu đầy đủ: `services/github-integration-service/docs/samples/analysis-input.sample.json`, 3 file thật của repo nhóm):

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

## 4. Luồng sử dụng

1. Người dùng đồng bộ repo (`POST /api/repositories/{id}/sync`).
2. Lấy `GET /api/repositories/{id}/sync/latest/analysis-input`. Dữ liệu lấy từ bộ nhớ, không gọi lại GitHub.
3. Gửi nguyên body sang Code Analyzer `POST /api/v1/analyze-repo`. Code Analyzer trả `{"scope", "target", "files": [FileAnalysis]}`.
4. Gửi nguyên kết quả đó sang AI service `POST /generate` để sinh tài liệu Markdown. Từ LD-396, bước sinh tài liệu `POST /api/repositories/{id}/documentation/generate` (Nhân làm) dùng lại chính `AnalysisInput.from(snapshot)`.

## 5. Lỗi

| Tình huống | Kết quả |
|---|---|
| Chưa đồng bộ lần nào, hoặc service vừa khởi động lại | `404 NOT_FOUND`, thông báo yêu cầu gọi `POST /api/repositories/{id}/sync` trước |
| Repo không phải của người dùng | `403 FORBIDDEN` |
| Repo không tồn tại | `404 NOT_FOUND` |
| `id` không phải UUID | `400 BAD_REQUEST` |
| Đồng bộ thành công nhưng không có file nào có nội dung | `200` với `files` rỗng |

## 6. Test cần có

- `AnalysisInputTest` (2, unit test):
  - Snapshot của repo `acme/shop` có 3 file: `app/main.py` có nội dung, `src/Big.java` `TOO_LARGE` không có nội dung, `src/App.java` có nội dung. `AnalysisInput.from` cho `scope = "repository"`, `target = "acme/shop"`, `files` đúng 2 phần tử `(app/main.py, python, ...)` và `(src/App.java, java, "class App {}")`.
  - JSON của `AnalysisInput` bằng đúng `{"scope": "repository", "target": "acme/shop", "files": [{"path": "src/App.java", "language": "java", "content": "class App {}"}]}` (so sánh bằng `JsonNode` của Jackson).
- `RepositorySyncApiTest`: trước khi đồng bộ, `GET .../sync/latest` trả `404 NOT_FOUND`. Sau khi đồng bộ repo `acme/shop` có 1 file `src/App.java`: `/sync/latest` không kèm nội dung file, còn `/sync/latest/analysis-input` trả `scope = "repository"`, `target = "acme/shop"`, 1 file `src/App.java`, `language = "java"`, kèm đúng nội dung.

## 7. Tiêu chí chấp nhận

- Body trả về gửi thẳng được sang Code Analyzer mà không cần sửa.
- Chỉ file có nội dung mới có trong `files`.
- Đã chạy thử cả chuỗi ngày 20/10/2026: gửi `analysis-input.sample.json` sang Code Analyzer nhận `target = LivingDocs-Team/Livingdocs` và 3 file trạng thái `ok`; gửi tiếp kết quả sang AI service thì job hoàn thành và trả tài liệu Markdown bắt đầu bằng `# LivingDocs-Team/Livingdocs`.
