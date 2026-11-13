# FR-GH-07 Tìm tài liệu bị ảnh hưởng bởi thay đổi mã nguồn

| Mục | Nội dung |
|---|---|
| Feature Jira | epic LD-8 Automatic Documentation Update |
| Task đã làm | LD-122 (LD-123 Map Source Changes to Documentation, LD-124 Identify Affected Documents, LD-125 Analyze Documentation Dependencies, LD-126 Generate Impact Evidence, LD-127 Test Affected Documentation Detection); PR #116 |
| Người thực hiện | Lê Hiền Hải Đăng |
| Thành phần | AI Service (cổng 8001): `app/source_change_impact.py`, endpoint `POST /internal/affected-documents` trong `main.py`; dùng lại bộ so khớp LD-148 `app/drift_affected.py` (của Huy). GitHub Integration Service: `change/AffectedDocumentsClient`, entity `AffectedDocument`, `ImpactEvidence`, `service/SourceChangeService`, `dto/SourceChangeResponse`, migration `V8__affected_documents.sql`. Frontend: mục **Source changes** trong `RepositoryActivity.jsx` |
| Tác nhân | FR-GH-06 (source change vừa lưu); Developer xem trên trang Repository Management; bước cập nhật tài liệu LD-128 (của Linh) đọc kết quả qua API |
| Phụ thuộc | FR-GH-06 (file và code entity thay đổi), FR-AI-06 của Linh (tài liệu đã lưu theo phiên bản, mỗi phần của tài liệu biết được sinh từ file nào) |

## 1. Mô tả

Ngay sau khi FR-GH-06 lưu một source change `PENDING`, GitHub Integration hỏi AI Service phần tài liệu đã lưu nào của repo có thể đã cũ. AI Service dùng lại luật so khớp của LD-148 (phát hiện lệch tài liệu): một phần tài liệu bị ảnh hưởng nếu nó được sinh từ chính file thay đổi, hoặc nhắc tới entity, endpoint, đường dẫn đã thay đổi. Mỗi phần được phân loại **trực tiếp** (`DIRECT`) hay **phụ thuộc** (`DEPENDENT`) và kèm bằng chứng là các dòng trong tài liệu nhắc tới code đã đổi. Kết quả được lưu cùng source change, trả qua API cho bước cập nhật tài liệu (LD-128) và hiển thị trên frontend. Việc gọi `POST /documents/{id}/updates` của LD-128 cho từng tài liệu bị ảnh hưởng chờ LD-128 vào `main`; chạy lại khi lỗi hiện làm qua API, giao diện chỉ báo lỗi.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-GH-07.1 | Chỉ kiểm tra tài liệu của **chính repo**: GitHub Integration lấy danh sách tài liệu đã lưu (`GET /documents` của AI Service), giữ tài liệu có `target` trùng `owner/repo` (không phân biệt hoa thường), giống cách LD-145 chọn tài liệu. Repo chưa có tài liệu nào thì không gọi tiếp, kết quả là danh sách rỗng. |
| FR-GH-07.2 | AI Service nhận source change dạng LD-116 (`files`: `path`, `previous_path`, `change` `ADDED`/`MODIFIED`/`REMOVED`/`RENAMED`, `language`, `entities`: `kind`, `name`, `change`) cùng `document_ids`, và chỉ đọc các tài liệu trong `document_ids`; không có chế độ "mọi tài liệu", nên tài liệu của repo khác không bao giờ bị đọc. Tài liệu không tồn tại thì chỉ là cảnh báo. |
| FR-GH-07.3 | **LD-123, ánh xạ thay đổi với tài liệu.** Một phần (theo file) của phiên bản hiện hành của tài liệu bị ảnh hưởng khi: (a) phần đó được sinh từ file thay đổi, kể cả file bị xoá, đổi tên (so theo `previous_path`), hay file mà FR-GH-06 không tìm được entity; hoặc (b) phần đó nhắc tới entity bị sửa hoặc xoá, endpoint hoặc đường dẫn file đã đổi. Entity `ADDED` chỉ tính cho phần của chính file đó. |
| FR-GH-07.4 | Luật so khớp tên của LD-148: tên phải khớp nguyên từ (`get_user` không khớp `get_users`); từ thường viết thường hoặc tên ≤ 3 ký tự chỉ tính khi nằm trong `code`, khối code hoặc tiêu đề; tên method ngắn (`add` của `Cart.add`) chỉ tính trong phần của chính file, trừ khi tên đặc biệt (có `_`, chữ hoa hoặc số); endpoint khớp mọi kiểu tham số (`{id}`, `:id`, `<id>`). |
| FR-GH-07.5 | **LD-124, tài liệu bị ảnh hưởng.** Kết quả là danh sách phần tài liệu: id, tiêu đề và phiên bản hiện hành của tài liệu lúc kiểm tra, phần bị ảnh hưởng, file mã nguồn mà phần đó được sinh ra, và lý do (`documents changed file <path>`, ``mentions `<tên>` ``). |
| FR-GH-07.6 | **LD-125, phụ thuộc tài liệu.** Mỗi phần là `DIRECT` khi nó được sinh từ chính file thay đổi, `DEPENDENT` khi nó mô tả code khác nhưng nhắc tới code đã thay đổi. Danh sách xếp `DIRECT` trước. |
| FR-GH-07.7 | **LD-126, bằng chứng.** Mỗi phần kèm các chỗ trong tài liệu nhắc tới code đã đổi: `target` (entity, endpoint hoặc đường dẫn), `kind`, `line` (dòng trong phần tài liệu), `excerpt` (đoạn trích dòng đó), theo thứ tự dòng, tối đa 20 chỗ. Phần `DIRECT` không nhắc tên nào thì danh sách rỗng; bằng chứng khi đó là chính file thay đổi trong `files` của source change. |
| FR-GH-07.8 | Lưu kết quả cùng source change và trạng thái `documentsStatus`: `PENDING` (đang tìm), `FOUND` (xong, danh sách có thể rỗng), `FAILED` (AI Service lỗi, `documentsErrorCode = AI_SERVICE_UNAVAILABLE`); `null` khi source change `FAILED`. Source change được phát hiện lại thì tìm lại từ đầu. |
| FR-GH-07.9 | Phát hiện thay đổi vẫn thành công khi bước tìm tài liệu lỗi (source change vẫn `PENDING`). `POST .../source-changes/{changeId}/retry` với source change `PENDING` có `documentsStatus = FAILED` chỉ chạy lại bước tìm tài liệu, không gọi lại GitHub. |
| FR-GH-07.10 | Endpoint của AI Service là endpoint nội bộ, bắt buộc `Authorization: Bearer <INTERNAL_API_SECRET>`: thiếu hoặc sai thì `401`, AI Service chưa cấu hình secret thì `503`. Body sai (không có file, loại thay đổi không hợp lệ) thì `422`. |
| FR-GH-07.11 | **Hiển thị.** Trên trang Repository Management, panel **PRs & commits** có mục **Source changes (n)**: mỗi source change hiện 7 ký tự đầu SHA, "Commit" hoặc "Pull request #n", số file mã nguồn, thời điểm; dưới đó là các tài liệu bị ảnh hưởng (tiêu đề, phần, nhãn **Direct** / **Dependent**, lý do, bằng chứng dạng "Line 14: …"). Trạng thái khác được giải thích: "Checking affected documentation…", "No documentation is affected.", "Affected documentation could not be checked: …", "Changes could not be detected: …". |

## 3. API

| Method | Endpoint | Gọi từ | Kết quả | Yêu cầu |
|---|---|---|---|---|
| GET | `/documents` (AI Service) | GitHub Integration | Danh sách tài liệu đã lưu, lọc theo `target` | FR-GH-07.1 |
| POST | `/internal/affected-documents` (AI Service) | GitHub Integration, `Authorization: Bearer <INTERNAL_API_SECRET>` | `200 {"documents": [...], "warnings": [...]}` | FR-GH-07.2 – 07.7, 07.10 |
| GET | `/api/repositories/{id}/source-changes` | Frontend, LD-128 (qua Backend BFF) | Source change kèm `documentsStatus`, `affectedDocuments` | FR-GH-07.8 |
| POST | `/api/repositories/{id}/source-changes/{changeId}/retry` | Frontend qua Backend BFF | Chạy lại bước tìm tài liệu khi `documentsStatus = FAILED` | FR-GH-07.9 |

Body gửi AI Service:

```json
{"repository": "acme/shop", "document_ids": ["9b2e..."],
 "files": [{"path": "shop/cart.py", "previous_path": null, "change": "MODIFIED", "language": "python",
            "entities": [{"kind": "FUNCTION", "name": "get_cart_total", "change": "MODIFIED"}]}]}
```

Phần thêm vào response của `GET .../source-changes` (FR-GH-06):

```json
{"documentsStatus": "FOUND", "documentsErrorCode": null, "documentsErrorMessage": null,
 "affectedDocuments": [
   {"documentId": "9b2e...", "title": "acme/shop", "version": 3, "section": "shop/cart.py",
    "documentsFile": "shop/cart.py", "dependency": "DIRECT",
    "reasons": ["documents changed file shop/cart.py"], "evidence": []},
   {"documentId": "9b2e...", "title": "acme/shop", "version": 3, "section": "shop/checkout.py",
    "documentsFile": "shop/checkout.py", "dependency": "DEPENDENT",
    "reasons": ["mentions `get_cart_total`"],
    "evidence": [{"target": "get_cart_total", "kind": "name", "line": 14,
                  "excerpt": "Charge the customer get_cart_total(cart_id) of the cart."}]}]}
```

## 4. Dữ liệu

Migration `V8__affected_documents.sql` (V5–V7 đã dùng cho LD-68, LD-116, LD-211):

| Bảng / cột | Nội dung | Ràng buộc |
|---|---|---|
| `source_changes.documents_status`, `documents_error_code`, `documents_error_message` | Trạng thái bước tìm tài liệu | |
| `source_change_documents` | `source_change_id`, `document_id`, `title`, `version`, `section_path`, `documents_file`, `dependency` (`DIRECT` / `DEPENDENT`), `reasons` (mỗi dòng một lý do, ≤ 4000) | Xoá theo source change |
| `source_change_document_evidence` | `document_row_id`, `target` (≤ 500), `kind`, `line_number`, `excerpt` (≤ 300) | Xoá theo phần tài liệu |

AI Service không lưu gì cho bước này; nó chỉ đọc phiên bản hiện hành của các tài liệu được gửi.

## 5. Luồng chính

1. FR-GH-06 lưu source change `PENDING` (`documentsStatus = PENDING`).
2. GitHub Integration đọc file và entity của source change, lấy danh sách tài liệu của repo từ AI Service.
3. Repo có tài liệu: gửi source change và `document_ids` sang `POST /internal/affected-documents`.
4. AI Service dựng danh sách thay đổi theo dạng LD-148, đọc từng phần của phiên bản hiện hành của các tài liệu, so khớp, thêm phần của file thay đổi chưa được so khớp, phân loại `DIRECT` / `DEPENDENT`, trả kết quả kèm dòng và trích đoạn.
5. GitHub Integration lưu kết quả, `documentsStatus = FOUND`.
6. Developer mở **PRs & commits** của repo, xem mục **Source changes**. LD-128 đọc `affectedDocuments` để biết tài liệu nào cần cập nhật.

## 6. Luồng lỗi

| Mã | HTTP | Khi nào | Kết quả |
|---|---|---|---|
| `AI_SERVICE_UNAVAILABLE` | (lưu trong `documentsErrorCode`) | AI Service không gọi được, trả lỗi, hoặc trả dữ liệu sai | `documentsStatus = FAILED`, source change vẫn `PENDING`; gọi retry để chạy lại bước này |
| (AI Service) | 401 / 503 | Thiếu hoặc sai mã nội bộ / AI Service chưa cấu hình `INTERNAL_API_SECRET` | GitHub Integration ghi `AI_SERVICE_UNAVAILABLE` |
| (AI Service) | 422 | Body sai: không có file, loại thay đổi không hợp lệ | GitHub Integration ghi `AI_SERVICE_UNAVAILABLE` |
| `SOURCE_CHANGE_NOT_FAILED` | 409 | Retry khi cả `status` lẫn `documentsStatus` đều không `FAILED` | Không chạy lại |

## 7. Quy tắc nghiệp vụ

- Không viết lại luật so khớp ở Java: dùng chung luật LD-148 với phát hiện lệch tài liệu, để hai chức năng cho cùng kết quả.
- Chỉ đọc tài liệu của chính repo.
- Phần tài liệu của file thay đổi luôn được coi là bị ảnh hưởng, kể cả khi không biết entity nào đổi.
- Bằng chứng tối đa 20 chỗ mỗi phần, đủ để giải thích; danh sách lý do luôn đầy đủ.
- Lỗi AI Service không làm mất kết quả phát hiện thay đổi.

## 8. Tiêu chí chấp nhận

- Sửa `get_cart_total` trong `shop/cart.py`: phần `shop/cart.py` của tài liệu là `DIRECT` (lý do `documents changed file shop/cart.py`); phần `shop/checkout.py` nhắc `get_cart_total` là `DEPENDENT`, có bằng chứng chứa dòng đó; `DIRECT` đứng trước.
- File bị xoá, đổi tên, hoặc sửa mà không biết entity: phần của file đó vẫn là `DIRECT`.
- Thêm entity ở file mới, hoặc đổi code không ai nhắc tới: không có tài liệu nào bị ảnh hưởng.
- Chỉ tài liệu được gửi mới bị đọc; repo chưa có tài liệu thì không gọi AI Service.
- AI Service lỗi: `documentsStatus = FAILED`, retry thì thành `FOUND` mà không gọi lại GitHub.
- Trên frontend thấy nhãn Direct / Dependent, lý do và bằng chứng theo dòng.

## 9. Kiểm thử

| Test | Số test | Nội dung |
|---|---|---|
| `ai-service/tests/test_affected_documents.py` | 10 | Tài liệu sinh offline từ 2 file: entity sửa ảnh hưởng phần của chính file (`DIRECT`) và phần nhắc tới nó (`DEPENDENT`, có trích đoạn); file sửa không biết entity vẫn ảnh hưởng phần của nó; file bị xoá hoặc đổi tên; entity mới và thay đổi không liên quan không ảnh hưởng gì; chỉ kiểm tra tài liệu được gửi; cần mã nội bộ (`401`, `503`); body sai `422`. Chạy bằng `python -m pytest` (job CI **AI Service Build and Test**) |
| `change/AffectedDocumentsClientTest` | 3 | AI Service giả (`MockRestServiceServer`): chỉ gửi tài liệu của repo, đọc phần bị ảnh hưởng và bằng chứng; repo không có tài liệu thì không gọi `POST`; AI Service lỗi thì `AI_SERVICE_UNAVAILABLE` |
| `SourceChangeDetectionTest` (3 test mới) | 3 | Kết quả được lưu cùng source change, `DIRECT` trước, bằng chứng theo dòng, bỏ chỗ thiếu dữ liệu; AI Service lỗi thì `FAILED`, retry chỉ chạy lại bước tìm tài liệu; source change `FAILED` không có bước tìm tài liệu |
| `tests/test_repository_activity.py` (2 test mới) | 2 | Playwright: mục Source changes hiện tài liệu, nhãn Direct / Dependent, lý do và bằng chứng; giải thích các trạng thái rỗng, lỗi AI Service, lỗi phát hiện |

Hai test Java chạy bằng `mvn verify` (job CI **GitHub Integration Service Test**); test giao diện chạy trong job **Frontend E2E Test**.
