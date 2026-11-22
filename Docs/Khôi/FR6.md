# FR-RW-06 Quy trình duyệt tài liệu cấp 1 dành cho Staff

| Mục | Nội dung |
|---|---|
| Epic Jira | LD-12 Review & Approval Workflow |
| Task Jira | LD-233 [Staff Review] Implement Staff Review |
| Task đã làm | LD-234, LD-235, LD-236, LD-237, LD-238 |
| Người thực hiện | Khôi Nguyễn Hữu Đăng |
| Thành phần | GitHub Integration Service (quy trình duyệt tài liệu `document-workflows`) và AI Service (phiên bản tài liệu, bằng chứng, so sánh phiên bản) |
| Tác nhân | Staff (nhận và duyệt tài liệu), Developer (gửi tài liệu duyệt), AI Service (lưu phiên bản và bằng chứng của tài liệu) |

## 1. Mô tả

Hệ thống cung cấp quy trình duyệt cấp 1 cho Staff. Tài liệu do Developer gửi duyệt xuất hiện trong hàng đợi của Staff; Staff nhận một tài liệu, xem nội dung cùng bằng chứng (grounding evidence), so sánh bản gửi duyệt với bản đã duyệt gần nhất, rồi quyết định: đạt (chuyển lên Manager) hoặc yêu cầu chỉnh sửa (trả lại cho người gửi). Mọi bước được ghi vào lịch sử của quy trình.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-RW-06.1 | (LD-234) Cung cấp hàng đợi các tài liệu chờ Staff duyệt (`PENDING_STAFF_REVIEW`) và các tài liệu do chính Staff đang duyệt (`STAFF_REVIEWING`), có phân trang. |
| FR-RW-06.2 | (LD-234) Cho phép Staff nhận tài liệu để duyệt (claim) và trả lại tài liệu đã nhận (release). |
| FR-RW-06.3 | (LD-235) Cung cấp nội dung tài liệu của phiên bản đang chờ duyệt cho Staff đang phụ trách. |
| FR-RW-06.4 | (LD-235) Cung cấp bằng chứng (grounding evidence) của tài liệu kèm kết quả đối chiếu với mã nguồn gốc (repository, nhánh, commit) để Staff đối chiếu. |
| FR-RW-06.5 | (LD-236) So sánh phiên bản đang chờ duyệt với phiên bản đã duyệt gần nhất và trả về bản khác biệt. |
| FR-RW-06.6 | (LD-237) Cho phép Staff gửi kết quả duyệt: đạt (`PASSED`) hoặc yêu cầu chỉnh sửa (`CHANGES_REQUESTED`) kèm nhận xét. |
| FR-RW-06.7 | (LD-237) Kết quả đạt chuyển quy trình sang chờ Manager (`PENDING_MANAGER_APPROVAL`); yêu cầu chỉnh sửa chuyển sang `CHANGES_REQUESTED` để người gửi sửa và gửi lại. |
| FR-RW-06.8 | (LD-233) Ghi lại người thực hiện, vai trò, thời điểm, trạng thái trước và sau, và nhận xét của từng bước vào lịch sử quy trình. |

## 3. Giao diện

Phần này là giao diện lập trình (API) do GitHub Integration Service cung cấp; giao diện web dùng các API này nằm ở task LD-310 (xem FR9).

| Thành phần | Nội dung | Yêu cầu |
|---|---|---|
| `GET /api/document-workflows/staff/queue` | Hàng đợi của Staff, có phân trang (`page`, `size` từ 1 đến 100) | FR-RW-06.1 |
| `POST /api/document-workflows/{id}/claim` và `/release` | Nhận và trả lại tài liệu | FR-RW-06.2 |
| `GET /api/document-workflows/{id}/document` | Nội dung phiên bản đang chờ duyệt | FR-RW-06.3 |
| `GET /api/document-workflows/{id}/review-evidence` | Bằng chứng và kết quả đối chiếu nguồn | FR-RW-06.4 |
| `GET /api/document-workflows/{id}/review-comparison` | Bản so sánh với phiên bản đã duyệt gần nhất | FR-RW-06.5 |
| `POST /api/document-workflows/{id}/staff-review` | Gửi kết quả duyệt và nhận xét | FR-RW-06.6 – 06.7 |
| `GET /api/document-workflows/{id}/history` | Lịch sử các bước của quy trình | FR-RW-06.8 |

## 4. Luồng chính

1. Developer gửi tài liệu duyệt; quy trình ở trạng thái `PENDING_STAFF_REVIEW` và xuất hiện trong hàng đợi của Staff.
2. Staff mở hàng đợi, chọn tài liệu và nhận để duyệt; quy trình chuyển sang `STAFF_REVIEWING` và gán cho Staff đó.
3. Staff xem nội dung, bằng chứng và bản so sánh với phiên bản đã duyệt gần nhất.
4. Staff gửi kết quả: đạt thì quy trình chuyển sang `PENDING_MANAGER_APPROVAL`; yêu cầu chỉnh sửa (kèm nhận xét) thì quy trình chuyển sang `CHANGES_REQUESTED`.
5. Mỗi bước được ghi vào lịch sử quy trình.

## 5. Luồng lỗi

| Trường hợp | Kết quả |
|---|---|
| Nhận tài liệu không còn ở trạng thái chờ duyệt (đã có người nhận) | Lỗi 409, quy trình không đổi |
| Trả lại tài liệu khi không phải Staff đang phụ trách | Lỗi 403 |
| Xem nội dung, bằng chứng hoặc so sánh khi không phải Staff đang phụ trách tài liệu đó | Lỗi 403 |
| Yêu cầu chỉnh sửa mà không có nhận xét | Lỗi 400 "A comment is required when requesting changes." |
| Quy trình không có phiên bản đã gửi hoặc phiên bản chờ duyệt không khớp phiên bản đã gửi | Lỗi 409 |
| Người dùng không có quyền hoặc vai trò Staff | Lỗi 403; không có tài liệu nào bị lộ |
| Quy trình bị thay đổi đồng thời | Lỗi 409, yêu cầu tải lại và thử lại |

## 6. Quy tắc nghiệp vụ

- Chỉ tài liệu ở trạng thái `PENDING_STAFF_REVIEW` mới được nhận; chỉ Staff đang phụ trách mới được trả lại, xem nội dung duyệt và gửi kết quả.
- Quyền được kiểm tra bằng các quyền `DOCUMENT_REVIEW_QUEUE_VIEW`, `DOCUMENT_CLAIM`, `DOCUMENT_RELEASE`, `DOCUMENT_REVIEW` và vai trò chính của người dùng do Backend xác thực; danh tính do client gửi không được tin cậy.
- Việc gán lại người duyệt chỉ dành cho Administrator có quyền `DOCUMENT_REASSIGN`.
- Bản so sánh dùng phiên bản đã duyệt gần nhất làm mốc; bằng chứng kèm kết quả đối chiếu với mã nguồn gốc.
- Phạm vi chưa làm so với mô tả Jira: chưa có sổ thay đổi riêng của tài liệu (change log) và chưa có bước kiểm tra tự động tài liệu theo mẫu (template). Yêu cầu chỉnh sửa là cách Staff trả tài liệu về cho người gửi.

## 7. Tiêu chí chấp nhận

- **AC-RW-06.1:** Staff thấy tài liệu chờ duyệt và tài liệu mình đang duyệt trong hàng đợi, có phân trang.
- **AC-RW-06.2:** Một tài liệu chỉ có thể được một Staff nhận; Staff khác nhận cùng lúc nhận lỗi 409.
- **AC-RW-06.3:** Staff đang phụ trách xem được nội dung, bằng chứng và bản so sánh; người khác bị từ chối.
- **AC-RW-06.4:** Kết quả đạt chuyển tài liệu lên Manager; yêu cầu chỉnh sửa phải có nhận xét và trả tài liệu về cho người gửi.
- **AC-RW-06.5:** Lịch sử ghi đủ người thực hiện, vai trò, thời điểm, trạng thái trước và sau của từng bước.

## 8. Kiểm thử

Jira có subtask kiểm thử LD-238 "Test Staff Review Workflow". Kiểm thử tự động gồm `DocumentWorkflowServiceTest` (GitHub Integration Service) và `ai-service/tests/test_versions.py` (phiên bản, bằng chứng và so sánh trên AI Service). Quy trình từ gửi duyệt đến quyết định của Manager còn được kiểm tra đầu cuối ở LD-403 (xem FR10). Jira ghi nhận LD-233 hoàn thành ngày 09/11/2026; mã nguồn được merge qua pull request #111 trên GitHub.
