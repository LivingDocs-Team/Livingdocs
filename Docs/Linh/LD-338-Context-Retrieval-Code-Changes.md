# LD-338 — Ngữ cảnh cho thay đổi code (Context Retrieval for Code Changes)

Khi một commit hoặc Pull Request đổi code, người viết tài liệu (hoặc AI) cần biết: đoạn code nào đã đổi, code nào khác liên quan tới nó, và tài liệu nào đang nói về nó. LD-338 gom đủ các thứ đó cho **từng thực thể bị đổi** qua API `POST /drift/context` của AI Service. Yêu cầu chi tiết: FR-AI-03.13–03.15 trong [FR3.md](FR3.md).

## Cách làm

Dùng lại các phần đã có, không thêm thư viện:

| Bước | Dùng lại | Kết quả |
|---|---|---|
| 1. Tìm thực thể bị đổi | Phân tích PR của drift (LD-146, `drift_changes.py`) | Danh sách thực thể: thêm, xoá, đổi tên, đổi chữ ký, đổi hành vi, kèm số dòng cũ/mới |
| 2. Cắt diff | Các hunk của `patch` | `X1`: chỉ những dòng diff nằm trong thực thể (tối đa 60 dòng) |
| 3. Tài liệu nhắc tên | Tìm tài liệu bị ảnh hưởng của drift (LD-148, `drift_affected.py`) | `D` với `relation = mentions`: các đoạn nhắc tên cũ, đường dẫn endpoint cũ, tham số đã xoá; tài liệu đã lưu có `document_id`, `version` |
| 4. Code liên quan | Chỉ mục TF-IDF của LD-335/337 (`retrieval.py`) trên các file ở commit head | `C` với `relation`: `handler`, `caller`, `callee`, `similar` |
| 5. Tài liệu liên quan khác | Cùng chỉ mục | `D` với `relation = related` (không trùng đoạn ở bước 3) |
| 6. Văn bản cho AI | — | `prompt`: mô tả thay đổi, diff, các mục C/D có mã để trích dẫn |

Truy vấn của mỗi thực thể gồm tên và chữ ký cũ/mới (tính gấp đôi), docstring, tham số thêm/bớt và các dòng `+`/`-` của diff. Quan hệ gọi hàm lấy từ `refs` của chỉ mục (tên mà mỗi đoạn code dùng): đoạn code dùng tên của thực thể là `caller`; tên mà code mới dùng (chữ ký mới, dòng `+`) là `callee`. Kết quả chỉ giống về chữ (`similar`) phải có điểm ≥ 0,30, tài liệu `related` phải ≥ 0,15, để không đưa nhiễu vào prompt.

## Đầu vào

Cùng body với `POST /drift/analyze`, thêm:

- `repository_files`: phân tích các file khác của repository ở commit head (định dạng của Code Analyzer). File thay đổi dùng `after` của chính nó; file bị xoá không được đưa vào chỉ mục.
- `k_code` (0–10, mặc định 4), `k_docs` (0–10, mặc định 3).
- `document_ids`: tài liệu đã lưu cần xét (`null` = tất cả, `[]` = không xét); `docs`: file Markdown của repository.

## Ví dụ

PR đổi `get_cart_total(cart_id, discount)` thành `get_cart_total(cart_id, currency)`, giờ gọi `convert(total, currency)`; repository có `checkout.py` gọi `get_cart_total`, `rates.py` có `convert`, `docs/pricing.md` có các mục Currencies, Discounts, Deployment. `prompt` của `get_cart_total` (không có tài liệu đã lưu):

```text
Changed code: function `get_cart_total` in shop/cart.py changed its signature.
Before: get_cart_total(cart_id: int, discount: float) -> float
After: get_cart_total(cart_id: int, currency: str) -> float
- removed parameter(s): discount
- added parameter(s): currency

X1: diff (shop/cart.py:10-15)
```diff
-def get_cart_total(cart_id: int, discount: float) -> float:
+def get_cart_total(cart_id: int, currency: str) -> float:
     cart = load(cart_id)
-    return sum(cart.items) - discount
+    total = sum(cart.items)
+    return convert(total, currency)
```

Related code at the head commit:
- C1 [caller]: GET /api/carts/{id} (shop/cart.py:9)
  GET /api/carts/{id} -> get_cart_total
- C2 [caller]: checkout (shop/checkout.py:3-6)
  checkout(cart_id)
- C3 [callee]: convert (shop/rates.py:1-4)
  convert(amount, currency)
  Convert an amount to a currency.
- C4 [similar]: count_cart_items (shop/cart.py:23-25)
  count_cart_items(cart_id)

Other related documentation:
- D1 [related]: Pricing > Discounts (docs/pricing.md:7-10)
  ## Discounts
  
  A discount is subtracted from the cart total.
- D2 [related]: Shop (README.md:1-5)
  # Shop
  
  Read a total with `GET /carts/:id`.
  Implementation: [cart](shop/cart.py), see `clear_cart()`.
  We add items to a cart.
- D3 [related]: Pricing > Currencies (docs/pricing.md:3-6)
  ## Currencies
  
  Amounts are converted to the currency of the customer.
```

Khi có tài liệu đã lưu sinh từ `shop/cart.py`, đoạn nói về `get_cart_total` trong đó đứng đầu với `D1 [mentions]`, vì đó là chỗ chắc chắn phải sửa. Endpoint đổi đường dẫn `GET /carts/{id}` → `GET /api/carts/{id}` nhận `C1 [handler]: get_cart_total` và đoạn README còn ghi `GET /carts/:id` (`mentions`). Hàm mới `apply_coupon` nhận phần tài liệu sinh từ `shop/cart.py` (`file_doc`): nơi cần thêm mô tả cho nó.

## Kiểm thử

File test: `ai-service/tests/test_change_context.py` (13 test). Chạy: `cd ai-service && python -m pytest tests/test_change_context.py -q`.

| ID | Nội dung kiểm tra | Kết quả mong đợi | Kết quả |
|---|---|---|---|
| CC-01 | Mỗi thực thể bị đổi có một ngữ cảnh; không lưu gì | Đủ các thay đổi (đổi chữ ký, xoá, thêm, đổi tên endpoint); chỉ mục 4 file, 2 tài liệu; số báo cáo drift không đổi | Đạt |
| CC-02 | Diff chỉ gồm dòng của thực thể | `get_cart_total`: dòng 10–15, 3 dòng thêm, 2 dòng xoá, không có dòng của `Cart.add` | Đạt |
| CC-03 | Quan hệ của code liên quan | `checkout` và route là `caller`, `convert` là `callee`, `write_log` không có, không trả lại chính nó; endpoint có `handler` đứng đầu | Đạt |
| CC-04 | Tài liệu đã lưu nhắc tên đứng đầu | `D1` là `mentions`, có `document_id`, `version = 1`, `matched` chứa `get_cart_total` | Đạt |
| CC-05 | Endpoint đổi tên | Đoạn README ghi đường dẫn cũ là `mentions` | Đạt |
| CC-06 | Thực thể mới thêm | Có `file_doc` trỏ tới tài liệu sinh từ file đó; prompt có mục tương ứng | Đạt |
| CC-07 | Tài liệu liên quan phải đủ gần | Có "Discounts", "Currencies"; không có "Deployment"; `_audit` không nhận tài liệu nào | Đạt |
| CC-08 | Giới hạn `k_code`, `k_docs` | 1 → tối đa 1 mục; 0 → rỗng; 11 → `422` | Đạt |
| CC-09 | Prompt trích đúng các mã | Mỗi C/D xuất hiện đúng một lần, số thứ tự liên tục, có khối diff `X1` | Đạt |
| CC-10 | Diff dài | Cắt còn 60 dòng, `truncated = true`, prompt ghi "(diff truncated)" | Đạt |
| CC-11 | Chỉ có `patch` (không có `before`/`after`) | Vẫn có diff và `caller` | Đạt |
| CC-12 | File bị xoá | Không vào chỉ mục, không xuất hiện trong code liên quan; thực thể của nó là `removed` | Đạt |
| CC-13 | Tính tất định; không có tài liệu | Hai lần gọi cho kết quả giống hệt; cảnh báo "No documentation was given" | Đạt |

Toàn bộ test của `ai-service`: 271 đạt, 23 bỏ qua (test tích hợp cần API key hoặc dịch vụ ngoài).

## Giới hạn

- Quan hệ gọi hàm dựa trên tên: hai hàm trùng tên ở hai file khác nhau đều được coi là `caller`.
- Chỉ trả ngữ cảnh, chưa tự viết lại tài liệu: bước sinh bản cập nhật bằng AI dùng `prompt` này (luồng cập nhật tài liệu LD-128).
- GitHub Integration Service chưa gọi `POST /drift/context`; khi tích hợp cần gửi thêm `repository_files` (phân tích các file khác ở commit head).
