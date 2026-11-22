# FR-FE-09 Giao diện duyệt và phê duyệt tài liệu

| Mục | Nội dung |
|---|---|
| Epic Jira | LD-286 Frontend Implementation |
| Task Jira | LD-310 [Review & Approval Interface] Implement Review & Approval Interface |
| Task đã làm | LD-311, LD-312, LD-313, LD-314, LD-315 |
| Người thực hiện | Khôi Nguyễn Hữu Đăng |
| Thành phần | Frontend LivingDocs Web: kiểm tra drift tài liệu, duyệt đề xuất của AI, hàng đợi Staff, hàng đợi Manager, nhận xét và lịch sử phê duyệt |
| Tác nhân | Staff, Manager, Developer (chủ tài liệu), GitHub Integration Service (quy trình duyệt, drift) và AI Service (bằng chứng, phiên bản) |

## 1. Mô tả

Hệ thống cung cấp giao diện web cho toàn bộ quy trình duyệt tài liệu: kiểm tra tài liệu lệch so với mã nguồn (drift), xem và chỉnh đề xuất của AI, hàng đợi duyệt của Staff, hàng đợi phê duyệt của Manager, cùng nhận xét và lịch sử phê duyệt của từng tài liệu. Giao diện chỉ hiển thị và gửi các thao tác mà API quy trình duyệt cho phép; mọi kiểm tra quyền do backend thực hiện.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-FE-09.1 | (LD-311) Kiểm tra drift cho một pull request của repository đã chọn, có tùy chọn kiểm tra thêm README và các file Markdown của repository. |
| FR-FE-09.2 | (LD-311) Hiển thị từng phát hiện drift với mức độ nghiêm trọng, điểm, dấu hiệu phá vỡ (breaking), gợi ý cập nhật, độ tin cậy, lý do xếp mức độ và bằng chứng. |
| FR-FE-09.3 | (LD-311) Lọc phát hiện theo mức độ nghiêm trọng, sao chép báo cáo dạng Markdown, xem lại các lần kiểm tra trước. |
| FR-FE-09.4 | (LD-311) Xử lý từng phát hiện: Acknowledge, Mark resolved, Dismiss (kèm lý do), Reopen. |
| FR-FE-09.5 | (LD-312) Hiển thị danh sách đề xuất của AI cho các tài liệu người dùng có quyền xem, kèm bản so sánh nội dung hiện tại và nội dung AI đề xuất, bản tóm tắt thay đổi và bằng chứng của AI. |
| FR-FE-09.6 | (LD-312) Cho phép chủ tài liệu chỉnh sửa nội dung và ghi chú sau khi Staff yêu cầu chỉnh sửa; bản sửa được lưu thành phiên bản mới. |
| FR-FE-09.7 | (LD-313) Hiển thị hàng đợi của Staff có phân trang, chi tiết tài liệu, nội dung, bản so sánh và bằng chứng. |
| FR-FE-09.8 | (LD-313) Cho phép Staff nhận và trả lại tài liệu, gửi kết quả duyệt đạt hoặc yêu cầu chỉnh sửa kèm nhận xét (tối đa 2.000 ký tự; bắt buộc khi yêu cầu chỉnh sửa). |
| FR-FE-09.9 | (LD-314) Hiển thị hàng đợi chờ phê duyệt và lịch sử quyết định của Manager, có phân trang, kèm chi tiết, nhận xét của Staff, bằng chứng và lịch sử. |
| FR-FE-09.10 | (LD-314) Cho phép Manager phê duyệt, từ chối (kèm lý do bắt buộc) và yêu cầu rollback (kèm phiên bản nguồn, lý do và xác nhận). |
| FR-FE-09.11 | (LD-315) Hiển thị nhận xét của Staff, lý do của Manager và yêu cầu chỉnh sửa trong chi tiết tài liệu. |
| FR-FE-09.12 | (LD-315) Hiển thị lịch sử phê duyệt của một quy trình: hành động, người thực hiện, vai trò, thời điểm, trạng thái trước và sau, nhận xét. |

## 3. Giao diện

| Màn hình / thành phần | Nội dung hiển thị | Yêu cầu |
|---|---|---|
| Documentation Drift | Chọn repository, số pull request, nút Check drift, danh sách phát hiện, bộ lọc mức độ, sao chép Markdown, các lần kiểm tra trước | FR-FE-09.1 – 09.4 |
| AI Suggestion Review | Danh sách đề xuất, so sánh nội dung, tóm tắt thay đổi, bằng chứng AI, biểu mẫu chỉnh sửa sau yêu cầu sửa | FR-FE-09.5 – 09.6 |
| Staff Review Queue | Hàng đợi, chi tiết, nội dung, so sánh, bằng chứng, nút nhận và trả lại, biểu mẫu kết quả duyệt | FR-FE-09.7 – 09.8 |
| Manager Approval | Hàng đợi chờ duyệt, lịch sử quyết định, chi tiết, nút Approve document, Reject document, Request rollback | FR-FE-09.9 – 09.10 |
| Nhận xét và lịch sử | Nhận xét của Staff, lý do của Manager, danh sách sự kiện Approval History | FR-FE-09.11 – 09.12 |

Frontend gọi API cùng origin của Backend (BFF), gồm các API `document-workflows` và các API drift của repository. Đề xuất của AI chỉ được xem và chỉnh sửa: API quy trình công khai không có thao tác chấp nhận hoặc bỏ qua đề xuất, nên giao diện không hiển thị các nút đó.

## 4. Luồng chính

1. Developer gửi tài liệu duyệt; Staff mở hàng đợi, nhận tài liệu, xem nội dung, so sánh và bằng chứng, rồi gửi kết quả đạt hoặc yêu cầu chỉnh sửa kèm nhận xét.
2. Nếu Staff yêu cầu chỉnh sửa, chủ tài liệu mở đề xuất, sửa nội dung kèm ghi chú và lưu phiên bản mới, rồi gửi duyệt lại.
3. Khi Staff duyệt đạt, Manager thấy tài liệu trong hàng đợi, xem nhận xét của Staff, bằng chứng và lịch sử, rồi phê duyệt hoặc từ chối kèm lý do; với tài liệu đã phê duyệt, Manager có thể yêu cầu rollback.
4. Sau mỗi thao tác, giao diện cập nhật hàng đợi và lịch sử; người dùng xem lại từng bước trong Approval History.
5. Tách biệt với luồng trên, người dùng kiểm tra một pull request để biết tài liệu nào lệch so với mã, xem mức độ nghiêm trọng và xử lý từng phát hiện.

## 5. Luồng lỗi

| Trường hợp | Kết quả hiển thị |
|---|---|
| Phiên hết hạn (401) | Thông báo phiên đã hết hạn và quay về đăng nhập |
| Không có quyền (403) | Thông báo không được phép thực hiện thao tác; vai trò không phải Manager không thấy khung phê duyệt |
| Quy trình hoặc tài liệu không còn tồn tại (404) | Thông báo không còn khả dụng |
| Xung đột trạng thái (409), ví dụ tài liệu đã được Staff khác nhận | Thông báo kèm gợi ý làm mới hàng đợi; trạng thái trên giao diện không bị đổi sai |
| Yêu cầu chỉnh sửa không có nhận xét, từ chối không có lý do, rollback thiếu thông tin | Biểu mẫu chặn việc gửi hoặc hiển thị lỗi của backend |
| Hàng đợi trống hoặc không có quy trình nào truy cập được | Trạng thái trống có giải thích, không hiển thị như lỗi |
| Phản hồi API không đúng định dạng | Báo lỗi dữ liệu không hợp lệ thay vì hiển thị trạng thái trống |
| Lỗi tải hoặc lỗi dịch vụ (kể cả drift) | Thông báo lỗi và nút thử lại |

## 6. Quy tắc nghiệp vụ

- Giao diện không tự suy ra kết quả: mọi trạng thái hiển thị lấy từ phản hồi của backend, và không báo thành công khi backend từ chối.
- Staff chỉ thao tác trên tài liệu mình đang phụ trách; Manager không thể quyết định tài liệu mà mình đã duyệt cấp 1 (backend kiểm tra).
- Đề xuất của AI chỉ chỉnh sửa được sau khi Staff yêu cầu chỉnh sửa; quy trình giữ nguyên trạng thái cho tới khi gửi duyệt lại.
- Mức độ nghiêm trọng của drift lấy từ báo cáo của backend; phát hiện thiếu mức độ không bị báo là "không có drift".
- Ghi chú: màn hình Documentation Drift (LD-311) đã được gỡ khỏi giao diện web ngày 17/11/2026 khi dòng #16 bị bỏ khỏi ma trận phân quyền (xem FRCREATEINTERFACE); các thành phần còn lại của task này vẫn dùng, nay được mở theo vai trò (Staff ở Document Review, Manager ở Final Approval).
- Phạm vi PR #125 còn gồm điều chỉnh cấu hình Flyway migration của GitHub Integration Service để CI chạy ổn định.

## 7. Tiêu chí chấp nhận

- **AC-FE-09.1:** Staff thấy hàng đợi, nhận và trả lại tài liệu, gửi kết quả đạt hoặc yêu cầu chỉnh sửa; kết quả hiển thị đúng theo phản hồi của backend.
- **AC-FE-09.2:** Manager thấy hàng đợi chờ duyệt và lịch sử quyết định; phê duyệt, từ chối kèm lý do và rollback hoạt động theo phản hồi của backend.
- **AC-FE-09.3:** Chi tiết tài liệu hiển thị nhận xét của Staff, lý do của Manager, bằng chứng và lịch sử sự kiện.
- **AC-FE-09.4:** Chủ tài liệu chỉnh sửa và lưu được đề xuất sau khi Staff yêu cầu chỉnh sửa; trước đó không chỉnh sửa được.
- **AC-FE-09.5:** Các lỗi 401, 403, 404, 409, hàng đợi trống và dữ liệu sai định dạng đều có thông báo riêng, không bị hiển thị như thành công.
- **AC-FE-09.6:** (khi màn hình còn trên web) Kiểm tra drift hiển thị phát hiện kèm mức độ, lọc theo mức độ, sao chép báo cáo và xử lý từng phát hiện.

## 8. Kiểm thử

Kiểm thử tự động bằng Playwright với API giả: `tests/test_staff_review_queue.py`, `tests/test_manager_approval.py`, `tests/test_documentation_suggestion_review.py` và (trước khi gỡ màn hình) `tests/test_frontend_drift.py`. Jira ghi nhận LD-310 hoàn thành ngày 16/11/2026; mã nguồn được merge qua pull request #125 trên GitHub.
