# FR-FE-01 Giao diện kết nối GitHub và quản lý repository

| Mục | Nội dung |
|---|---|
| Epic Jira | LD-286 Frontend Implementation |
| Task Jira | LD-298 [GitHub & Repository Interface] Implement GitHub & Repository Interface |
| Task đã làm | LD-299, LD-300, LD-301, LD-303 |
| Người thực hiện | Khôi Nguyễn Hữu Đăng |
| Thành phần | Frontend LivingDocs Web: màn hình kết nối GitHub, danh sách repository, chọn repository, đồng bộ repository |
| Tác nhân | Người dùng LivingDocs (kết nối GitHub, chọn và đồng bộ repository), GitHub Integration Service (phía backend cung cấp dữ liệu) |

## 1. Mô tả

Hệ thống cung cấp giao diện web để người dùng kết nối hoặc ngắt kết nối tài khoản GitHub, xem trạng thái kết nối, xem các repository khả dụng, chọn repository đưa vào workspace và đồng bộ lại thủ công. Trạng thái đồng bộ và lỗi liên quan được hiển thị rõ ràng để người dùng biết repository đã sẵn sàng cho bước phân tích và sinh tài liệu hay chưa.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-FE-01.1 | (LD-299) Có giao diện kết nối tài khoản GitHub và ngắt kết nối tài khoản đã kết nối. |
| FR-FE-01.2 | (LD-299) Hiển thị trạng thái kết nối GitHub hiện tại (đã kết nối hoặc chưa kết nối). |
| FR-FE-01.3 | (LD-300) Hiển thị danh sách repository GitHub khả dụng của tài khoản đã kết nối. |
| FR-FE-01.4 | (LD-300) Khi chưa kết nối GitHub, hoặc danh sách rỗng, hoặc tải danh sách lỗi, giao diện hiển thị trạng thái tương ứng thay vì danh sách trống không giải thích. |
| FR-FE-01.5 | (LD-301) Cho phép người dùng chọn các repository đưa vào workspace. |
| FR-FE-01.6 | (LD-301) Hiển thị các repository đã được chọn (đã kết nối vào workspace) để người dùng quản lý. |
| FR-FE-01.7 | (LD-303) Cho phép đồng bộ lại repository thủ công. |
| FR-FE-01.8 | (LD-303) Hiển thị trạng thái đồng bộ của repository và thông báo lỗi liên quan khi đồng bộ thất bại. |

## 3. Giao diện

| Màn hình / thành phần | Nội dung hiển thị | Yêu cầu |
|---|---|---|
| Kết nối GitHub | Nút kết nối, nút ngắt kết nối, nhãn trạng thái kết nối | FR-FE-01.1 – 01.2 |
| Danh sách repository | Các repository khả dụng, trạng thái rỗng, trạng thái lỗi | FR-FE-01.3 – 01.4 |
| Chọn repository | Thao tác chọn repository đưa vào workspace, danh sách repository đã chọn | FR-FE-01.5 – 01.6 |
| Đồng bộ repository | Nút đồng bộ thủ công, trạng thái đồng bộ, lỗi đồng bộ | FR-FE-01.7 – 01.8 |

Frontend gọi API của GitHub Integration Service để lấy trạng thái kết nối, danh sách repository, lưu lựa chọn và kích hoạt đồng bộ. Chi tiết endpoint theo hợp đồng API của service đó.

## 4. Luồng chính

1. Người dùng mở trang GitHub & Repository; giao diện hiển thị trạng thái kết nối GitHub.
2. Nếu chưa kết nối, người dùng chọn kết nối GitHub và hoàn tất xác thực; giao diện cập nhật sang trạng thái đã kết nối.
3. Giao diện tải và hiển thị danh sách repository khả dụng.
4. Người dùng chọn repository đưa vào workspace; repository đã chọn xuất hiện trong danh sách quản lý.
5. Người dùng bấm đồng bộ; giao diện hiển thị trạng thái đồng bộ cho tới khi hoàn tất hoặc báo lỗi.

## 5. Luồng lỗi

| Trường hợp | Kết quả hiển thị |
|---|---|
| Chưa kết nối GitHub | Hiển thị trạng thái chưa kết nối và nút kết nối; không hiển thị danh sách repository |
| Kết nối GitHub thất bại | Hiển thị thông báo lỗi, giữ trạng thái chưa kết nối |
| Tải danh sách repository lỗi | Hiển thị thông báo lỗi, cho phép thử lại |
| Tài khoản không có repository khả dụng | Hiển thị trạng thái danh sách rỗng |
| Đồng bộ repository thất bại | Hiển thị trạng thái đồng bộ lỗi kèm lý do, cho phép đồng bộ lại |

## 6. Quy tắc nghiệp vụ

- Chỉ các repository đã được chọn mới thuộc workspace và đi tiếp tới bước phân tích, sinh tài liệu.
- Đồng bộ là thao tác thủ công do người dùng kích hoạt; giao diện luôn hiển thị trạng thái và lỗi gần nhất của lần đồng bộ.
- Frontend không lưu thông tin xác thực GitHub; việc xác thực và truy cập GitHub do GitHub Integration Service đảm nhiệm.
- Lỗi từ backend được hiển thị cho người dùng, không bị bỏ qua im lặng.

## 7. Tiêu chí chấp nhận

- **AC-FE-01.1:** Người dùng chưa kết nối GitHub thấy trạng thái chưa kết nối và nút kết nối; sau khi kết nối thành công, trạng thái chuyển sang đã kết nối.
- **AC-FE-01.2:** Người dùng đã kết nối thấy danh sách repository khả dụng; danh sách rỗng hoặc lỗi tải hiển thị trạng thái tương ứng.
- **AC-FE-01.3:** Người dùng chọn một repository thì repository đó xuất hiện trong danh sách đã chọn của workspace.
- **AC-FE-01.4:** Bấm đồng bộ thủ công thì giao diện hiển thị trạng thái đồng bộ; đồng bộ thất bại hiển thị lỗi và cho phép thử lại.
- **AC-FE-01.5:** Người dùng ngắt kết nối GitHub thì giao diện quay về trạng thái chưa kết nối.

## 8. Kiểm thử

Kiểm thử theo các tiêu chí chấp nhận ở mục 7 trên giao diện web. Jira ghi nhận LD-298 hoàn thành trong Sprint 3 (21/10/2026), có 1 pull request đã merge trên GitHub và 1 build thành công.
