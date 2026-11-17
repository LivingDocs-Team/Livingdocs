# FR-AI-01 Tạo và theo dõi job sinh tài liệu

| Mục | Nội dung |
|---|---|
| Story Jira | LD-90 Implement Documentation Generation |
| Task đã làm | LD-91 – LD-95; mở rộng trong LD-340 và LD-96 |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service (cổng 8001): `main.py`, `app/jobs.py`, `app/models.py` |
| Tác nhân | GitHub Integration Service (gọi thay người dùng), người dùng xem kết quả qua trang Documentation |

## 1. Mô tả

Hệ thống nhận kết quả phân tích code của một file, một module hoặc cả repository, tạo một **job** chạy nền để sinh tài liệu, và cho phép theo dõi trạng thái, tiến độ, cảnh báo cho đến khi lấy được tài liệu Markdown. Một file lỗi không làm hỏng cả job.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AI-01.1 | Nhận yêu cầu sinh tài liệu với `scope` là `file`, `module` hoặc `repository`, `target` (tên file, module hoặc repo, không rỗng) và danh sách `files` (ít nhất 1) theo định dạng của Code Analyzer. |
| FR-AI-01.2 | Tuỳ chọn: `template_id` (mặc định `default`, xem FR-AI-05), `output_language` `vi` hoặc `en` (mặc định `vi`, không phân biệt hoa thường), `context` là tài liệu có sẵn (xem FR-AI-03). |
| FR-AI-01.3 | Từ chối ngay (422) khi: thiếu trường bắt buộc, `files` rỗng, `scope` hoặc `output_language` sai, hai file trùng `path`, số dòng `line_start`/`line_end` nhỏ hơn 1, `http_method` của endpoint không thuộc GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS. Template không tồn tại → 404. |
| FR-AI-01.4 | Hợp lệ thì trả về ngay `202` kèm job ở trạng thái `pending`; việc sinh tài liệu chạy nền (FastAPI `BackgroundTasks`). |
| FR-AI-01.5 | Job có: `id` (uuid hex), `scope`, `target`, `template_id`, `template_name`, `template_sections`, `status` (`pending` → `running` → `completed` hoặc `failed`), `progress` (0–1), `message`, `files_total`, `files_done`, `file_results`, `warnings`, `confidence`, `confidence_level`, `result`, `error`, `created_at`, `updated_at` (UTC). |
| FR-AI-01.6 | Sau mỗi file, cập nhật `files_done`, `progress = files_done / files_total × 0,95` (làm tròn 3 chữ số), `file_results`, `warnings`, và `message = "Documenting <path>"`. Hoàn thành thì `progress = 1.0`. |
| FR-AI-01.7 | Mỗi file có một kết quả `{path, status, message, confidence}` với `status`: `generated` (AI viết), `offline` (không có API key), `fallback` (AI lỗi, dựng từ dữ liệu phân tích), `skipped` (analyzer báo `empty`/`invalid`/`unsupported`), `failed` (lỗi bất ngờ riêng file đó). |
| FR-AI-01.8 | File có `status` khác `ok` từ analyzer thì bỏ qua, ghi lý do (`error` của analyzer, hoặc `analyzer status '<status>'`) vào `message` và `warnings` (`<path>: skipped (<lý do>).`). |
| FR-AI-01.9 | Lỗi bất ngờ ở một file chỉ làm file đó `failed` (cảnh báo `<path>: generation failed: <lỗi>`); các file khác vẫn tiếp tục. |
| FR-AI-01.10 | Job `failed` (kèm `error = "No documentation could be generated for any file"`) chỉ khi không file nào sinh được tài liệu. Còn lại là `completed`, `message` = `Completed` hoặc `Completed with N warning(s)`. |
| FR-AI-01.11 | Kết quả Markdown: `scope = file`, đúng 1 file và không file nào bị bỏ qua → chỉ tài liệu của file đó. Các trường hợp khác → trang tổng quan rồi tài liệu từng file, ngăn bằng `\n\n---\n\n`. |
| FR-AI-01.12 | Trang tổng quan gồm: `# <target>`, "Tài liệu cho N file.", tên mẫu tài liệu, độ tin cậy chung, "Danh sách file" (mỗi dòng: `` `path` — AI/offline/dự phòng (AI lỗi) · độ tin cậy x``), "File không sinh được tài liệu" (đường dẫn: lý do). Có bản tiếng Anh tương ứng khi `output_language = en`. |
| FR-AI-01.13 | Liệt kê job (mới nhất trước), xem một job, lấy Markdown, lấy báo cáo bằng chứng (FR-AI-04). |
| FR-AI-01.14 | `/health` trả `{"status": "ok", "generator": "ai"}` hoặc `"generator": "offline"`. |

## 3. API

| Method | Endpoint | Kết quả | Yêu cầu |
|---|---|---|---|
| GET | `/health` | `{"status","generator"}` | FR-AI-01.14 |
| POST | `/generate` | `202` + Job | FR-AI-01.1 – 01.4 |
| GET | `/jobs` | Danh sách Job, mới nhất trước | FR-AI-01.13 |
| GET | `/jobs/{id}` | Job | FR-AI-01.5 – 01.10 |
| GET | `/jobs/{id}/result` | Markdown, `text/markdown` | FR-AI-01.11 – 01.12 |
| GET | `/jobs/{id}/report` | JobReport (FR-AI-04) | FR-AI-01.13 |

Ví dụ body `/generate` (rút gọn):

```json
{"scope": "repository", "target": "acme/shop", "template_id": "default", "output_language": "vi",
 "files": [{"path": "shop/routes.py", "language": "python", "status": "ok",
            "functions": [{"name": "get_cart_total", "signature": "def get_cart_total(cart_id: int) -> float",
                           "parameters": [{"name": "cart_id", "type": "int"}], "return_type": "float",
                           "lineno": 10, "end_lineno": 13}],
            "endpoints": [{"http_method": "GET", "path": "/carts/{cart_id}/total", "handler": "get_cart_total"}]},
           {"path": "shop/broken.py", "status": "invalid", "error": "SyntaxError line 1: invalid syntax"}]}
```

## 4. Luồng chính

1. GitHub Integration gửi kết quả phân tích tới `POST /generate`; nhận `202` và `id` của job.
2. Job chuyển `running`, lấy mẫu tài liệu, dựng chỉ mục truy xuất (FR-AI-03) một lần cho cả job.
3. Lần lượt từng file: bỏ qua file lỗi, các file còn lại được sinh tài liệu (FR-AI-02) và chấm điểm (FR-AI-04); tiến độ cập nhật sau mỗi file.
4. Ghép Markdown, lưu báo cáo, job `completed`. Bên gọi hỏi `GET /jobs/{id}` (frontend hỏi mỗi 750 ms, tối đa 120 s) rồi lấy `/result` và `/report`.

## 5. Luồng lỗi

| Trường hợp | HTTP | Kết quả |
|---|---|---|
| Body sai định dạng (FR-AI-01.3) | 422 | `{"detail": [...]}`, không tạo job |
| `template_id` không tồn tại | 404 | `Template '<id>' not found` |
| Job không tồn tại (`/jobs/{id}`, `/result`, `/report`) | 404 | `Job not found` |
| Lấy `/result` hoặc `/report` khi job chưa `completed` | 409 | `Job is <status>` |
| Không file nào sinh được tài liệu | 200 khi xem job | Job `failed`, `/result` trả 409 |

## 6. Quy tắc nghiệp vụ

- Job và báo cáo chỉ lưu trong bộ nhớ (`JobStore`, khoá `threading.Lock`); khởi động lại service thì mất, phải sinh lại.
- Thứ tự file trong kết quả giữ đúng thứ tự trong `files` của yêu cầu.
- Bên gọi (GitHub Integration) tự kiểm soát người dùng nào được xem job nào; AI Service không có tài khoản người dùng.

## 7. Tiêu chí chấp nhận

- **AC-AI-01.1:** Gửi kết quả analyzer của 6 file (3 ok, 1 invalid, 1 empty, 1 unsupported) thì nhận `202`; job `completed`, `files_done = 6`, `progress = 1.0`, 3 file `offline`/`generated`, 3 file `skipped` kèm lý do của analyzer.
- **AC-AI-01.2:** Chỉ gửi file lỗi thì job `failed`, `/result` và `/report` trả `409`.
- **AC-AI-01.3:** `files` rỗng, `scope = galaxy`, `output_language = fr` hoặc hai file trùng `path` → `422`.
- **AC-AI-01.4:** `scope = file` với 1 file hợp lệ → Markdown bắt đầu bằng `# <path>` và không có "Danh sách file".
- **AC-AI-01.5:** Job không tồn tại → `404` ở cả `/jobs/{id}`, `/result`, `/report`.

## 8. Kiểm thử

`ai-service/tests/test_api.py`, `ai-service/tests/integration/test_ai_service_integration.py` (luồng job với kết quả thật của analyzer), `test_live_pipeline.py -m live` (2 service thật, job CI `ai-service-integration`).
