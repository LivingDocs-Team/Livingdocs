# LD-336 Thử nghiệm Embedding Retrieval và so sánh với TF-IDF

| Mục | Nội dung |
|---|---|
| Task Jira | LD-336 Thử nghiệm Embedding Retrieval và so sánh với TF-IDF |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Mã thử nghiệm | `ai-service/experiments/retrieval/` (`dataset.py`, `benchmark.py`, `results_ld336.md`) |
| Liên quan | FR-AI-03 (truy xuất ngữ cảnh), LD-335 (chỉ mục), LD-337 (cải thiện dựa trên kết quả này) |

## 1. Mục tiêu

AI Service đang xếp hạng code liên quan và đoạn tài liệu bằng **TF-IDF** (so khớp từ khoá, FR-AI-03). Câu hỏi của thử nghiệm: thay hoặc kết hợp bằng **embedding** (so khớp theo nghĩa) có cho ngữ cảnh tốt hơn không, và phải trả giá gì (phụ thuộc, tốc độ).

## 2. Dữ liệu thử nghiệm

`experiments/retrieval/dataset.py`: một repository cửa hàng trực tuyến gồm **14 file** đã phân tích (13 Python, 1 Java; 47 mục code trong chỉ mục: 8 lớp, 16 phương thức, 16 hàm, 7 endpoint) và **5 tài liệu** (README, giá, bảo mật, vận hành bằng tiếng Anh; một hướng dẫn tiếng Việt) chia thành 19 đoạn.

Với từng file, kết quả đúng được gán bằng tay: code ở file khác thật sự liên quan (file gọi tới, được gọi, model dùng chung, endpoint phơi ra) và các đoạn tài liệu mô tả cùng chức năng. Tài liệu cố ý dùng từ khác với code ở một số chỗ, giống cách người viết thật: *basket* thay cho *cart*, *promo code* thay cho *voucher*, *value-added tax* thay cho *VAT*, *signs in* thay cho *login*, *delivery cost* thay cho *shipping fee*, và một tài liệu tiếng Việt.

Nhãn do người làm thử nghiệm gán nên con số tuyệt đối chỉ mang tính tham khảo; điều quan trọng là so sánh các phương pháp trên **cùng** bộ nhãn.

## 3. Phương pháp so sánh

Mọi phương pháp dùng cùng các mục trong chỉ mục (LD-335) và cùng câu truy vấn của mỗi file (FR-AI-03.5); lấy tối đa 4 đoạn code và 3 đoạn tài liệu như hệ thống thật.

| Phương pháp | Cách tính điểm |
|---|---|
| **TF-IDF** (đang dùng) | Cosine TF-IDF trên từ đã tách theo định danh; ngưỡng 0,05 |
| **Embedding** | Trung bình vector từ GloVe 100 chiều (Wikipedia + Gigaword, 400.000 từ) của các từ trong mục và trong truy vấn; cosine |
| **Hybrid** | 0,5 × điểm TF-IDF + 0,5 × điểm embedding |

Mô hình embedding câu (sentence-transformers, mô hình đa ngôn ngữ) **không thử được**: môi trường chạy thử không truy cập được nơi lưu mô hình (Hugging Face), và các mô hình này kéo theo phụ thuộc hàng trăm MB (PyTorch/ONNX). GloVe tải được từ GitHub, đủ để đánh giá hướng "so khớp theo nghĩa của từ".

Chỉ số (trung bình trên các file có ít nhất một kết quả đúng): **Recall@k**, **Precision@k**, **MRR** (vị trí kết quả đúng đầu tiên), **nDCG@k** (thứ tự xếp hạng), và **Noise** = số mục không liên quan trả về mỗi file (tính trên mọi file, kể cả file không có gì liên quan).

## 4. Kết quả

Ngưỡng mặc định và ngưỡng tốt nhất của từng phương pháp (ngưỡng tốt nhất được chọn trên chính bộ dữ liệu này nên hơi lạc quan):

| Phương pháp | Code R@4 | Code nDCG@4 | Code noise | Tài liệu R@3 | Tài liệu MRR | Tài liệu nDCG@3 | Tài liệu noise | ms/file |
|---|---|---|---|---|---|---|---|---|
| TF-IDF, ngưỡng 0,05 | **0,91** | **0,93** | 1,50 | 0,61 | 0,49 | 0,43 | 1,86 | **0,25** |
| Embedding GloVe, ngưỡng 0,80 | 0,69 | 0,67 | 1,36 | 0,33 | 0,38 | 0,32 | 0,86 | 0,91 |
| Embedding GloVe, ngưỡng tốt nhất 0,70 | 0,74 | 0,71 | 2,00 | 0,61 | 0,62 | 0,56 | 1,64 | 0,55 |
| Hybrid, ngưỡng 0,45 | **0,91** | 0,89 | **1,00** | 0,44 | 0,57 | 0,47 | **0,71** | 0,76 |
| Hybrid, ngưỡng tốt nhất 0,35 | **0,91** | 0,89 | 1,79 | **0,67** | **0,85** | **0,68** | 1,86 | 0,76 |

Embedding cần tải file vector 130 MB và mất khoảng 2 giây để nạp; 88 % từ trong chỉ mục có vector (các từ tiếng Việt và một số tên riêng không có).

Bảng đầy đủ (thêm Precision và MRR của code): `ai-service/experiments/retrieval/results_ld336.md`.

## 5. Phân tích

1. **Code: TF-IDF tốt hơn rõ.** Code liên quan thường chia sẻ đúng tên định danh (`CartService`, `apply_voucher`, `cart_id`). Lấy trung bình vector từ làm "nhoè" các tên này: nDCG@4 giảm từ 0,93 xuống 0,71. Hybrid giữ được recall của TF-IDF nhưng không vượt.
2. **Tài liệu: cả hai đều yếu, nhưng nguyên nhân chính không phải do thiếu embedding.** Xem từng file cho thấy:
   - Đoạn mở đầu ngắn của README (`# Shop` + "Online shop backend.") đứng **đầu ở 11/14 file**, vì mọi đường dẫn đều bắt đầu bằng `shop/`, từ `shop` có trong mọi truy vấn và đoạn này lại rất ngắn.
   - Các đoạn chỉ có tiêu đề (`# Pricing`) cũng lọt vào kết quả và đứng đầu ở 2 file.
   - Tài liệu dùng từ khác code (*basket*, *promo code*, *signs in*) bị bỏ lỡ; GloVe giúp được một phần, đây là chỗ hybrid tăng MRR tài liệu từ 0,49 lên 0,85.
   - Đoạn tiếng Việt **không phương pháp nào tìm được** (TF-IDF không có từ chung; GloVe chỉ có tiếng Anh).
3. **Chi phí của embedding:** thêm file 130 MB vào image Docker, thêm 2 giây khởi động, chậm hơn 2–4 lần; mô hình đa ngôn ngữ còn nặng hơn nhiều và cần mạng/GPU tuỳ cấu hình.

## 6. Kết luận và đề xuất (đầu vào cho LD-337)

- **Giữ TF-IDF (từ khoá) làm phương pháp mặc định** cho code: chính xác hơn, nhanh, không phụ thuộc ngoài, kết quả tất định.
- Phần lớn lỗi ở tài liệu đến từ chất lượng chỉ mục và truy vấn, sửa được mà không cần embedding (thực hiện ở LD-337):
  - bỏ khỏi truy vấn các từ xuất hiện trong gần như mọi đường dẫn file (tên repository như `shop`);
  - không đưa đoạn chỉ có tiêu đề vào chỉ mục;
  - chuẩn hoá theo độ dài đoạn (BM25), để đoạn rất ngắn không được điểm cao chỉ vì ngắn;
  - ưu tiên code mà file đang viết **gọi tới thật sự** (tên lớp/hàm xuất hiện trong `source`).
- Embedding chỉ đáng thêm sau này dưới dạng **tuỳ chọn** (hybrid), khi có mô hình đa ngôn ngữ chạy được trong hạ tầng của nhóm; khi đó chạy lại `benchmark.py` để đo trên cùng bộ nhãn.

## 7. Cách chạy lại

```bash
cd ai-service
python -m experiments.retrieval.benchmark --tune          # tải GloVe một lần (~130 MB) vào ~/.cache/livingdocs
python -m experiments.retrieval.benchmark --no-embedding  # chỉ TF-IDF, không cần tải gì
```

`tests/test_retrieval_benchmark.py` kiểm tra bộ nhãn khớp với chỉ mục và chạy benchmark phần TF-IDF (không tải GloVe) trong CI.
