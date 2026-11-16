# LD-355 — Kiểm thử và hoàn thiện AI Grounding Evidence

Kiểm thử phần bằng chứng xác thực (grounding evidence) của FR-AI-04: catalog mã E/C/D của mỗi file, cách đọc mã AI trích dẫn, điểm dẫn chứng (`grounding`) trong độ tin cậy, và bằng chứng hiển thị trong tài liệu/báo cáo.

- File test: `ai-service/tests/test_grounding_evidence.py` (12 test case, 21 test do GE-01 chạy 10 bộ dữ liệu).
- Chạy: `cd ai-service && python -m pytest tests/test_grounding_evidence.py -q`
- AI giả trả JSON cố định nên kiểm soát được chính xác mã nào được trích. Không cần `ANTHROPIC_API_KEY`.

## Test case

| ID | Nội dung kiểm tra | Kết quả mong đợi | Kết quả |
|---|---|---|---|
| GE-01 | Chuẩn hoá mã trích dẫn (10 bộ dữ liệu) | `"E1, C2"` → `E1, C2`; `[E1]`, `e2:` → `E1, E2`; `E01` → `E1`; bỏ trùng, bỏ rỗng; `"source code"`, `CartService`, `E2E` không phải mã → giữ nguyên để tính là mã sai | Đạt (sau sửa lỗi 1) |
| GE-02 | `overview_evidence` là chuỗi | Kết quả hợp lệ ngay lần gọi đầu, file ở trạng thái `generated` | Đạt (sau sửa lỗi 1) |
| GE-03 | Trích `[E1]` | `grounding = 1`, `invalid_citations = 0` | Đạt (sau sửa lỗi 1) |
| GE-04 | Mã không có trong catalog (`E9`) | Trừ đúng 0,10 điểm; cảnh báo `ignored citations ... E9` | Đạt |
| GE-05 | Trích mã E của file khác | Không tính là dẫn chứng; tính là mã sai | Đạt |
| GE-06 | Endpoint không có số dòng | Bằng chứng trỏ tới handler `shop/routes.py:5-7`, đoạn trích có source của handler | Đạt (sau sửa lỗi 2) |
| GE-07 | Handler là phương thức (`CartController.total`, Java) | Bằng chứng lấy dòng 12–18 và chữ ký của phương thức | Đạt (sau sửa lỗi 2) |
| GE-08 | Endpoint có số dòng / handler không có trong file | Giữ số dòng của analyzer; handler lạ → chỉ ghi `path`, không lỗi | Đạt |
| GE-09 | Overload (`Calc.add` 2 lần) | Mỗi overload có mã riêng (E2, E3); trích E3 vẫn được `grounding = 1`; bằng chứng hiển thị cả hai | Đạt (sau sửa lỗi 3) |
| GE-10 | Trích D1 trong phần tổng quan | D1 có trong `context_used` và mục "Nguồn tham chiếu" của từng file | Đạt |
| GE-11 | Mọi mục của catalog trỏ tới vị trí thật | Có `path`; mã E thuộc đúng file; dòng đầu ≤ dòng cuối; đoạn trích 1–300 ký tự | Đạt |
| GE-12 | Chế độ offline | Không có `grounding`, không có nguồn tham chiếu; vẫn hiển thị E1 làm bằng chứng | Đạt |

Toàn bộ test của `ai-service`: 237 đạt, 23 bỏ qua (test tích hợp cần API key hoặc dịch vụ ngoài). Trên code của `main` trước khi sửa: 10/21 test không đạt.

## Lỗi tìm thấy và đã sửa

1. **Mã trích dẫn không chuẩn bị tính là sai** (`app/doc_schema.py`). Trước đây chỉ nhận danh sách mã sạch: `"E1, C2"` thành một mã `"E1, C2"` không tồn tại, `[E1]` cũng vậy, nên thực thể mất điểm dẫn chứng và bị trừ 0,10 dù AI trích đúng. Tệ hơn, `overview_evidence` là chuỗi làm cả câu trả lời sai định dạng và phải gọi lại AI. Sửa: hàm `citation_ids()` tìm mọi mã `E/C/D + số` trong từng phần tử, dùng cho cả `evidence` và `overview_evidence`.
2. **Endpoint không có vị trí** (`app/evidence.py`). Nhiều analyzer không gửi số dòng cho route (chỉ gửi cho hàm), nên bằng chứng của endpoint chỉ là tên file. Sửa: lấy số dòng và source/chữ ký của handler (hàm, hoặc phương thức `Lớp.tên`) trong cùng file.
3. **Overload ghi đè nhau** (`app/evidence.py`, `app/confidence.py`). Hai phương thức cùng tên có cùng khoá `Calc.add`; catalog chỉ nhớ mã của overload cuối, nên AI trích mã của overload đầu chỉ được 0,5 điểm dẫn chứng. Sửa: catalog lưu mọi mã E của một khoá (`own_ids`), trích mã nào trong số đó cũng được 1.

## Giới hạn còn lại

- Khoảng mã (`D1-D3`) chỉ lấy hai đầu D1, D3, không mở rộng thành D2.
- Mô tả của AI cho các overload vẫn gộp chung theo tên (`Calc.add`), như trước.
- Test dùng AI giả; độ chính xác trích dẫn của AI thật được kiểm ở kiểm thử tích hợp (LD-390).
