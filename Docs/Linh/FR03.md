# FR-AI-03 Truy xuất mã liên quan và tài liệu có sẵn làm ngữ cảnh

| Mục | Nội dung |
|---|---|
| Story / task Jira | LD-340 Document Generation From Analysis; LD-335 Hoàn thiện Document & Code Indexing; LD-337 Cải thiện Knowledge Retrieval |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service: `app/retrieval.py`, `POST /retrieval/preview` (`main.py`) |
| Tác nhân | Job sinh tài liệu (FR-AI-01), AI (nhận ngữ cảnh trong prompt) |

## 1. Mô tả

Khi viết tài liệu cho một file, AI cần biết file đó dùng lớp/hàm nào ở file khác và tài liệu có sẵn (README, ghi chú thiết kế) nói gì về nó. Hệ thống tự tìm các đoạn code liên quan trong các file khác của cùng yêu cầu và các đoạn tài liệu liên quan nhất, đưa vào prompt làm ngữ cảnh có thể trích dẫn (mã `C1`, `C2`… cho code, `D1`, `D2`… cho tài liệu). Không cần dịch vụ ngoài.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AI-03.1 | Yêu cầu sinh tài liệu có thể kèm `context`: danh sách tài liệu `{path (bắt buộc), title, content (Markdown, tối đa 200.000 ký tự)}`. |
| FR-AI-03.2 | Chỉ mục được dựng **một lần mỗi job** từ các file có `status = ok`: mọi lớp (tên, loại, lớp cha, docstring, **trường** `tên: kiểu`, tên các phương thức), mọi phương thức (`Lớp.phương_thức`), mọi hàm, mọi **endpoint** (`GET /path` kèm handler, tham số, request body, response — LD-335), và các đoạn của tài liệu `context`. Mỗi mục giữ đường dẫn, tên, loại (`class`/`method`/`function`/`endpoint`/`section`), số dòng và đoạn trích. |
| FR-AI-03.3 | Tách tài liệu thành đoạn tại mỗi tiêu đề Markdown `#`…`######`; dòng bắt đầu bằng `#` **nằm trong khối code** ```` ``` ```` hoặc `~~~` không phải tiêu đề (LD-335). Ngoài ra cắt khi đoạn dài hơn 1.200 ký tự và gặp dòng trống (ngoài khối code), hoặc dài hơn 2.400 ký tự. Mỗi đoạn mang tên tiêu đề gần nhất (không có thì `title` hoặc `path`), **đường dẫn tiêu đề** `section` (ví dụ `Shop > Cart > VAT`, cũng được đưa vào chỉ mục) và số dòng bắt đầu/kết thúc trong tài liệu. Đoạn chỉ có dòng tiêu đề không được đưa vào chỉ mục (LD-337). |
| FR-AI-03.4 | Tách từ theo kiểu định danh: `getCartTotal` → `get cart total`, `cart_id` → `cart id` (đúng cả với chữ có dấu); chữ thường; **bỏ dấu tiếng Việt** (`Hóa đơn`, `HoaDon` → `hoa don`, LD-337); **gộp số nhiều tiếng Anh** (`products` → `product`, `categories` → `category`; giữ nguyên từ kết thúc `ss`/`us`/`is`, LD-337); bỏ từ dưới 2 ký tự, số thuần, và từ dừng tiếng Anh/tiếng Việt/từ khoá lập trình (the, and, def, self, return, class, str, int, của, các, được…). |
| FR-AI-03.5 | Xếp hạng bằng độ tương đồng cosine TF-IDF: idf = ln((n + 1) / (df + 0,5)) + 1; trọng số từ = (1 + ln(tần suất)) × idf. Câu truy vấn của một file gồm đường dẫn, module, tên/lớp cha/docstring của lớp, nội dung các phương thức và hàm (tên, chữ ký, tham số, kiểu, docstring, source), đường dẫn/handler/request/response của endpoint; **bỏ các từ có trong ≥ 80 % đường dẫn file** khi có từ 4 file (LD-337, chỉnh ở LD-339) và, với phạm vi repository, tên repository khi nó cũng là thư mục (LD-339). Điểm cộng (LD-337, điểm cuối tối đa 1,0): +0,25 cho lớp/hàm mà file gọi (tên có trong source, chữ ký, kiểu); phương thức `Lớp.m` +0,25 khi file dùng cả `Lớp` và `m`, +0,10 khi chỉ dùng `Lớp`; +0,20 cho code nhắc tới lớp/hàm của file; +0,15 cho đoạn tài liệu có từ dạng code (`CartService`, `cart_id`) trùng tên lớp/hàm của file. |
| FR-AI-03.6 | Với mỗi file lấy tối đa **4 đoạn code** từ các file **khác** và tối đa **3 đoạn tài liệu**, chỉ giữ đoạn có điểm ≥ 0,05; cùng điểm thì xếp theo đường dẫn rồi tên. Đánh mã theo thứ tự điểm: `C1…C4`, `D1…D3` (đánh lại riêng cho từng file). |
| FR-AI-03.7 | Hai đoạn trích giống hệt nhau (tài liệu bị sao chép) chỉ chiếm một chỗ trong k kết quả (LD-339). Đoạn trích tối đa 600 ký tự: code = chữ ký (có tiền tố `Lớp.` với phương thức) + docstring; lớp = `class Tên(Cha)` + docstring + `fields: ...` + `methods: ...`; endpoint = `GET /path -> handler` + tham số, request, response; tài liệu = nội dung đoạn. |
| FR-AI-03.8 | Đưa vào prompt dưới mục "Related code from other files" và "Existing documentation": `- C1: Tên (path:dòng-dòng)` và đoạn trích thụt lề. Không có đoạn nào đạt ngưỡng thì không có mục đó. |
| FR-AI-03.9 | Các đoạn C/D mà AI thực sự trích dẫn được liệt kê ở cuối tài liệu file trong mục "Nguồn tham chiếu" (mỗi dòng: **C1** Tên — `path:dòng-dòng`; C trước D, theo số) và trong `context_used` của báo cáo (FR-AI-04). |
| FR-AI-03.10 | (LD-335) Mỗi kết quả truy xuất mang `score` (độ tương đồng, 0–1, 4 chữ số) và là bản sao: chỉ mục không bị đổi giữa các file. |
| FR-AI-03.11 | (LD-335) Thống kê chỉ mục: số file đã phân tích, số tài liệu, số mục theo loại, số từ vựng. |
| FR-AI-03.12 | (LD-335) `POST /retrieval/preview` nhận cùng body với `POST /generate` (kiểm tra hợp lệ giống hệt, `422` khi sai), trả thống kê chỉ mục và, cho từng file `ok`, danh sách C/D mà prompt của file đó sẽ nhận (`ref`, `kind`, `entity`, `path`, `name`, `section`, `line_start`, `line_end`, `score`, `excerpt`). Không tạo job, không gọi AI. Dùng để kiểm tra và giải thích kết quả truy xuất. |
| FR-AI-03.13 | (LD-338) Ngữ cảnh cho thay đổi code: `POST /drift/context` nhận cùng body với `POST /drift/analyze` (PR, file thay đổi có `patch`/`before`/`after`, `docs`, `document_ids`) và thêm `repository_files` (phân tích các file khác của repository ở commit head), `k_code` (0–10, mặc định 4), `k_docs` (0–10, mặc định 3). Với **mỗi thực thể bị thay đổi** (thêm, xoá, đổi tên, đổi chữ ký, đổi hành vi) trả: `X1` = các dòng diff nằm trong thực thể (tối đa 60 dòng, `truncated` khi bị cắt); `C1..` = code liên quan ở commit head; `D1..` = tài liệu; và `prompt` là đoạn văn bản sẵn để gửi AI, trích đúng các mã đó. Không lưu gì, không gọi AI. |
| FR-AI-03.14 | (LD-338) Code liên quan được tìm bằng chỉ mục TF-IDF của FR-AI-03 trên các file ở commit head (file đã xoá không được đưa vào), truy vấn gồm tên cũ/mới, chữ ký cũ/mới, docstring, tham số thêm/bớt và các dòng diff. Mỗi mục có `relation`: `handler` (hàm phục vụ endpoint bị đổi), `caller` (code dùng thực thể bị đổi), `callee` (code mà phiên bản mới dùng), `similar` (chỉ giống về chữ, phải có điểm ≥ 0,30). Không bao giờ trả lại chính thực thể bị đổi. Thứ tự: handler, caller, callee, similar. |
| FR-AI-03.15 | (LD-338) Tài liệu: trước hết là các đoạn **có nhắc tên** thực thể (tìm bằng cách tìm tài liệu bị ảnh hưởng của drift, LD-148: tên cũ, đường dẫn endpoint cũ, tham số đã xoá), `relation = mentions`, điểm 1,0, có `matched` (tên tìm thấy), `document_id`, `version` với tài liệu đã lưu (tối đa 10 đoạn); với thực thể mới thêm, đoạn đầu của phần tài liệu sinh từ chính file đó (`file_doc`); sau đó tối đa `k_docs` đoạn liên quan khác (`related`, điểm ≥ 0,15), không trùng đoạn đã có. |

## 3. API

Ngữ cảnh dùng trường `context` của `POST /generate` (FR-AI-01). Xem trước kết quả truy xuất: `POST /retrieval/preview` (cùng body, FR-AI-03.12). Ngữ cảnh cho thay đổi code của một Pull Request: `POST /drift/context` (FR-AI-03.13–03.15).

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
- **AC-AI-03.5 (LD-335):** `cart_service.py` không gọi route nào nhưng endpoint `POST /carts/{cart_id}/discount` ở `routes.py` dùng `apply_discount` → C của `cart_service.py` có endpoint đó.
- **AC-AI-03.7 (LD-337):** Mọi file nằm dưới `shop/`, README có đoạn mở đầu "Online shop backend" → đoạn này không còn đứng đầu kết quả tài liệu của các file (chỉ số đo trong `Docs/Linh/LD-337-Cai-thien-Knowledge-Retrieval.md`).
- **AC-AI-03.8 (LD-338):** PR đổi `get_cart_total(cart_id, discount)` thành `get_cart_total(cart_id, currency)` và gọi `convert(total, currency)`; `checkout.py` gọi `get_cart_total` → ngữ cảnh của `get_cart_total` có `checkout` (`caller`), `convert` (`callee`), đoạn tài liệu đã lưu nhắc `get_cart_total` là `D1` (`mentions`), và các đoạn "Discounts", "Currencies" của `docs/pricing.md` (`related`), không có đoạn "Deployment".
- **AC-AI-03.6 (LD-335):** Tài liệu có khối ```` ```bash ```` chứa dòng `# install the service` → không tạo đoạn mới tên "install the service"; khối code nằm trong đoạn "Cart" với số dòng đúng.

## 8. Kiểm thử

`ai-service/tests/test_evidence_confidence.py` (tách từ, tách đoạn và số dòng, truy xuất code và tài liệu, không có nhiễu khi không có ngữ cảnh), `tests/integration/test_ai_service_integration.py` (prompt của `routes.py` có code liên quan và README), `ai-service/tests/test_indexing.py` (LD-335: endpoint và trường lớp được đưa vào chỉ mục, khối code, đường dẫn tiêu đề, thống kê chỉ mục, điểm và tính tất định, `POST /retrieval/preview`), `ai-service/tests/test_retrieval_improvements.py` (LD-337, gồm chặn hồi quy trên benchmark), `ai-service/tests/test_retrieval_benchmark.py` (LD-336), `ai-service/tests/test_change_context.py` (LD-338, 13 test CC-01..CC-13).
