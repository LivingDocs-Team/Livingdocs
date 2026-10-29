# FR-AI-02 Sinh tài liệu từ kết quả phân tích code

| Mục | Nội dung |
|---|---|
| Story / task Jira | LD-340 Document Generation From Analysis |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service: `app/generator.py`, `app/prompts.py`, `app/doc_schema.py`, `app/renderer.py` |
| Tác nhân | Job sinh tài liệu (FR-AI-01), Claude API (Anthropic) |

## 1. Mô tả

Với mỗi file đã phân tích, hệ thống nhờ AI viết **mô tả** cho các lớp, phương thức, hàm và endpoint, rồi tự dựng tài liệu Markdown theo một bố cục cố định. AI không viết Markdown và không quyết định cấu trúc: AI chỉ trả về JSON mô tả, còn tên, chữ ký, kiểu dữ liệu và thứ tự mục luôn lấy từ kết quả phân tích và mẫu tài liệu. Khi AI lỗi hoặc không có API key, tài liệu vẫn được dựng từ dữ liệu phân tích.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AI-02.1 | Prompt cho mỗi file gồm, theo thứ tự: ngôn ngữ viết (`Vietnamese (tiếng Việt)` hoặc `English`); phong cách từ mẫu (`instructions`); phạm vi mẫu (mục nào cần viết, mục nào để trống, FR-AI-05); khuôn JSON mẫu; kết quả phân tích của file; evidence catalog (FR-AI-04). |
| FR-AI-02.2 | Kết quả phân tích đưa vào prompt dạng JSON: bỏ trường rỗng, bỏ `status`/`error`; `source` của mỗi hàm/phương thức cắt còn 1.500 ký tự (thêm `... (truncated)`); nếu cả JSON vẫn dài hơn 40.000 ký tự thì bỏ hết `source`, giữ cấu trúc. |
| FR-AI-02.3 | System prompt quy định: chỉ trả 1 object JSON, không Markdown/code fence; dùng đúng tên trong phân tích; không bịa thực thể; mô tả dựa trên chữ ký, kiểu, docstring, source, không đoán được thì nói ngắn gọn; tóm tắt 1–2 câu, tham số và giá trị trả về 1 câu; viết bằng ngôn ngữ yêu cầu; trích mã bằng chứng (FR-AI-04); dùng code/tài liệu truy xuất chỉ làm ngữ cảnh; tự đánh giá `confidence` 0–1. |
| FR-AI-02.4 | Khuôn JSON AI phải trả: `{"overview", "overview_evidence": [], "classes": [{"name","summary","evidence","confidence","methods": [{"name","summary","parameters": [{"name","description"}],"returns","evidence","confidence"}]}], "functions": [...như methods], "endpoints": [{"method","path","summary","evidence","confidence"}]}`. |
| FR-AI-02.5 | Đọc câu trả lời: bỏ code fence ```` ```json ```` nếu có, lấy đoạn từ `{` đầu tiên tới `}` cuối cùng, parse JSON, kiểm tra theo khuôn. Lỗi thì báo rõ: `empty response`, `no JSON object found`, `invalid JSON: ... (line n)`, `top-level JSON value must be an object`, `schema mismatch at '<vị trí>': ...`. `evidence` nhận cả chuỗi lẻ; `confidence` sai kiểu thành rỗng, ngoài 0–1 thì kẹp về 0–1. |
| FR-AI-02.6 | Gọi AI tối đa `LLM_MAX_ATTEMPTS` lần (mặc định 3). Lỗi gọi API (mạng, timeout, rate limit) → ghi cảnh báo `AI call failed (attempt n)`, chờ `1 s × 2^(n−1)` rồi thử lại (không chờ sau lần cuối). |
| FR-AI-02.7 | AI trả sai định dạng → ghi cảnh báo `invalid AI output (attempt n)`, gửi lại hội thoại kèm câu trả lời sai và prompt sửa: "Your previous response could not be used: <lỗi>. Reply again with ONLY the JSON object in the required shape, nothing else." |
| FR-AI-02.8 | Hết số lần thử → file có trạng thái `fallback`, cảnh báo "AI did not return a valid result after N attempt(s); documentation was built from analysis data only.", tài liệu dựng từ dữ liệu phân tích. |
| FR-AI-02.9 | Không có `ANTHROPIC_API_KEY` → không gọi AI, mọi file `offline`. File không có thực thể nào → không gọi AI, vẫn `generated`. |
| FR-AI-02.10 | AI bỏ sót thực thể có trong phân tích (thuộc mục của mẫu) → cảnh báo `AI gave no description for <tên>`. AI mô tả thực thể không có trong phân tích → bỏ qua khi dựng và cảnh báo `ignored entities not in the analysis`. |
| FR-AI-02.11 | Dựng Markdown mỗi file: `# <path>`, rồi lần lượt các mục của mẫu: **Tổng quan** (overview của AI, hoặc "Không tìm thấy lớp, hàm hoặc endpoint nào trong file này." khi file rỗng; dòng nghiêng: ngôn ngữ, module, số lớp / hàm (gồm cả phương thức) / endpoint, độ tin cậy file); **Các lớp** (tiêu đề cấp 3 "Lớp `Tên` (kế thừa A, B)", mô tả, rồi từng phương thức ở tiêu đề cấp 4); **Các hàm** (tiêu đề cấp 3); **API Endpoints** (tiêu đề cấp 3 `GET /path`, mô tả, hàm xử lý, bảng tham số, request body, response). Mục không có nội dung thì không in. Cuối file: "Nguồn tham chiếu" (FR-AI-04). |
| FR-AI-02.12 | Mỗi hàm/phương thức: tên, khối chữ ký (chữ ký của analyzer, không có thì `tên(tham số)`), mô tả, bảng tham số 4 cột Tên, Kiểu, Mặc định, Mô tả (ký tự gạch đứng được escape, xuống dòng thành dấu cách; không có tham số → "Không có tham số."), dòng "Giá trị trả về: `kiểu` — mô tả" ("Không xác định" khi không có kiểu), dòng độ tin cậy và bằng chứng. |
| FR-AI-02.13 | Mô tả được chọn theo thứ tự: mô tả của AI → docstring của analyzer → câu dự phòng thận trọng. Hàm: "Mô tả suy luận: tên hàm `x` gợi ý chức năng <hành động>; cần kiểm tra mã nguồn để xác nhận hành vi cụ thể." (hành động suy từ động từ đầu tiên nhận ra trong tên: get/fetch → truy xuất dữ liệu, create/add → tạo/thêm dữ liệu, delete/remove → xoá dữ liệu, validate/check → kiểm tra…). Lớp: "Chưa có mô tả xác nhận cho lớp `X`." Endpoint có handler: "Endpoint này được ánh xạ tới handler `h`. Mục đích nghiệp vụ chưa được xác nhận từ dữ liệu phân tích." |
| FR-AI-02.14 | Hỗ trợ 2 ngôn ngữ đầu ra `vi` và `en` cho toàn bộ nhãn (tiêu đề mục, bảng, trạng thái, mức độ tin cậy). |

## 3. Cấu hình

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `ANTHROPIC_API_KEY` | (trống) | Có thì chạy chế độ AI; trống thì offline |
| `LLM_MODEL` | `claude-sonnet-5-5` | Model Claude |
| `LLM_MAX_TOKENS` | 4096 | Giới hạn token mỗi câu trả lời |
| `LLM_TIMEOUT` | 60 | Timeout mỗi lần gọi (giây); SDK không tự thử lại (`max_retries=0`), việc thử lại do FR-AI-02.6 |
| `LLM_MAX_ATTEMPTS` | 3 | Số lần thử tối đa mỗi file |

## 4. Luồng chính

1. Job (FR-AI-01) gọi sinh tài liệu cho một file, kèm ngữ cảnh truy xuất (FR-AI-03).
2. Tạo evidence catalog và prompt; gọi Claude; parse và kiểm tra JSON.
3. Chấm điểm từng thực thể (FR-AI-04), dựng Markdown theo mẫu (FR-AI-05), trả về Markdown, trạng thái, cảnh báo và báo cáo file.

## 5. Luồng lỗi

| Trường hợp | Trạng thái file | Cảnh báo |
|---|---|---|
| Lỗi mạng / timeout / rate limit ở mọi lần thử | `fallback` | `AI call failed (attempt n)` + thông báo dự phòng |
| AI trả không phải JSON / sai khuôn ở mọi lần thử | `fallback` | `invalid AI output (attempt n): <lỗi>` + thông báo dự phòng |
| Lần đầu lỗi, lần sau đúng | `generated` | Cảnh báo của lần lỗi vẫn được giữ |
| Không có API key | `offline` | Không có |

## 6. Quy tắc nghiệp vụ

- Tài liệu luôn có cùng bố cục cho mọi file, bất kể AI trả gì; tên và kiểu không bao giờ lấy từ AI.
- Bảng tham số dùng tên tham số của analyzer; mô tả tham số lấy từ AI nếu có, không thì từ `description` của analyzer.
- `self` / `cls` không được analyzer gửi nên không có trong bảng.

## 7. Tiêu chí chấp nhận

- **AC-AI-02.1:** AI trả JSON hợp lệ → file `generated`, Markdown có mô tả của AI, tên hàm đúng như analyzer.
- **AC-AI-02.2:** AI trả JSON bọc trong ```` ```json ```` → vẫn đọc được.
- **AC-AI-02.3:** AI trả văn bản thường ở lần 1, JSON đúng ở lần 2 → `generated`, prompt lần 2 có câu "Your previous response could not be used".
- **AC-AI-02.4:** AI timeout ở mọi lần → `fallback`, tài liệu vẫn có tên hàm và docstring của analyzer.
- **AC-AI-02.5:** AI mô tả một hàm không có trong phân tích → hàm đó không xuất hiện trong Markdown, có cảnh báo `ignored entities`.
- **AC-AI-02.6:** `output_language = en` → prompt yêu cầu English, Markdown có "## Overview".

## 8. Kiểm thử

`ai-service/tests/test_generator.py` (prompt, parse, thử lại, dự phòng, bố cục), `tests/integration/test_ai_service_integration.py` (model giả theo prompt: AI đúng, timeout, trả rác), `test_live_pipeline.py -m llm` (Claude thật, chạy tay).
