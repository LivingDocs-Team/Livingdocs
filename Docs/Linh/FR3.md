# FR-AI-03 Truy xuất mã liên quan và tài liệu có sẵn làm ngữ cảnh

| Mục | Nội dung |
|---|---|
| Story / task Jira | LD-340 Document Generation From Analysis |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service: `app/retrieval.py` |
| Tác nhân | Job sinh tài liệu (FR-AI-01), AI (nhận ngữ cảnh trong prompt) |

## 1. Mô tả

Khi viết tài liệu cho một file, AI cần biết file đó dùng lớp/hàm nào ở file khác và tài liệu có sẵn (README, ghi chú thiết kế) nói gì về nó. Hệ thống tự tìm các đoạn code liên quan trong các file khác của cùng yêu cầu và các đoạn tài liệu liên quan nhất, đưa vào prompt làm ngữ cảnh có thể trích dẫn (mã `C1`, `C2`… cho code, `D1`, `D2`… cho tài liệu). Không cần dịch vụ ngoài.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AI-03.1 | Yêu cầu sinh tài liệu có thể kèm `context`: danh sách tài liệu `{path (bắt buộc), title, content (Markdown, tối đa 200.000 ký tự)}`. |
| FR-AI-03.2 | Chỉ mục được dựng **một lần mỗi job** từ: mọi lớp (tên, lớp cha, docstring, tên các phương thức), mọi phương thức (`Lớp.phương_thức`), mọi hàm của các file có `status = ok`, và các đoạn của tài liệu `context`. Mỗi mục giữ đường dẫn, tên, số dòng và đoạn trích. |
| FR-AI-03.3 | Tách tài liệu thành đoạn tại mỗi tiêu đề `#`; ngoài ra cắt khi đoạn dài hơn 1.200 ký tự và gặp dòng trống, hoặc dài hơn 2.400 ký tự. Mỗi đoạn mang tên tiêu đề gần nhất (không có thì `title` hoặc `path`) và số dòng bắt đầu/kết thúc trong tài liệu. |
| FR-AI-03.4 | Tách từ theo kiểu định danh: `getCartTotal` → `get cart total`, `cart_id` → `cart id`; chữ thường; giữ chữ có dấu tiếng Việt; bỏ từ dưới 2 ký tự, số thuần, và từ dừng tiếng Anh/tiếng Việt/từ khoá lập trình (the, and, def, self, return, class, str, int, của, các, được…). |
| FR-AI-03.5 | Xếp hạng bằng độ tương đồng cosine TF-IDF: idf = ln((n + 1) / (df + 0,5)) + 1; trọng số từ = (1 + ln(tần suất)) × idf. Câu truy vấn của một file gồm đường dẫn, module, tên/lớp cha/docstring của lớp, nội dung các phương thức và hàm (tên, chữ ký, tham số, kiểu, docstring, source), đường dẫn/handler/request/response của endpoint. |
| FR-AI-03.6 | Với mỗi file lấy tối đa **4 đoạn code** từ các file **khác** và tối đa **3 đoạn tài liệu**, chỉ giữ đoạn có điểm ≥ 0,05; cùng điểm thì xếp theo đường dẫn rồi tên. Đánh mã theo thứ tự điểm: `C1…C4`, `D1…D3` (đánh lại riêng cho từng file). |
| FR-AI-03.7 | Đoạn trích tối đa 600 ký tự: code = chữ ký (có tiền tố `Lớp.` với phương thức) + docstring; lớp = `class Tên(Cha)` + docstring + `methods: ...`; tài liệu = nội dung đoạn. |
| FR-AI-03.8 | Đưa vào prompt dưới mục "Related code from other files" và "Existing documentation": `- C1: Tên (path:dòng-dòng)` và đoạn trích thụt lề. Không có đoạn nào đạt ngưỡng thì không có mục đó. |
| FR-AI-03.9 | Các đoạn C/D mà AI thực sự trích dẫn được liệt kê ở cuối tài liệu file trong mục "Nguồn tham chiếu" (mỗi dòng: **C1** Tên — `path:dòng-dòng`; C trước D, theo số) và trong `context_used` của báo cáo (FR-AI-04). |

## 3. API

Không có endpoint riêng. Dùng trường `context` của `POST /generate` (FR-AI-01).

```json
{"context": [{"path": "README.md", "title": "Shop",
              "content": "# Shop\n\n## Cart\n\nThe cart total includes VAT and is computed by CartService."}]}
```

## 4. Luồng chính

1. Job dựng chỉ mục từ tất cả file và tài liệu `context`.
2. Trước khi viết từng file, hệ thống tạo truy vấn từ file đó và lấy code liên quan ở file khác cùng các đoạn tài liệu phù hợp.
3. Các đoạn này vào evidence catalog (FR-AI-04) và prompt; AI dùng để giải thích mục đích, quan hệ giữa các thành phần.

## 5. Luồng lỗi

| Trường hợp | Kết quả |
|---|---|
| Không có `context` và chỉ có 1 file | Không có ngữ cảnh, prompt chỉ có code của chính file |
| Tài liệu `context` dài hơn 200.000 ký tự | `422` khi gửi yêu cầu |
| AI trích mã C/D không tồn tại | Bỏ mã đó, cảnh báo và trừ điểm (FR-AI-04) |

## 6. Quy tắc nghiệp vụ

- Ngữ cảnh chỉ để giải thích: AI không được mô tả thực thể nằm trong ngữ cảnh mà không có trong phân tích của file (FR-AI-02.10).
- Code của chính file đang viết không bao giờ được truy xuất làm C (nó đã là E, FR-AI-04).
- Kết quả truy xuất cố định với cùng đầu vào (không ngẫu nhiên), nên test được.

## 7. Tiêu chí chấp nhận

- **AC-AI-03.1:** `routes.py` gọi `CartService().total(...)` ở `cart_service.py` → prompt của `routes.py` có `C1` là `CartService` hoặc phương thức của nó, từ `cart_service.py`.
- **AC-AI-03.2:** README có mục "Cart" (nói về VAT) và mục "Deployment" (docker) → `D1` của `routes.py` là đoạn "Cart", không có đoạn "Deployment".
- **AC-AI-03.3:** Chỉ 1 file, không `context` → không có mục ngữ cảnh trong prompt.
- **AC-AI-03.4:** `tokenize("getCartTotal cart_id")` = `["get", "cart", "total", "cart", "id"]`.

## 8. Kiểm thử

`ai-service/tests/test_evidence_confidence.py` (tách từ, tách đoạn và số dòng, truy xuất code và tài liệu, không có nhiễu khi không có ngữ cảnh), `tests/integration/test_ai_service_integration.py` (prompt của `routes.py` có code liên quan và README).
