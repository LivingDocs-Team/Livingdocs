# Hợp đồng dữ liệu LD-328 → LD-340

Tài liệu này mô tả định dạng kết quả phân tích mã nguồn (LD-328, Lâm) mà module sinh tài liệu
(LD-340, Linh) nhận vào. Hai bên cần thống nhất định dạng này trước khi triển khai sâu.
Ví dụ đầy đủ nằm trong `sample_data/sample_analysis.json`.

## Request gửi tới `POST /generate`

| Trường | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `scope` | `"file"` \| `"module"` \| `"repository"` | có | |
| `target` | string | có | Tên file, module hoặc repository |
| `files` | list `FileAnalysis` | có, ≥ 1 | Không được trùng `path` |
| `template_id` | string | không | Mặc định `default` |
| `output_language` | `"vi"` \| `"en"` | không | Mặc định `vi` |

## `FileAnalysis`: một file đã phân tích

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `path` | string, bắt buộc | Đường dẫn tương đối trong repository |
| `language` | string | Ví dụ `python` |
| `module` | string | Ví dụ `shop.services` |
| `status` | `ok` \| `empty` \| `invalid` \| `unsupported` | Mặc định `ok`. Khác `ok` thì file bị bỏ qua và ghi vào cảnh báo |
| `error` | string | Lý do khi `status` khác `ok` (ví dụ `SyntaxError line 3`) |
| `classes` | list `ClassInfo` | |
| `functions` | list `Function` | Hàm cấp module |
| `endpoints` | list `Endpoint` | |

**`ClassInfo`**: `name` (bắt buộc), `bases` (list string), `docstring`, `methods` (list `Function`).

**`Function`**: `name` (bắt buộc), `signature`, `parameters` (list `Parameter`), `return_type`,
`docstring`, `source` (đoạn code, tùy chọn; bị cắt còn 1.500 ký tự khi đưa vào prompt).

**`Parameter`**: `name` (bắt buộc), `type`, `default`, `description`.

**`Endpoint`**: `http_method` (GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS), `path` (bắt buộc),
`handler`, `parameters`, `request_body`, `response`.

## Lưu ý cho LD-328

- Gửi `source` của hàm và phương thức nếu có thể: AI mô tả chính xác hơn khi thấy code.
- File rỗng, file lỗi cú pháp hoặc ngôn ngữ chưa hỗ trợ: vẫn gửi kèm `status` và `error`
  thay vì bỏ khỏi danh sách, để tài liệu ghi rõ file nào không sinh được.
- `self` / `cls` không cần đưa vào `parameters`.

## Kết quả trả về (cho frontend, LD-298/304)

`GET /jobs/{id}` trả về `status` (`pending`/`running`/`completed`/`failed`), `progress`, `message`,
`warnings` và `file_results`. Mỗi phần tử `file_results` có `path` và `status`:

| `status` | Ý nghĩa |
|---|---|
| `generated` | AI sinh tài liệu thành công |
| `offline` | Không có API key, tài liệu dựng từ dữ liệu phân tích |
| `fallback` | AI lỗi sau khi thử lại, tài liệu dựng từ dữ liệu phân tích |
| `skipped` | Bộ phân tích không xử lý được file |
| `failed` | Lỗi không mong muốn ở riêng file này |

Job chỉ `failed` khi không file nào sinh được tài liệu. Markdown lấy ở `GET /jobs/{id}/result`.
