# FR-AI-04 Bằng chứng xác thực và điểm độ tin cậy

| Mục | Nội dung |
|---|---|
| Story / task Jira | LD-340 Document Generation From Analysis |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service: `app/evidence.py`, `app/confidence.py`, `GET /jobs/{id}/report`; frontend hiển thị danh sách bằng chứng |
| Tác nhân | Người đọc/duyệt tài liệu, frontend trang Documentation |

## 1. Mô tả

Mỗi mô tả trong tài liệu đi kèm **bằng chứng** chỉ tới đúng vị trí code (file:dòng) hoặc đoạn tài liệu đã dùng, và một **điểm độ tin cậy** 0–1. Điểm chủ yếu dựa trên các tín hiệu kiểm chứng được (dữ liệu đầu vào, AI có trích đúng code của chính thực thể không), AI tự chấm chỉ chiếm một phần nhỏ. Người duyệt nhờ đó biết mô tả nào cần kiểm tra lại.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AI-04.1 | Mỗi file có một evidence catalog. Mỗi thực thể của file (theo thứ tự: lớp, các phương thức của lớp đó, …, hàm, endpoint) có mã `E1, E2, …` trỏ tới code của chính nó: `path`, `name` (khoá `Lớp`, `Lớp.phương_thức`, `hàm` hoặc `GET /path`), `line_start`, `line_end`, đoạn trích tối đa 300 ký tự. Catalog có thêm các mục C/D truy xuất được (FR-AI-03). |
| FR-AI-04.2 | Prompt liệt kê catalog dưới "Evidence catalog": "Own code (cite the item's own id):" rồi `- E1: Tên (path:dòng-dòng)`, sau đó các mục C và D. Vị trí in là `path:đầu-cuối`, `path:đầu` khi chỉ một dòng, hoặc `path` khi không có số dòng. |
| FR-AI-04.3 | AI phải ghi `evidence` (danh sách mã) và `confidence` (0–1) cho mỗi mục, `overview_evidence` cho phần tổng quan. Mã được chuẩn hoá chữ hoa, bỏ trùng; mã không có trong catalog bị bỏ và cảnh báo `ignored citations not in the evidence catalog: X9, D7.`. |
| FR-AI-04.4 | Điểm mỗi thực thể khi có mô tả của AI: `0,30 × chất lượng đầu vào + 0,30 × mức dẫn chứng + 0,20 × đã mô tả + 0,20 × AI tự chấm − 0,10 (nếu có mã trích không tồn tại)`, kẹp về [0, 1], làm tròn 2 chữ số. Mức dẫn chứng = 1 nếu trích mã E của chính thực thể, 0,5 nếu chỉ trích mã khác, 0 nếu không trích. Đã mô tả = 1 nếu có `summary` không rỗng. AI tự chấm thiếu hoặc sai kiểu → 0,5. |
| FR-AI-04.5 | Không có mô tả của AI (offline hoặc dự phòng): điểm = `0,60 × chất lượng đầu vào`. |
| FR-AI-04.6 | Chất lượng đầu vào (0–1) là trung bình các tín hiệu: **hàm/phương thức**: có `source`, có docstring, tỉ lệ có kiểu (số tham số có kiểu + 1 nếu có kiểu trả về) / (số tham số + 1); **lớp**: có docstring, tỉ lệ phương thức có `source` (0 khi không có phương thức); **endpoint**: có handler, có response, tỉ lệ tham số có kiểu (1 khi không có tham số). |
| FR-AI-04.7 | Mức: `high` khi ≥ 0,75, `medium` khi ≥ 0,50, còn lại `low`. Nhãn tiếng Việt: cao / trung bình / thấp. |
| FR-AI-04.8 | Điểm file = trung bình điểm các thực thể của file (thuộc các mục của mẫu, FR-AI-05). Điểm job = trung bình điểm **mọi thực thể** của mọi file. Không có thực thể → không có điểm. |
| FR-AI-04.9 | Mỗi thực thể lưu `factors`: `input_quality`, `ai_described`; khi có AI thêm `grounding`, `self_assessed`, `invalid_citations`. Bằng chứng của thực thể = mã E của nó trước, rồi các mã hợp lệ khác AI đã trích. |
| FR-AI-04.10 | Trong Markdown, dưới mỗi lớp/hàm/endpoint có dòng trích dẫn dạng: Độ tin cậy: **0.96 (cao)** · Bằng chứng: `shop/routes.py:5-7`, C1 `shop/cart_service.py:10-14`, D1 `README.md:5-8`. Điểm file nằm ở dòng thông tin của mục Tổng quan; điểm job ở trang tổng quan ("Độ tin cậy chung"). |
| FR-AI-04.11 | `GET /jobs/{id}/report` trả: `job_id`, `template_id`, `template_name`, `confidence`, `level`, `method` (mô tả cách tính bằng chữ), `files[]` gồm `path`, `status`, `confidence`, `level`, `entities[]` (`kind` = class/method/function/endpoint, `name`, `confidence`, `level`, `evidence[]` `{id, kind = source/code/doc, path, name, line_start, line_end, excerpt}`, `factors`) và `context_used[]` (các mục C/D được trích). File bị bỏ qua hoặc lỗi vẫn có mặt với `status` tương ứng. |
| FR-AI-04.12 | `confidence` cũng có trong `file_results[]` và job (`confidence`, `confidence_level`) của FR-AI-01. Frontend hiển thị danh sách bằng chứng dạng `Tên — path:đầu-cuối`. |

## 3. API

| Method | Endpoint | Yêu cầu |
|---|---|---|
| GET | `/jobs/{id}/report` (qua GitHub Integration: `/api/documentation/jobs/{id}/report`) | FR-AI-04.11 |

Ví dụ một thực thể trong báo cáo:

```json
{"kind": "function", "name": "get_cart_total", "confidence": 0.96, "level": "high",
 "evidence": [{"id": "E1", "kind": "source", "path": "shop/routes.py", "name": "get_cart_total",
               "line_start": 5, "line_end": 7, "excerpt": "async def get_cart_total(cart_id: int) -> float: ..."},
              {"id": "D1", "kind": "doc", "path": "README.md", "name": "Cart", "line_start": 5, "line_end": 8}],
 "factors": {"input_quality": 1.0, "grounding": 1.0, "ai_described": 1.0, "self_assessed": 0.8,
             "invalid_citations": 0.0}}
```

## 4. Luồng chính

1. Trước khi gọi AI, dựng catalog E + C + D cho file và đưa vào prompt.
2. AI trả mô tả kèm mã bằng chứng và tự chấm.
3. Hệ thống kiểm tra mã, tính điểm từng thực thể, điểm file, điểm job; ghi vào Markdown, job và báo cáo.

## 5. Luồng lỗi

| Trường hợp | Kết quả |
|---|---|
| AI trích mã không có trong catalog | Bỏ mã, cảnh báo, trừ 0,10 điểm thực thể đó |
| AI ghi `confidence` không phải số | Dùng 0,5 |
| Analyzer không gửi số dòng | Bằng chứng chỉ ghi `path` |
| Xem báo cáo khi job chưa xong | `409`; job không tồn tại `404` |

## 6. Quy tắc nghiệp vụ

- Không có AI thì điểm tối đa 0,60 (mức trung bình), vì tài liệu chỉ nhắc lại dữ liệu trích xuất.
- Số dòng nhận cả tên `line_start`/`line_end` và `lineno`/`end_lineno` (tên mà Code Analyzer đang gửi); đầu ra luôn dùng `line_start`/`line_end`.
- Báo cáo được lưu trong bộ nhớ cùng job.

## 7. Tiêu chí chấp nhận

- **AC-AI-04.1:** Hàm có source, docstring, đủ kiểu; AI mô tả, trích E của nó, tự chấm 0,8 → điểm `0,3 + 0,3 + 0,2 + 0,16 = 0,96`, mức `high`.
- **AC-AI-04.2:** Như trên nhưng có thêm 2 mã sai (`X9`, `D7`) → điểm `0,86`, `invalid_citations = 2`, cảnh báo nêu cả `X9` và `D7`.
- **AC-AI-04.3:** AI không trích mã nào → `grounding = 0`, điểm thấp hơn khi có trích.
- **AC-AI-04.4:** Offline, hàm có chất lượng đầu vào 1,0 → điểm `0,60`, mức `medium`.
- **AC-AI-04.5:** Analyzer gửi `lineno = 27`, `end_lineno = 30` → bằng chứng `line_start = 27`, `line_end = 30`, Markdown có `` `shop/cart_service.py:27-30` ``.

## 8. Kiểm thử

`ai-service/tests/test_evidence_confidence.py` (16 test: công thức điểm, mã sai, offline/dự phòng, báo cáo qua API, số dòng), `tests/integration/test_ai_service_integration.py` (số dòng từ analyzer thật, báo cáo đủ thực thể, điểm offline ≤ 0,60).
