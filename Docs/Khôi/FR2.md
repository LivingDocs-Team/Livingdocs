# FR-FE-02 Xem trước, chỉnh sửa và theo dõi chỉnh sửa tài liệu

| Mục | Nội dung |
|---|---|
| Epic Jira | LD-7 Documentation Generation |
| Task Jira | LD-101 [Documentation Preview & Editing] Implement Documentation Preview & Editing |
| Task đã làm | LD-102, LD-103, LD-104 (LD-105 là subtask kiểm thử của cùng task) |
| Người thực hiện | Khôi Nguyễn Hữu Đăng |
| Thành phần | Frontend LivingDocs Web: trang Documentation (xem trước, trình soạn thảo, theo dõi chỉnh sửa) |
| Tác nhân | Người dùng LivingDocs (xem, chỉnh sửa, xem lại thay đổi), AI Service (cung cấp tài liệu đã sinh) |

## 1. Mô tả

Hệ thống cho phép người dùng xem trước tài liệu do AI sinh ra, chỉnh sửa tài liệu đó và theo dõi các thay đổi đã thực hiện. Bản tài liệu gốc do AI sinh được giữ lại trước khi chỉnh sửa, và người dùng xem lại các thay đổi trước khi gửi.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-FE-02.1 | (LD-102) Cho phép xem trước tài liệu đã được AI sinh. |
| FR-FE-02.2 | (LD-102) Hiển thị nội dung tài liệu rõ ràng, dễ đọc. |
| FR-FE-02.3 | (LD-103) Cho phép chỉnh sửa nội dung tài liệu đã sinh bằng trình soạn thảo. |
| FR-FE-02.4 | (LD-103, LD-104) Giữ lại phiên bản tài liệu do AI sinh ra trước khi người dùng chỉnh sửa. |
| FR-FE-02.5 | (LD-104) Theo dõi các chỉnh sửa của người dùng so với bản gốc do AI sinh. |
| FR-FE-02.6 | (LD-104) Cho phép người dùng xem lại các thay đổi trước khi gửi. |

## 3. Giao diện

| Thành phần | Nội dung hiển thị | Yêu cầu |
|---|---|---|
| Xem trước tài liệu | Nội dung tài liệu đã sinh, trình bày rõ ràng | FR-FE-02.1 – 02.2 |
| Trình soạn thảo | Vùng chỉnh sửa nội dung tài liệu | FR-FE-02.3 |
| Theo dõi chỉnh sửa | Bản gốc do AI sinh, các thay đổi của người dùng, bước xem lại trước khi gửi | FR-FE-02.4 – 02.6 |

Frontend lấy tài liệu đã sinh từ AI Service để hiển thị và dùng làm bản gốc. Chi tiết endpoint theo hợp đồng API giữa các service.

## 4. Luồng chính

1. Người dùng mở tài liệu đã sinh; giao diện hiển thị bản xem trước.
2. Người dùng chuyển sang chế độ chỉnh sửa; hệ thống giữ lại bản gốc do AI sinh.
3. Người dùng sửa nội dung trong trình soạn thảo; các thay đổi được theo dõi so với bản gốc.
4. Người dùng xem lại các thay đổi, rồi gửi bản đã chỉnh sửa.

## 5. Luồng lỗi

| Trường hợp | Kết quả hiển thị |
|---|---|
| Không tải được tài liệu | Hiển thị thông báo lỗi, cho phép thử lại |
| Tài liệu chưa có nội dung | Hiển thị trạng thái chưa có tài liệu, không mở trình soạn thảo |
| Gửi bản chỉnh sửa thất bại | Hiển thị lỗi, giữ nguyên nội dung người dùng đã sửa để thử lại |

## 6. Quy tắc nghiệp vụ

- Bản tài liệu do AI sinh luôn được giữ nguyên làm bản gốc; chỉnh sửa của người dùng không ghi đè bản gốc.
- Người dùng luôn có bước xem lại thay đổi trước khi gửi.
- Việc xem trước, chỉnh sửa và theo dõi chỉnh sửa áp dụng cho tài liệu đã sinh xong.

## 7. Tiêu chí chấp nhận

- **AC-FE-02.1:** Mở tài liệu đã sinh thì nội dung hiển thị rõ ràng ở chế độ xem trước.
- **AC-FE-02.2:** Người dùng chỉnh sửa được nội dung tài liệu trong trình soạn thảo.
- **AC-FE-02.3:** Sau khi chỉnh sửa, bản gốc do AI sinh vẫn được giữ lại và có thể đối chiếu.
- **AC-FE-02.4:** Các thay đổi so với bản gốc được hiển thị để người dùng xem lại trước khi gửi.
- **AC-FE-02.5:** Lỗi tải hoặc lỗi gửi được báo cho người dùng và không làm mất nội dung đang chỉnh sửa.

## 8. Kiểm thử

Kiểm thử theo các tiêu chí chấp nhận ở mục 7 trên giao diện web; Jira có subtask riêng LD-105 "Test Documentation Preview & Editing". LD-101 hoàn thành trong Sprint 4 (26/10/2026), có 3 pull request đã merge trên GitHub và 1 build thành công.
