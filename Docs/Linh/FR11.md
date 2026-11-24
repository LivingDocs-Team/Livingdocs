# LD-339 — Kiểm thử RAG & Knowledge Retrieval

Kiểm thử luồng RAG của AI Service từ đầu đến cuối: dữ liệu phân tích + tài liệu ngữ cảnh → chỉ mục truy xuất (FR-AI-03) → prompt gửi AI → trích dẫn E/C/D → mục "Nguồn tham chiếu" trong tài liệu và `context_used` trong báo cáo (FR-AI-04).

- File test: `ai-service/tests/test_rag.py` (16 test, mỗi test là một test case RAG-xx).
- Chạy: `cd ai-service && python -m pytest tests/test_rag.py -q`
- AI giả (`Recorder`): ghi lại mọi prompt và trả JSON cố định, nên kiểm tra được chính xác ngữ cảnh nào tới AI và trích dẫn quay về ra sao. Không cần `ANTHROPIC_API_KEY`.
- Dữ liệu: 3 file của repository `shop` (`cart/service.py`, `cart/routes.py`, `pricing/tax.py`) và `README.md` có 3 mục (Shop, Cart, Deployment).

## Test case

| ID | Nội dung kiểm tra | Kết quả mong đợi | Kết quả |
|---|---|---|---|
| RAG-01 | Prompt của `routes.py` có mã liên quan và tài liệu, kèm vị trí | Có `C1: CartService.total (shop/cart/service.py:10-14)` và `D1: Cart (README.md:5-8)`; mục Deployment không vào prompt | Đạt (sau sửa lỗi 2) |
| RAG-02 | File không tự truy xuất chính mình | Không C nào có đường dẫn trùng file đang sinh | Đạt |
| RAG-03 | Giới hạn k và độ dài đoạn trích | Tối đa 4 C, 3 D; mỗi đoạn ≤ 600 ký tự; số thứ tự C1–C4, D1–D3 liên tục | Đạt |
| RAG-04 | Một file, không có tài liệu | Prompt không có mục "Related code" / "Existing documentation" | Đạt |
| RAG-05 | File lỗi (status ≠ ok) | Không được đưa vào chỉ mục | Đạt |
| RAG-06 | Trích dẫn C/D được hiển thị | Có mục "Nguồn tham chiếu" với **C1**, **D1** kèm vị trí; báo cáo có `context_used` tương ứng | Đạt |
| RAG-07 | Id trong prompt khớp catalog | Tập id `E/C/D` trong prompt = tập id của catalog dùng để kiểm trích dẫn | Đạt |
| RAG-08 | Ngữ cảnh không được trích dẫn | Không có mục "Nguồn tham chiếu", `context_used` rỗng | Đạt |
| RAG-09 | Trích dẫn ngữ cảnh tính vào grounding | grounding = 1,0 (E), 0,5 (chỉ C), 0,0 (không trích dẫn) | Đạt |
| RAG-10 | Tài liệu tiếng Việt khớp định danh tiếng Việt | Lớp `HoaDon.tinh_tien` lấy được mục "Hóa đơn" đầu tiên | Đạt |
| RAG-11 | Bỏ dấu chỉ dùng khi so khớp | Đoạn trích trong prompt giữ nguyên chữ có dấu | Đạt |
| RAG-12 | Tài liệu bị sao chép (2 file giống nhau) | Một đoạn giống hệt chỉ chiếm 1 chỗ trong 3 D | Đạt (sau sửa lỗi 1) |
| RAG-13 | Tính tất định | Hai job cùng đầu vào cho tài liệu giống hệt | Đạt |
| RAG-14 | `POST /retrieval/preview` khớp với job | Mọi C/D của preview có trong prompt của đúng file đó, cùng id | Đạt |
| RAG-15 | Thư mục nghiệp vụ dùng chung bởi 2/3 file | `cart` không bị bỏ khỏi truy vấn; `routes.py` lấy được mục Cart | Đạt (sau sửa lỗi 2) |
| RAG-16 | Tên repository là thư mục | Với phạm vi repository, `shop` bị bỏ; với phạm vi module thì không | Đạt (sau sửa lỗi 2) |

Toàn bộ test của `ai-service`: 258 đạt, 23 bỏ qua (test tích hợp cần API key hoặc dịch vụ ngoài).

## Lỗi tìm thấy và đã sửa

1. **Đoạn tài liệu trùng lặp chiếm nhiều chỗ** (RAG-12). Khi repository có cùng một nội dung ở hai file (ví dụ README được chép vào `docs/`), cả hai đoạn được đưa vào prompt, mất một trong 3 chỗ D. Sửa: `RetrievalIndex.search` bỏ đoạn có nội dung (đã chuẩn hoá khoảng trắng) giống một đoạn đã chọn.
2. **Luật bỏ từ chung của đường dẫn quá mạnh với repository nhỏ** (RAG-01, RAG-15). Luật của LD-337 bỏ từ có trong ≥ 60 % đường dẫn khi có ≥ 3 file. Với 3 file, `cart` có trong 2 đường dẫn (67 %) nên bị bỏ; `routes.py` mất mục "Cart" của README, trong khi mục "Deployment" vẫn được lấy. Sửa:
   - chỉ bỏ từ có trong ≥ 80 % đường dẫn và khi có ≥ 4 file;
   - với phạm vi repository, luôn bỏ tên repository nếu nó cũng là thư mục trong đường dẫn (trường hợp `shop/...` mà luật cũ nhắm tới).

   Đo lại bằng benchmark của LD-336/LD-337 (`python -m experiments.retrieval.benchmark --no-embedding`): kết quả production không đổi (code R@4 0,96, nDCG 0,96; tài liệu MRR 0,93, nDCG 0,75, nhiễu 1,00).

Trên code của LD-337 (trước khi sửa) RAG-12, RAG-15, RAG-16 không đạt; sau khi sửa cả 16 test đạt.

## Giới hạn còn lại

- Tài liệu tiếng Việt chỉ khớp khi định danh trong code là tiếng Việt không dấu (`HoaDon`, `tinh_tien`); code tiếng Anh vẫn khó lấy được tài liệu tiếng Việt (xem LD-336).
- Test dùng AI giả nên không đánh giá chất lượng câu chữ AI viết; phần đó thuộc kiểm thử tích hợp có API key (LD-390).
