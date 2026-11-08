# FR-FE-03 Giao diện quản lý tài liệu (sinh tài liệu, xem trước và chỉnh sửa)

| Mục | Nội dung |
|---|---|
| Epic Jira | LD-286 Frontend Implementation |
| Task Jira | LD-304 [Documentation Management Interface] Implement Documentation Management Interface |
| Task đã làm | LD-305, LD-307 (cùng task còn LD-306 Template UI, LD-308 Update & Version UI, LD-309 Diff & Rollback UI) |
| Người thực hiện | Khôi Nguyễn Hữu Đăng |
| Thành phần | Frontend LivingDocs Web: trang Documentation (giao diện sinh tài liệu, giao diện xem trước và chỉnh sửa) |
| Tác nhân | Người dùng LivingDocs, AI Service (sinh tài liệu và trả kết quả) |

## 1. Mô tả

Hệ thống cung cấp giao diện quản lý tài liệu trên ứng dụng web LivingDocs. Người dùng yêu cầu sinh tài liệu từ mã nguồn, theo dõi trạng thái sinh, xem tài liệu đã sinh, rồi xem trước và chỉnh sửa tài liệu ngay trong giao diện. Trạng thái sinh và bằng chứng (grounding evidence) được hiển thị cùng tài liệu.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-FE-03.1 | (LD-305) Có giao diện để người dùng yêu cầu sinh tài liệu từ mã nguồn. |
| FR-FE-03.2 | (LD-305) Hiển thị trạng thái sinh tài liệu trong lúc sinh và khi kết thúc (thành công hoặc lỗi). |
| FR-FE-03.3 | (LD-305) Hiển thị tài liệu đã sinh khi quá trình sinh hoàn tất. |
| FR-FE-03.4 | (LD-307) Có giao diện xem trước tài liệu đã sinh. |
| FR-FE-03.5 | (LD-307) Có giao diện chỉnh sửa tài liệu đã sinh. |
| FR-FE-03.6 | (LD-304) Hiển thị bằng chứng (grounding evidence) kèm tài liệu để người dùng đối chiếu nội dung với mã nguồn. |

## 3. Giao diện

| Thành phần | Nội dung hiển thị | Yêu cầu |
|---|---|---|
| Sinh tài liệu | Điều khiển yêu cầu sinh, trạng thái sinh, kết quả hoặc lỗi | FR-FE-03.1 – 03.3 |
| Xem trước tài liệu | Nội dung tài liệu đã sinh | FR-FE-03.4 |
| Chỉnh sửa tài liệu | Vùng chỉnh sửa nội dung tài liệu | FR-FE-03.5 |
| Bằng chứng | Thông tin grounding evidence đi kèm tài liệu | FR-FE-03.6 |

Frontend gọi AI Service để yêu cầu sinh tài liệu và lấy trạng thái, kết quả, bằng chứng. Chi tiết endpoint theo hợp đồng API giữa các service. Phần lựa chọn mẫu tài liệu (LD-306), cập nhật và phiên bản (LD-308), so sánh khác biệt và khôi phục (LD-309) thuộc cùng task LD-304 nhưng nằm ngoài phạm vi tài liệu này.

## 4. Luồng chính

1. Người dùng mở trang Documentation và yêu cầu sinh tài liệu cho mã nguồn đã chọn.
2. Giao diện hiển thị trạng thái sinh cho tới khi quá trình sinh kết thúc.
3. Khi hoàn tất, giao diện hiển thị tài liệu đã sinh cùng bằng chứng.
4. Người dùng xem trước tài liệu, chuyển sang chỉnh sửa khi cần và lưu thay đổi.

## 5. Luồng lỗi

| Trường hợp | Kết quả hiển thị |
|---|---|
| Yêu cầu sinh tài liệu thất bại | Hiển thị thông báo lỗi, cho phép yêu cầu lại |
| Quá trình sinh kết thúc với lỗi | Hiển thị trạng thái lỗi kèm thông tin lỗi, không hiển thị tài liệu rỗng |
| Không tải được tài liệu để xem trước hoặc chỉnh sửa | Hiển thị thông báo lỗi, cho phép thử lại |

## 6. Quy tắc nghiệp vụ

- Chỉ tài liệu đã sinh xong mới được xem trước và chỉnh sửa.
- Trạng thái sinh luôn được hiển thị để người dùng biết tài liệu đã sẵn sàng hay chưa.
- Bằng chứng được hiển thị cùng tài liệu để người dùng kiểm tra độ tin cậy của nội dung.
- Frontend không tự sinh nội dung tài liệu; nội dung đến từ AI Service.

## 7. Tiêu chí chấp nhận

- **AC-FE-03.1:** Người dùng yêu cầu sinh tài liệu từ giao diện thì thấy trạng thái sinh được cập nhật cho tới khi kết thúc.
- **AC-FE-03.2:** Sinh thành công thì tài liệu đã sinh được hiển thị; sinh lỗi thì hiển thị lỗi và cho phép thử lại.
- **AC-FE-03.3:** Người dùng xem trước được tài liệu đã sinh.
- **AC-FE-03.4:** Người dùng chỉnh sửa được tài liệu đã sinh trong giao diện.
- **AC-FE-03.5:** Bằng chứng đi kèm tài liệu được hiển thị để đối chiếu.

## 8. Kiểm thử

Kiểm thử theo các tiêu chí chấp nhận ở mục 7 trên giao diện web. LD-305 và LD-307 hoàn thành ngày 20/10/2026, task cha LD-304 hoàn thành trong Sprint 3 (21/10/2026), có 1 pull request đã merge trên GitHub và 1 build thành công.
