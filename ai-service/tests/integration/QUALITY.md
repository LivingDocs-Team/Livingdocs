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

## 3. Lỗi của Code Analyzer (LD-328, chuyển Lâm)

Mỗi lỗi có một test `xfail` cùng mã trong `test_output_quality_live.py`. Khi sửa xong, test chuyển
sang XPASS; lúc đó bỏ dấu `xfail`.

| Mã | Mức độ | Lỗi | Ảnh hưởng | Gợi ý sửa |
|---|---|---|---|---|
| A1 | **Cao** | `javalang` chỉ hiểu Java 8: `record`, text block `"""`... báo `invalid`, thông báo lỗi rỗng (`JavaSyntaxError: `) | 35/96 file Java của repo (DTO, client GitHub, BFF controller) không có tài liệu | Dùng `tree-sitter-java` (có trên PyPI). Trước mắt ghi vị trí lỗi: `f"JavaSyntaxError line {e.at.position.line}: {e.description}"` |
| A2 | **Cao** | Không lấy endpoint Spring (`@GetMapping`, `@PostMapping`, `@RequestMapping` ở lớp) | 0/30 API Java có trong tài liệu | Đọc `method.annotations`; ghép path của `@RequestMapping` ở lớp với path ở phương thức |
| A3 | Trung bình | Python: `@app.route("/x")` không có `methods` thì bỏ qua (Flask mặc định GET); `@app.get(path="/x")` bỏ qua; prefix của `APIRouter(prefix=...)` không được ghép | Thiếu hoặc sai đường dẫn API | Mặc định `["GET"]`; đọc keyword `path`; tìm `APIRouter(prefix=...)` gán cho biến router |
| A4 | Trung bình | Java: interface, enum và constructor không được xuất | Thiếu repository, enum trạng thái, constructor injection | `tree.filter(InterfaceDeclaration / EnumDeclaration)`, `node.constructors` |
| A5 | Trung bình | Không đọc Javadoc | Java không có mô tả, độ tin cậy thấp | `node.documentation` (javalang) hoặc comment ngay trước khai báo |
| A6 | Trung bình | Lớp và endpoint không có `lineno`/`end_lineno` | 130 bằng chứng chỉ trỏ tới file | `ClassInfo` thêm `lineno=node.lineno`, `end_lineno=node.end_lineno` |
| A7 | Thấp | Lớp cha dạng thuộc tính (`models.Model`, `typing.Generic[T]`) bị bỏ | Mất quan hệ kế thừa | `ast.unparse(base)` thay cho chỉ lấy `ast.Name` |
| A8 | Trung bình | Không lấy trường của lớp (pydantic, dataclass, thành phần record) | Lớp dữ liệu không có nội dung để mô tả, độ tin cậy 0 | Thêm `fields` (tên, kiểu, mặc định) từ `ast.AnnAssign`. Cần thống nhất lại `CONTRACT.md` |
| A9 | Thấp | `module` luôn `null` | Tài liệu hiện "Module: -" (ai-service đã tự suy ra, xem F2) | Suy ra từ `path` |
| A10 | Thấp | File có BOM UTF-8 (lưu bằng Notepad trên Windows) báo `invalid` | Mất tài liệu cả file | `content.lstrip("﻿")` trước khi parse |
| A11 | Thấp | `language` phân biệt hoa thường: `"Python"` → `unsupported` | Phía gọi gửi sai chữ hoa thì mất cả file | `.strip().lower()` trước khi so |
| A12 | Thấp | Trùng `path` vẫn trả 2 phần tử | ai-service trả 422 cho **cả** request | Bỏ trùng hoặc báo lỗi rõ ở analyzer |

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
# trong ai-service/
python -m pytest -q                       # unit test, gồm tests/test_output_quality.py
ANALYZER_URL=http://localhost:8000 AI_SERVICE_URL=http://localhost:8001 \
  python -m pytest -m live -v tests/integration
```
