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
| `context` | list `ContextDocument` | không | Tài liệu có sẵn làm ngữ cảnh (README, ghi chú thiết kế) |

**`ContextDocument`**: `path` (bắt buộc), `title`, `content` (văn bản Markdown, tối đa 200.000 ký tự).
Nội dung được chia đoạn theo tiêu đề; đoạn liên quan nhất tới từng file được đưa vào prompt
và có thể được AI trích dẫn làm bằng chứng (mã `D1`, `D2`…).

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

**`ClassInfo`**: `name` (bắt buộc), `bases` (list string), `docstring`, `methods` (list `Function`),
`line_start`, `line_end`.

**`Function`**: `name` (bắt buộc), `signature`, `parameters` (list `Parameter`), `return_type`,
`docstring`, `source` (đoạn code, tùy chọn; bị cắt còn 1.500 ký tự khi đưa vào prompt),
`line_start`, `line_end`.

**`Parameter`**: `name` (bắt buộc), `type`, `default`, `description`.

**`Endpoint`**: `http_method` (GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS), `path` (bắt buộc),
`handler`, `parameters`, `request_body`, `response`, `line_start`, `line_end`.

`line_start` / `line_end`: số dòng (bắt đầu từ 1) của thực thể trong file. Không bắt buộc, nhưng
thiếu thì bằng chứng chỉ trỏ được tới tên file thay vì `file.py:12-20`. ai-service cũng nhận tên
`lineno` / `end_lineno` mà bộ phân tích hiện đang gửi (LD-390).

## Lưu ý cho LD-328

- Gửi `source` của hàm và phương thức nếu có thể: AI mô tả chính xác hơn khi thấy code.
- File rỗng, file lỗi cú pháp hoặc ngôn ngữ chưa hỗ trợ: vẫn gửi kèm `status` và `error`
  thay vì bỏ khỏi danh sách, để tài liệu ghi rõ file nào không sinh được.
- `self` / `cls` không cần đưa vào `parameters`.
- Gửi `line_start` = `node.lineno` và `line_end` = `node.end_lineno` (Python `ast`) cho lớp, hàm,
  phương thức; với Java dùng `node.position.line` cho `line_start`.
- Truyền `repo_path` khi đọc file để `path` là đường dẫn tương đối (`app/x.py`), vì `path` xuất
  hiện trong tài liệu và trong bằng chứng.

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

Mỗi job và mỗi phần tử `file_results` có thêm `confidence` (0–1); job có `confidence_level`
(`high` ≥ 0,75, `medium` ≥ 0,5, `low`).

## Bằng chứng và độ tin cậy: `GET /jobs/{id}/report`

Trả về cho từng file và từng thực thể (lớp, phương thức, hàm, endpoint):

- `confidence`, `level` và `factors` (các thành phần tạo nên điểm);
- `evidence`: danh sách bằng chứng, mỗi mục gồm `id`, `kind` (`source` = code của chính thực thể,
  `code` = code liên quan ở file khác, `doc` = đoạn tài liệu có sẵn), `path`, `line_start`,
  `line_end`, `excerpt`;
- `context_used` của mỗi file: các đoạn code và tài liệu truy xuất được mà AI đã trích dẫn.

Cách tính điểm nằm trong trường `method` của báo cáo và trong `app/confidence.py`:

- Có mô tả của AI: 0,30 × chất lượng đầu vào (có source, docstring, kiểu dữ liệu) + 0,30 × mức
  dẫn chứng (trích code của chính thực thể = 1; chỉ trích nguồn khác = 0,5; không trích = 0)
  + 0,20 × có mô tả + 0,20 × điểm AI tự đánh giá; trừ 0,10 nếu trích mã không tồn tại.
- Không có AI (offline hoặc dự phòng): 0,60 × chất lượng đầu vào.
