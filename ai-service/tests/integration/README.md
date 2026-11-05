# Kiểm thử tích hợp AI Service (LD-390)

Kiểm tra ai-service khi nhận **kết quả thật** của service phân tích (LD-328), qua đúng các API mà
pipeline dùng: `POST /generate` → `GET /jobs/{id}` → `/result` → `/report`.

```
github-integration ──files+content──▶ analyzer /api/v1/analyze-repo ──{scope,target,files}──▶ ai-service /generate
```

## Dữ liệu kiểm thử

- `fixtures/shop/`: repository nhỏ gồm 2 file Python (lớp, phương thức, endpoint FastAPI), 1 file
  Java (Spring controller), 1 file lỗi cú pháp, 1 file rỗng, 1 file `.js` (chưa hỗ trợ).
- `fixtures/analyzer_output.json`: kết quả analyzer cho repository trên. Khi analyzer đổi định dạng,
  chạy lại từ thư mục gốc repo: `python ai-service/scripts/capture_analyzer_output.py`.
- `fixtures/README_shop.md`: tài liệu có sẵn, gửi trong `context`.
- `fixtures/quality/`: file dùng cho kiểm tra chất lượng đầu ra: route Flask/FastAPI nhiều kiểu,
  lớp pydantic, lớp kế thừa `models.Model`, file có BOM, Spring controller có overload, Javadoc,
  interface, enum và một `record` Java 16.
- `PromptDrivenModel` (`conftest.py`): model giả, trả lời theo evidence catalog trong prompt; có thể
  giả lập timeout API hoặc trả về văn bản không phải JSON.

## Các nhóm test

| File | Chạy khi | Nội dung |
|---|---|---|
| `test_ai_service_integration.py` | luôn (CI job `ai-service-test`) | 19 test, chạy trong tiến trình, không dùng mạng |
| `test_live_pipeline.py` `-m live` | có `ANALYZER_URL`, `AI_SERVICE_URL` (CI job `ai-service-integration`) | Gọi 2 service thật qua HTTP |
| `test_live_pipeline.py` `-m llm` | `RUN_LLM_TESTS=1` và `ANTHROPIC_API_KEY` | Gọi Claude API thật, chạy tay |
| `test_output_quality_live.py` `-m live` | như `test_live_pipeline.py` | Chất lượng đầu ra: so kết quả analyzer và tài liệu với file nguồn (`fixtures/quality/`). Các lỗi của analyzer được đánh dấu `xfail` (xem `QUALITY.md`) |

## Test case

| # | Trường hợp | Kết quả mong đợi |
|---|---|---|
| 1 | Gửi nguyên kết quả analyzer vào `/generate` | 202, job `completed`, `target`, `files_total`, `progress` đúng |
| 2 | File `invalid` / `empty` / `unsupported` | `skipped`, lý do của analyzer giữ nguyên trong `message` và `warnings` |
| 3 | Mọi lớp, phương thức, hàm, endpoint của analyzer | Đều có trong Markdown |
| 4 | Analyzer gửi `lineno` / `end_lineno` | Bằng chứng trỏ đúng `file:dòng đầu-dòng cuối` |
| 5 | `/report` | Khớp job, đủ thực thể, điểm trong 0–1 |
| 6 | Không có API key | Điểm tối đa 0,60 |
| 7 | Có AI + tài liệu `context` | `generated`, độ tin cậy `high`, prompt có code liên quan và tài liệu, file bị bỏ qua không gọi AI |
| 8 | AI timeout ở 1 file, trả rác ở 1 file | Hai file đó `fallback`, file còn lại `generated`, job vẫn `completed` |
| 9 | `output_language: en` | Prompt và Markdown tiếng Anh |
| 10 | Template tự tạo qua API | Đúng thứ tự mục; xoá template thì `/generate` trả 404 |
| 11 | Không file nào sinh được | Job `failed`, `/result` và `/report` trả 409 |
| 12 | `scope: file` | Chỉ trả tài liệu của file đó, không có trang tổng quan |
| 13 | `files` rỗng, `scope` sai, ngôn ngữ sai, trùng `path` | 422 |
| 14 | Job không tồn tại | 404 ở `/jobs/{id}`, `/result`, `/report` |
| 15 | Nhiều job | Tách biệt, `/jobs` sắp mới nhất trước |
| 16 | `/health` | `generator: offline` khi không có key |
| L1 | 2 service thật đang chạy | Cả hai trả lời |
| L2 | Body giống github-integration → analyzer → ai-service | Job `completed`, giữ tên repo, giữ số dòng |
| L3 | Claude thật | JSON hợp lệ, không trích dẫn sai, ≥ 80% thực thể có dẫn chứng |
| Q1 | Lớp, hàm Python và số dòng | Khớp đúng với file nguồn (so bằng `ast`) |
| Q2 | Phương thức Java và số dòng | Số dòng trỏ đúng dòng khai báo |
| Q3 | Mọi thực thể của analyzer | Có trong Markdown |
| Q4 | File bị bỏ qua | Luôn có lý do, không còn `JavaSyntaxError: ` rỗng |
| Q5 | Bằng chứng | Mỗi thực thể một mã riêng, dòng nằm trong file và chứa đúng tên thực thể (kể cả overload) |
| Q6 | Docstring có `Args:`/`Returns:` | Điền vào cột mô tả tham số và giá trị trả về khi không có AI |
| A1–A12 | Lỗi của analyzer (`xfail`) | Xem `QUALITY.md` |

Đo chất lượng trên mã nguồn thật của repo (cần 2 service đang chạy):

```bash
ANALYZER_URL=http://localhost:8000 AI_SERVICE_URL=http://localhost:8001 \
  python ai-service/scripts/quality_report.py app ai-service services backend tests
```
