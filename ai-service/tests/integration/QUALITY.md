# Kiểm tra Analyzer, AI Service và chất lượng dữ liệu đầu ra

Ngày kiểm tra: 02/11/2026 · Nhánh: `QA-Analyzer-AI-Output-Quality` · Người thực hiện: Linh

## 1. Cách kiểm tra

1. Chạy Code Analyzer (LD-328) và AI Service (LD-340) như trong CI.
2. Đưa **chính mã nguồn của repo** qua analyzer, rồi qua AI Service. Mã nguồn gồm thư mục `app/`,
   `ai-service/`, `services/`, `backend/` và `tests/`: 42 file Python và 96 file Java.
   Lệnh chạy: `ai-service/scripts/quality_report.py`.
3. So kết quả với file nguồn:
   - Python: so với `ast`.
   - Java: so với số khai báo, annotation `@...Mapping` và khối Javadoc.
   - Tài liệu sinh ra: kiểm tra đủ thực thể, bằng chứng trỏ đúng dòng, mô tả tham số, lý do bỏ qua file.
4. Thử thêm các trường hợp biên (`fixtures/quality/`). Mỗi lỗi tìm được có một test trong
   `test_output_quality_live.py`.

AI Service chạy **offline** (không có `ANTHROPIC_API_KEY`), nên lần này chưa kiểm tra chất lượng
mô tả do Claude viết. Muốn kiểm tra phần đó thì chạy `RUN_LLM_TESTS=1 ANTHROPIC_API_KEY=... pytest -m llm`.

## 2. Kết quả trên mã nguồn thật

| Chỉ số | Python | Java |
|---|---|---|
| File | 42 | 96 |
| Phân tích được (`ok`) | 41 (1 file rỗng) | **61 (35 file `invalid`, 36%)** |
| Lớp tìm thấy / có trong nguồn | 59 / 59 | 57 / 73 (thiếu interface, enum, record) |
| Hàm, phương thức tìm thấy / có trong nguồn | 327 / 327 | 345 (không tính constructor) |
| Endpoint tìm thấy / route trong nguồn | 14 / 14 | **0 / 30** |
| Docstring / Javadoc lấy được | 63 | **0 / 96 khối Javadoc** |
| Lớp có số dòng | **0 / 59** | **0 / 57** |
| `module` được điền | **0** | **0** |

Tài liệu sinh ra có 802 thực thể, tất cả đều có trong Markdown. Có 130 bằng chứng (của lớp và
endpoint) chỉ trỏ được tới tên file vì analyzer không gửi số dòng. 105 lớp hiện câu "Chưa có mô tả"
khi chạy offline, phần lớn là lớp dữ liệu (pydantic, DTO) mà analyzer không gửi các trường.

## 3. Lỗi của Code Analyzer (LD-328): đã sửa (04/11/2026, nhánh `QA-Fix-Code-Analyzer`)

Mỗi lỗi có test trong `tests/test_analysis.py` (unit, chạy ở job `ai-service-integration`) và
`test_output_quality_live.py` (2 service thật). Các test này trước là `xfail`, nay pass bình thường.

| Mã | Mức độ | Lỗi | Cách sửa |
|---|---|---|---|
| A1 | **Cao** | `javalang` chỉ hiểu Java 8: `record`, text block `"""`... báo `invalid`, thông báo lỗi rỗng | Phân tích Java bằng `tree-sitter-java` (`app/java_extractor.py`), đọc được cú pháp Java 17. Lỗi cú pháp ghi rõ vị trí: `JavaSyntaxError line 3:12: unexpected '...'` |
| A2 | **Cao** | Không lấy endpoint Spring | Đọc `@GetMapping/@PostMapping/@PutMapping/@DeleteMapping/@PatchMapping/@RequestMapping`, ghép path của `@RequestMapping` ở lớp, kế thừa `method=` của lớp; tham số `@PathVariable/@RequestParam/...`, `@RequestBody` → `request_body`, kiểu trả về → `response` |
| A3 | Trung bình | Route Flask/FastAPI: `route()` không có `methods`, `path=` dạng keyword, prefix của router | Mặc định GET; đọc `path=`/`rule=`; ghép `APIRouter(prefix=...)` và `Blueprint(url_prefix=...)`; thêm `response` = kiểu trả về |
| A4 | Trung bình | Thiếu interface, enum, record, constructor | Xuất đủ, có trường `kind` (`class`/`interface`/`enum`/`record`); lớp lồng nhau tên `Ngoai.Trong` |
| A5 | Trung bình | Không đọc Javadoc | Javadoc ngay trước khai báo → `docstring` (giữ `@param`, `@return` để ai-service đọc) |
| A6 | Trung bình | Lớp, endpoint không có số dòng | `lineno`/`end_lineno` cho lớp (Python, Java) và endpoint |
| A7 | Thấp | Lớp cha dạng `models.Model`, `typing.Generic[T]` bị bỏ | `ast.unparse(base)`; Java gồm cả `extends` và `implements` |
| A8 | Trung bình | Không lấy trường của lớp | `fields` (tên, kiểu, mặc định, dòng) cho pydantic/dataclass/hằng lớp, field Java, thành phần record, hằng enum. ai-service hiển thị bảng "Thuộc tính" và tính vào độ tin cậy |
| A9 | Thấp | `module` luôn `null` | Python suy ra từ `path`; Java lấy từ `package` |
| A10 | Thấp | File có BOM UTF-8 báo `invalid` | Bỏ ký tự BOM (`\ufeff`) trước khi phân tích |
| A11 | Thấp | `"Python"` (chữ hoa) → `unsupported` | So sánh không phân biệt hoa thường |
| A12 | Thấp | Trùng `path` → ai-service trả 422 cho cả request | Giữ bản đầu, ghi vào `warnings` của kết quả |

Ngoài ra: file rỗng có `error`, file chưa hỗ trợ ghi rõ đuôi file (`Language 'unknown' is not supported (file extension '.js').`).

Kết quả trên cùng mã nguồn sau khi sửa (`quality_report.py`, 43 file Python, 96 file Java):

| Chỉ số | Trước | Sau |
|---|---|---|
| File Java phân tích được | 61 / 96 | **96 / 96** |
| Endpoint Java | 0 | **43** (gồm 16 endpoint của BFF proxy: 4 path × 4 method) |
| Lớp Java (gồm interface, enum, record) | 57 | 118 |
| Docstring/Javadoc của phương thức Java | 0 | 51 |
| Lớp có số dòng | 0 | 179 / 179 |
| Bằng chứng trỏ được tới dòng | 672 / 802 | **1062 / 1062** |
| File có `module` | 0 | 138 / 138 |
| Thực thể độ tin cậy trung bình (offline) | 44 | 204 |

## 4. Lỗi của AI Service đã sửa trong nhánh này

| Mã | Lỗi | Sửa |
|---|---|---|
| F1 | Phương thức overload (Java `get(Long)` và `get(String)`) dùng chung một mã bằng chứng và một mô tả, nên bằng chứng của `get(Long)` trỏ sang dòng của `get(String)` | `app/normalize.py`: tên trùng trong một file được đổi thành `get(Long)` / `get(String)`, còn trùng nữa thì đánh `#2`. AI nhận đúng tên này nên mô tả cũng khớp |
| F2 | "Module: -" ở mọi file | Suy ra `module` từ đường dẫn khi analyzer không gửi (`app/services/cart.py` → `app.services.cart`, Java lấy theo package) |
| F3 | Chạy offline thì dán nguyên docstring (cả phần `Args:`, `Returns:`) vào mô tả, cột mô tả tham số để trống, giá trị trả về ghi "Không xác định" | `app/docstrings.py` đọc docstring kiểu Google, NumPy, reST và Javadoc: lấy đoạn tóm tắt, điền mô tả tham số và giá trị trả về. Khi có AI, mô tả của AI vẫn được ưu tiên |
| F4 | Endpoint chạy offline chỉ có câu chung chung, Response "Không xác định" | Lấy docstring và kiểu trả về của hàm xử lý (handler) |
| F5 | File bị bỏ qua hiện lý do rỗng `JavaSyntaxError: ` (34 file) | Ghi `JavaSyntaxError (analyzer status 'invalid', no details)` |

Kết quả trên mã nguồn thật trước và sau khi sửa (cùng một kết quả analyzer):

| Chỉ số | Trước | Sau |
|---|---|---|
| File bị bỏ qua có lý do rỗng | 34 | 0 |
| Module được hiển thị | 0 / 102 | 102 / 102 |
| Overload dùng chung một bằng chứng (fixture `OrderApi.java`) | 1 cặp | 0 |

Repo hiện ít dùng docstring có mục `Args:`, nên F3 chỉ điền thêm được vài dòng trên code thật.
Fixture có overload và docstring đầy đủ (`fixtures/quality/`) thể hiện rõ phần sửa. Ba test
end-to-end (Q4, Q5, Q6) **fail trên `main`** và pass trên nhánh này.

## 5. Chạy lại

```bash
# ở thư mục gốc repo: unit test của analyzer
python -m pytest -q -o addopts="" tests/test_analysis.py
# trong ai-service/
python -m pytest -q                       # unit test, gồm tests/test_output_quality.py
ANALYZER_URL=http://localhost:8000 AI_SERVICE_URL=http://localhost:8001 \
  python -m pytest -m live -v tests/integration
```



