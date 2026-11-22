# FR-KB-05 Quan hệ giữa tài liệu và mã nguồn

| Mục | Nội dung |
|---|---|
| Epic Jira | LD-11 Knowledge Base |
| Task Jira | LD-211 [Code & Documentation Relationship] Implement Code & Documentation Relationship |
| Task đã làm | LD-212, LD-213, LD-214, LD-215, LD-216 |
| Người thực hiện | Khôi Nguyễn Hữu Đăng |
| Thành phần | GitHub Integration Service (lưu và cung cấp quan hệ tài liệu - mã nguồn) và Frontend LivingDocs Web (trang Documentation) |
| Tác nhân | Người dùng LivingDocs (xem, tạo và theo dõi liên kết), GitHub Integration Service (lưu tài liệu đã sinh, thực thể mã và liên kết) |

## 1. Mô tả

Hệ thống lưu mỗi tài liệu đã sinh thành một bản ghi có mã định danh riêng, lưu các thực thể mã nguồn đã phân tích của repository, và cho phép người dùng liên kết tài liệu với mã nguồn liên quan. Từ một tài liệu người dùng xem được mã nguồn liên kết; từ một thực thể mã người dùng xem được các tài liệu liên kết với nó.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-KB-05.1 | (LD-212) Mỗi tài liệu đã sinh có mã định danh riêng (`documentId`) bên cạnh mã công việc sinh (`jobId`); mỗi thực thể mã có mã định danh ổn định theo repository, đường dẫn file, loại thực thể và tên đầy đủ. |
| FR-KB-05.2 | (LD-212) Thực thể mã không còn trong file đã phân tích được đánh dấu không hoạt động; liên kết cũ được giữ và hiện lại khi thực thể xuất hiện trở lại. |
| FR-KB-05.3 | (LD-213) Cho phép liên kết một tài liệu với một hoặc nhiều thực thể mã đang hoạt động của cùng repository, và thay thế toàn bộ liên kết; danh sách rỗng nghĩa là gỡ hết liên kết. |
| FR-KB-05.4 | (LD-214) Hiển thị danh sách thực thể mã của repository kèm trạng thái đã liên kết với tài liệu đang mở, và lưu bằng nút "Save code links". |
| FR-KB-05.5 | (LD-215) Từ tài liệu, xem được mã nguồn liên kết và mở mã nguồn trên GitHub. |
| FR-KB-05.6 | (LD-215) Từ thực thể mã, bấm "Related documents" để xem các tài liệu liên kết và mở lại tài liệu đó. |
| FR-KB-05.7 | (LD-214) Hiển thị trạng thái đang tải, chưa có thực thể mã, chưa có tài liệu liên kết và lỗi tải hoặc lưu liên kết. |

## 3. Giao diện

| Màn hình / thành phần | Nội dung hiển thị | Yêu cầu |
|---|---|---|
| Khối "Related source code" | Danh sách thực thể mã của repository, ô chọn liên kết, nút "Save code links" | FR-KB-05.3 – 05.4 |
| Điều hướng tài liệu tới mã | Mã nguồn đã liên kết với tài liệu và liên kết mở nguồn trên GitHub | FR-KB-05.5 |
| Điều hướng mã tới tài liệu | Nút "Related documents" cho từng thực thể và danh sách "Documentation linked to this code entity" | FR-KB-05.6 |
| Trạng thái | Đang tải, chưa có thực thể mã, chưa có liên kết, lỗi | FR-KB-05.7 |

API của GitHub Integration Service: `GET /api/repositories/{id}/code-entities`, `GET /api/repositories/{id}/documentation`, `GET /api/documentation/{documentId}`, `GET` và `PUT /api/documentation/{documentId}/code-entities`, `GET /api/documentation/code-entities/{entityId}/documents`. Chi tiết theo hợp đồng `documentation-code-relationship-contract.md` của service đó.

## 4. Luồng chính

1. Người dùng sinh tài liệu cho repository; hệ thống lưu tài liệu với `documentId` và phân tích thực thể mã của repository.
2. Người dùng mở tài liệu trong trang Documentation; giao diện hiển thị khối "Related source code".
3. Người dùng chọn các thực thể mã liên quan và bấm "Save code links"; hệ thống thay thế toàn bộ liên kết của tài liệu.
4. Người dùng bấm "Related documents" ở một thực thể mã để xem các tài liệu liên kết với thực thể đó và mở lại tài liệu cần xem.

## 5. Luồng lỗi

| Trường hợp | Kết quả hiển thị |
|---|---|
| Không tải được thực thể mã hoặc liên kết | Thông báo lỗi, không làm mất nội dung tài liệu đang xem |
| Repository chưa có thực thể mã đã phân tích | Thông báo chưa có thực thể mã, không cho tạo liên kết |
| Lưu liên kết có thực thể không tồn tại, không hoạt động hoặc thuộc repository khác | API trả lỗi 400 và giao diện hiển thị thông báo, liên kết cũ được giữ nguyên |
| Thực thể mã chưa liên kết với tài liệu nào | Thông báo chưa có tài liệu liên kết |
| Tài liệu hoặc thực thể không thuộc người dùng | API không cho truy cập (không trả dữ liệu của người khác) |

## 6. Quy tắc nghiệp vụ

- Liên kết chỉ nối tài liệu với thực thể mã của cùng repository; ID trùng lặp trong yêu cầu được loại bỏ.
- Quyền sở hữu tài liệu và thực thể mã được kiểm tra theo repository đã kết nối của người dùng.
- Xóa repository thì xóa luôn tài liệu, thực thể mã và liên kết của repository đó; tính năng này không ghi lại tài liệu hay bản chụp mã nguồn đã có.
- Số dòng chỉ là siêu dữ liệu: thay đổi số dòng không làm đổi mã định danh của thực thể.

## 7. Tiêu chí chấp nhận

- **AC-KB-05.1:** Sau khi sinh tài liệu, tài liệu có `documentId` và mở lại được từ danh sách tài liệu đã lưu.
- **AC-KB-05.2:** Người dùng chọn thực thể mã, bấm "Save code links" thì từ tài liệu xem lại được đúng các thực thể đã liên kết.
- **AC-KB-05.3:** Từ một thực thể mã, "Related documents" hiển thị các tài liệu liên kết và mở lại được tài liệu.
- **AC-KB-05.4:** Liên kết không hợp lệ bị từ chối và không làm mất liên kết hiện có.
- **AC-KB-05.5:** Thực thể mã đã biến mất khỏi file không còn xuất hiện trong kết quả nhưng liên kết cũ vẫn được giữ.

## 8. Kiểm thử

Jira có subtask kiểm thử LD-216 "Test Documentation-to-Code Relationships". Kiểm thử tự động gồm `DocumentationCodeRelationshipApiTest` và `DocumentationGenerationServiceTest` (GitHub Integration Service) và kịch bản giao diện `test_ld211_documentation_code_relationship_flow` trong `tests/test_frontend.py`. Jira ghi nhận LD-211 hoàn thành ngày 10/11/2026; mã nguồn được merge qua pull request #102 trên GitHub.
