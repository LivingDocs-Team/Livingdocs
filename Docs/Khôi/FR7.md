# FR-RW-07 Quy trình phê duyệt tài liệu cuối cùng dành cho Manager

| Mục | Nội dung |
|---|---|
| Epic Jira | LD-12 Review & Approval Workflow |
| Task Jira | LD-239 [Manager Approval] Implement Manager Approval |
| Task đã làm | LD-240, LD-241, LD-242, LD-243, LD-244 |
| Người thực hiện | Khôi Nguyễn Hữu Đăng |
| Thành phần | GitHub Integration Service (quy trình duyệt tài liệu `document-workflows`), AI Service (phiên bản tài liệu, duyệt và rollback phiên bản) và Backend (danh mục quyền của các vai trò) |
| Tác nhân | Manager (phê duyệt, từ chối, rollback), Staff (người đã duyệt cấp 1), AI Service (áp dụng quyết định lên phiên bản tài liệu) |

## 1. Mô tả

Hệ thống cung cấp bước phê duyệt cuối cùng cho Manager. Chỉ tài liệu đã được Staff duyệt đạt mới xuất hiện trong hàng đợi của Manager. Manager xem nhận xét của Staff, bằng chứng của tài liệu và toàn bộ lịch sử trước khi quyết định phê duyệt hoặc từ chối, và có thể rollback một tài liệu đã phê duyệt về phiên bản trước đó. Mỗi quyết định ghi lại người quyết định, thời điểm và lý do.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-RW-07.1 | (LD-240) Cung cấp hàng đợi các tài liệu chờ Manager phê duyệt (`PENDING_MANAGER_APPROVAL`), có phân trang. |
| FR-RW-07.2 | (LD-241) Cung cấp cho Manager kết quả và nhận xét của Staff cùng bằng chứng (grounding evidence) của tài liệu. |
| FR-RW-07.3 | (LD-242) Cung cấp lịch sử đầy đủ của quy trình (audit trail) để Manager xem trước khi quyết định. |
| FR-RW-07.4 | (LD-243) Cho phép Manager phê duyệt tài liệu; phê duyệt áp dụng phiên bản đã duyệt lên tài liệu và chuyển quy trình sang `APPROVED`. |
| FR-RW-07.5 | (LD-243) Cho phép Manager từ chối tài liệu kèm lý do bắt buộc; quy trình chuyển sang `REJECTED`. |
| FR-RW-07.6 | (LD-239) Cho phép Manager rollback một tài liệu đã phê duyệt về một phiên bản trước, kèm lý do bắt buộc; phiên bản khôi phục phải được Staff duyệt lại. |
| FR-RW-07.7 | (LD-239) Ghi lại người quyết định, thời điểm và lý do cho mỗi quyết định phê duyệt, từ chối và rollback. |
| FR-RW-07.8 | (LD-239) Thêm quyền `DOCUMENT_ROLLBACK` vào danh mục quyền và gán cho vai trò Manager cùng với quyền xem hàng đợi, phê duyệt và từ chối. |

## 3. Giao diện

Phần này là giao diện lập trình (API) do GitHub Integration Service cung cấp; giao diện web dùng các API này nằm ở task LD-310 (xem FR9).

| Thành phần | Nội dung | Yêu cầu |
|---|---|---|
| `GET /api/document-workflows/manager/queue` | Hàng đợi của Manager, có phân trang | FR-RW-07.1 |
| `GET /api/document-workflows/{id}` và `/evidence` | Chi tiết quy trình, kết quả và nhận xét của Staff, bằng chứng tài liệu | FR-RW-07.2 |
| `GET /api/document-workflows/{id}/history` | Lịch sử quy trình | FR-RW-07.3 |
| `POST /api/document-workflows/{id}/approve` | Phê duyệt (không cần nội dung yêu cầu) | FR-RW-07.4 |
| `POST /api/document-workflows/{id}/reject` | Từ chối kèm lý do | FR-RW-07.5 |
| `POST /api/document-workflows/{id}/rollback` | Rollback kèm `sourceVersion` và lý do | FR-RW-07.6 |

## 4. Luồng chính

1. Staff duyệt đạt; quy trình ở trạng thái `PENDING_MANAGER_APPROVAL` và xuất hiện trong hàng đợi của Manager.
2. Manager mở tài liệu, xem nhận xét của Staff, bằng chứng và lịch sử.
3. Manager phê duyệt: AI Service áp dụng phiên bản đã duyệt, quy trình chuyển sang `APPROVED` và quyết định được ghi vào lịch sử. Hoặc Manager từ chối kèm lý do: quy trình chuyển sang `REJECTED`.
4. Với tài liệu đã phê duyệt, Manager có thể rollback về một phiên bản trước kèm lý do; AI Service tạo phiên bản mới từ phiên bản đó và quy trình quay lại bước Staff duyệt.

## 5. Luồng lỗi

| Trường hợp | Kết quả |
|---|---|
| Quyết định khi quy trình chưa ở trạng thái chờ Manager hoặc Staff chưa duyệt đạt | Lỗi 409 "Manager decisions require a successful staff review." |
| Staff đã duyệt tài liệu cố gắng ra quyết định cuối cùng | Lỗi 403 "The staff reviewer cannot make the final manager decision." |
| Từ chối không có lý do | Lỗi 400 "A rejection reason is required." |
| Phiên bản tài liệu thay đổi trong lúc duyệt | Lỗi 409 "The document version changed during review." |
| Rollback tài liệu chưa được phê duyệt | Lỗi 409 "Only an approved document can be rolled back." |
| Rollback thiếu phiên bản nguồn hợp lệ, thiếu lý do hoặc chọn đúng phiên bản đang được duyệt | Lỗi 400 với thông báo tương ứng |
| Rollback khi tài liệu đang có phiên bản chờ xử lý hoặc phiên bản hiện tại không khớp quy trình | Lỗi 409 "The document version changed. Reload and retry." |
| Người dùng không có quyền hoặc không phải Manager | Lỗi 403; không có tài liệu nào bị lộ |

## 6. Quy tắc nghiệp vụ

- Chỉ Manager có quyền `DOCUMENT_APPROVE`, `DOCUMENT_REJECT` hoặc `DOCUMENT_ROLLBACK` mới thực hiện được quyết định tương ứng; quyền xem hàng đợi là `DOCUMENT_APPROVAL_QUEUE_VIEW`. Vai trò chính của người dùng do Backend xác thực.
- Người đã duyệt cấp 1 không được ra quyết định cuối cùng cho cùng tài liệu.
- Từ chối là trạng thái cuối của quy trình (`REJECTED`); tài liệu cần quy trình mới nếu muốn gửi lại.
- Rollback không xóa lịch sử: phiên bản khôi phục là một phiên bản mới, phải qua Staff duyệt lại, và sự kiện `ROLLBACK_REQUESTED` ghi phiên bản nguồn cùng lý do.
- Phạm vi chưa làm so với mô tả Jira: Manager chưa có thao tác "trả về chỉnh sửa" riêng; việc yêu cầu chỉnh sửa do Staff thực hiện ở bước cấp 1.

## 7. Tiêu chí chấp nhận

- **AC-RW-07.1:** Manager chỉ thấy tài liệu đã được Staff duyệt đạt trong hàng đợi.
- **AC-RW-07.2:** Manager xem được nhận xét của Staff, bằng chứng và lịch sử trước khi quyết định.
- **AC-RW-07.3:** Phê duyệt chuyển quy trình sang `APPROVED`; từ chối phải có lý do và chuyển sang `REJECTED`.
- **AC-RW-07.4:** Rollback chỉ áp dụng cho tài liệu đã phê duyệt, cần phiên bản nguồn khác phiên bản hiện tại cùng lý do, và đưa phiên bản mới về bước Staff duyệt.
- **AC-RW-07.5:** Mỗi quyết định ghi lại người quyết định, thời điểm và lý do; người không có quyền bị từ chối.

## 8. Kiểm thử

Jira có subtask kiểm thử LD-244 "Test Manager Approval Workflow". Kiểm thử tự động gồm `DocumentWorkflowServiceTest`, `DocumentWorkflowControllerTest` và `GitHubIntegrationFlowTest` (GitHub Integration Service), `RoleCatalogInitializerTest` (Backend, danh mục quyền) và `ai-service/tests/test_versions.py` (duyệt và rollback phiên bản). Quy trình từ gửi duyệt đến quyết định của Manager được kiểm tra đầu cuối ở LD-403 (xem FR10). Jira ghi nhận LD-239 hoàn thành ngày 10/11/2026 (00:01); mã nguồn được merge qua pull request #110 trên GitHub.
