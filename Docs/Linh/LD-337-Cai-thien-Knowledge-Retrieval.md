# LD-337 Cải thiện Knowledge Retrieval

| Mục | Nội dung |
|---|---|
| Task Jira | LD-337 Cải thiện Knowledge Retrieval |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service: `app/retrieval.py` (FR-AI-03); đo bằng `experiments/retrieval/benchmark.py` |
| Đầu vào | Kết luận của LD-336 (`LD-336-Embedding-vs-TFIDF.md`) |

## 1. Vấn đề (từ LD-336)

- Đoạn mở đầu README (`# Shop` + một câu) đứng đầu kết quả tài liệu ở 11/14 file, vì từ `shop` có trong mọi đường dẫn file.
- Đoạn chỉ có tiêu đề (`# Pricing`) lọt vào kết quả.
- Số nhiều không khớp số ít (*products* / `product`, *passwords* / `password`, *codes* / `code`).
- Tài liệu tiếng Việt có dấu không khớp với định danh không dấu của nhóm (`HoaDon`, `luot_gui`).
- Xếp hạng chỉ dựa vào từ chung, chưa dùng thông tin "file này gọi code nào".

Embedding (GloVe) không giải quyết được các điểm trên mà còn làm kết quả code kém đi, nên LD-337 giữ TF-IDF và sửa đúng các nguyên nhân.

## 2. Thay đổi

| # | Cải thiện | Cách làm |
|---|---|---|
| 1 | Bỏ dấu tiếng Việt khi tách từ | `Hóa đơn`, `HóaĐơn`, `HoaDon`, `hoa_don` đều thành `hoa don`; từ dừng tiếng Việt cũng so sánh không dấu. Tách chữ hoa/thường đúng cả với chữ có dấu. |
| 2 | Gộp số nhiều tiếng Anh | `products` → `product`, `categories` → `category`; không đổi từ kết thúc `ss`, `us`, `is` (`class`, `status`, `basis`). |
| 3 | Bỏ đoạn chỉ có tiêu đề | Đoạn không có nội dung ngoài dòng tiêu đề không vào chỉ mục; tiêu đề vẫn nằm trong đường dẫn tiêu đề của các đoạn con. |
| 4 | Bỏ từ chung của đường dẫn khỏi truy vấn | Từ có trong ít nhất 60 % đường dẫn file (khi có từ 3 file trở lên) không dùng để truy vấn: tên repository (`shop`), `src main java com <công ty>`… |
| 5 | Ưu tiên code được gọi thật sự | Tên lớp/hàm xuất hiện trong `source`, chữ ký, kiểu tham số/trả về của file đang viết: hàm hoặc lớp được gọi +0,25; phương thức `Lớp.m` +0,25 khi file dùng cả `Lớp` và `m`, +0,10 khi chỉ dùng `Lớp`. |
| 6 | Ưu tiên code gọi tới file | Mục code có `source`/kiểu dữ liệu nhắc tới lớp hoặc hàm của file đang viết: +0,20 (ví dụ route gọi `CartService()` khi đang viết `cart/service.py`). |
| 7 | Ưu tiên đoạn tài liệu nhắc tên code của file | Đoạn có từ dạng code (`CartService`, `cart_id`) trùng tên lớp/hàm của file: +0,15. Từ thường (`cart`) không tính. |

Điểm cuối = cosine TF-IDF + các điểm cộng, tối đa 1,0; ngưỡng 0,05 và số lượng (4 code, 3 tài liệu) giữ nguyên.

## 3. Kết quả trên bộ dữ liệu của LD-336

| | Code R@4 | Code nDCG@4 | Code noise | Tài liệu R@3 | Tài liệu MRR | Tài liệu nDCG@3 | Tài liệu noise | ms/file |
|---|---|---|---|---|---|---|---|---|
| Trước (LD-336, TF-IDF) | 0,91 | 0,93 | 1,50 | 0,61 | 0,49 | 0,43 | 1,86 | 0,25 |
| **Sau (LD-337)** | **0,96** | **0,96** | **1,36** | **0,70** | **0,93** | **0,75** | **1,00** | 0,40 |

Đóng góp của từng nhóm thay đổi (cùng chỉ mục mới, `results_ld337.md`):

| | Code nDCG@4 | Tài liệu MRR | Tài liệu nDCG@3 | Tài liệu noise |
|---|---|---|---|---|
| Chỉ thay đổi 1–3 (tách từ, bỏ đoạn tiêu đề) | 0,92 | 0,61 | 0,58 | 1,64 |
| + bỏ từ chung của đường dẫn (4) | 0,92 | 0,93 | 0,75 | 1,00 |
| + điểm cộng gọi/được gọi (5–7) | 0,96 | 0,93 | 0,75 | 1,00 |

- Đoạn tài liệu đúng giờ thường đứng **đầu** (MRR tài liệu 0,49 → 0,93), số đoạn không liên quan giảm gần một nửa.
- Code được gọi thật sự lên đầu danh sách (nDCG code 0,93 → 0,96).
- Chậm hơn khoảng 0,15 ms mỗi file, không đáng kể.
- Còn hạn chế: đoạn tiếng Việt chỉ tìm được khi có từ trùng (không dấu) với code; tài liệu dùng từ hoàn toàn khác (*basket* / `cart`) vẫn có thể bị bỏ lỡ. Muốn xử lý cần embedding đa ngôn ngữ (xem LD-336, mục 6).

## 4. Kiểm thử

- `ai-service/tests/test_retrieval_improvements.py`: bỏ dấu, gộp số nhiều, từ dạng code trong văn bản, từ chung của đường dẫn, bỏ đoạn tiêu đề, đoạn mở đầu chung không còn đứng đầu, ba loại điểm cộng, điểm tối đa 1,0, và **chặn hồi quy** trên benchmark (code R@4 ≥ 0,95, nDCG ≥ 0,95; tài liệu MRR ≥ 0,90, nDCG ≥ 0,70, noise ≤ 1,0; phải tốt hơn TF-IDF thuần).
- Các test cũ của truy xuất (`test_evidence_confidence.py`, `test_indexing.py`) vẫn qua.
