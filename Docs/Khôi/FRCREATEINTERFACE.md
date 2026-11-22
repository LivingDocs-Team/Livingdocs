# FR-FE-RBAC Phân quyền theo vai trò, screen flow riêng cho từng vai trò và giao diện mới

| Mục | Nội dung |
|---|---|
| Epic Jira | Không gắn Jira |
| Task Jira | Không gắn Jira (nhánh `Create_authorize_screen_flow`, pull request #153) |
| Task đã làm | Phân quyền theo ma trận Screen × Role, screen flow của 5 vai trò, giao diện tối mới, kiểm tra quyền ở backend |
| Người thực hiện | Khôi Nguyễn Hữu Đăng |
| Thành phần | Frontend LivingDocs Web (menu, route guard, màn hình công khai, giao diện), Backend (BFF kiểm tra quyền), bộ kiểm thử và CI |
| Tác nhân | Developer, Staff, Manager, Technical Lead, Administrator (5 vai trò), người dùng chưa đăng nhập |

## 1. Mô tả

Hệ thống phân quyền theo năm vai trò. Mỗi vai trò chỉ thấy menu và các màn hình của riêng mình (screen flow), chỉ thấy các nút thao tác mà ma trận quyền cho phép, và backend từ chối các yêu cầu API ngoài quyền. Người dùng chưa đăng nhập chỉ thấy ba màn hình công khai: Home, Login và Register. Giao diện được thiết kế lại theo phong cách tối, có nền và hiệu ứng chuyển động, kích thước hiển thị tăng 50%.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-FE-RBAC.1 | Có ma trận quyền Screen × Role gồm 23 dòng và 5 vai trò (Developer, Staff, Manager, Technical Lead, Administrator) với các hành động C (tạo), R (đọc), U (sửa), D (xóa), A (duyệt hoặc từ chối), E (xuất); vai trò ADMIN cũ được coi là Administrator. |
| FR-FE-RBAC.2 | Mỗi vai trò có một cây screen flow riêng (module, màn hình, màn hình con); menu, breadcrumb và đường dẫn đều lấy từ cây này. Flow của Developer, Staff, Manager theo flow chính thức của nhóm; flow của Technical Lead và Administrator là flow tạm, dựng từ các dòng ma trận mà vai trò đó có quyền. |
| FR-FE-RBAC.3 | Trước khi đăng nhập chỉ có Home, Login và Register; Register chỉ tạo tài khoản Developer. Vào đường dẫn nội bộ khi chưa đăng nhập thì chuyển về Login; sau khi đăng nhập mở đúng trang đã yêu cầu nếu vai trò được phép, nếu không thì mở trang chủ của vai trò. |
| FR-FE-RBAC.4 | Sau khi đăng nhập, người dùng chỉ vào được các màn hình trong flow của mình: đường dẫn thuộc vai trò khác hiển thị trang 403, đường dẫn không tồn tại chuyển về trang chủ của vai trò, tài khoản không có vai trò hợp lệ hiển thị "No role assigned". |
| FR-FE-RBAC.5 | Các nút thao tác chỉ hiện khi ma trận cho phép, ví dụ Generate documentation, Manage templates, Submit for review, Restore this version, nhận và duyệt tài liệu, Export Markdown (chỉ Developer), khung Staff Review Queue trong trang Documentation (chỉ vai trò có quyền xử lý hàng đợi). |
| FR-FE-RBAC.6 | Màn hình có trong flow nhưng chưa xây dựng hiển thị trang "Chưa triển khai" đúng vị trí trong menu và breadcrumb, mục menu hiển thị mờ. |
| FR-FE-RBAC.7 | Menu chỉ liệt kê các màn hình chính, tên nhóm in đậm; màn hình con mở bằng đường dẫn và breadcrumb, mục cha vẫn sáng khi đang ở màn hình con. Staff › Document Editor là nút ở đầu trang Review Queue; Profile & Settings hiển thị hai ô (Profile, Notification Preferences). Menu Developer không còn mục Generation Request (Generated Documents mở cùng trang). |
| FR-FE-RBAC.8 | Gỡ khỏi giao diện web cho mọi vai trò: Dashboard (#4), Auto-Update (#14, #15), Drift Alerts & Review (#16, gồm trang Documentation Drift) và Collections (#21); các quyền không có màn hình trong flow của vai trò bị bỏ khỏi ma trận, và quyền Export (#8) thêm cho Developer. |
| FR-FE-RBAC.9 | Backend kiểm tra quyền theo cùng ma trận tại Backend (BFF): mỗi route của GitHub Integration cần ít nhất một cặp (dòng ma trận, hành động) mà vai trò có; route chưa có quy tắc bị từ chối; các route drift bị từ chối cho mọi vai trò. |
| FR-FE-RBAC.10 | Giao diện tối mới: biến màu thiết kế, màn hình công khai gồm hero và thẻ đăng nhập, nền chuyển động, hiệu ứng khi rê chuột lên ô chức năng, kích thước hiển thị tăng 50%; hiệu ứng tắt khi hệ điều hành bật giảm chuyển động. |
| FR-FE-RBAC.11 | Có 5 tài khoản test (mỗi vai trò một tài khoản) và script tạo chúng qua API có sẵn. |
| FR-FE-RBAC.12 | Sửa lỗi phát hiện trong quá trình làm: `GET /api/admin/users` trả 500 trên PostgreSQL khi không có tham số `search`; ghim các job CI dùng Playwright hoặc build Docker vào Ubuntu 24.04; làm các kiểm thử giao diện chờ trang tải xong thay vì đọc một lần. |

## 3. Giao diện

| Màn hình / thành phần | Nội dung hiển thị | Yêu cầu |
|---|---|---|
| Màn hình công khai | Header Home, Login, Register; hero và thẻ đăng nhập, đăng ký hoặc chào mừng | FR-FE-RBAC.3, 10 |
| Khung ứng dụng | Thanh trên có email, vai trò, nút Logout; menu theo vai trò; breadcrumb | FR-FE-RBAC.2, 4, 6, 7 |
| Trang 403, "No role assigned", "Chưa triển khai" | Thông báo tương ứng kèm đường về trang chủ của vai trò | FR-FE-RBAC.4, 6 |
| Nút theo quyền | Các nút bọc bởi `<Can screen action>` | FR-FE-RBAC.5 |
| Backend (BFF) | `ScreenPermissions` (ma trận), `ApiRoutePermissions` (quy tắc route) | FR-FE-RBAC.9 |
| Tài liệu và công cụ | `Docs/rbac-screen-flow.md`, `scripts/seed_rbac_test_accounts.py`, `scripts/rbac-test-accounts.example.json` | FR-FE-RBAC.11 |

Frontend định tuyến bằng đường dẫn dạng `#/duong-dan` (không thêm thư viện), cấu hình quyền và flow nằm trong `frontend/src/rbac/`. Thêm màn hình hoặc quyền mới chỉ cần sửa cấu hình, không sửa logic menu hay route guard (hướng dẫn trong `Docs/rbac-screen-flow.md`).

## 4. Luồng chính

1. Người dùng chưa đăng nhập mở web và thấy Home, Login, Register.
2. Người dùng đăng nhập; giao diện đọc vai trò từ backend và chuyển tới trang chủ của vai trò (Developer: GitHub Connection, Staff: Review Queue, Manager: Approval Queue, Technical Lead: Knowledge Search, Administrator: Profile).
3. Menu chỉ hiển thị các màn hình của vai trò; các nút thao tác chỉ hiện khi vai trò có quyền.
4. Khi người dùng gửi yêu cầu API, Backend (BFF) kiểm tra vai trò theo ma trận trước khi chuyển tiếp tới GitHub Integration Service.
5. Người dùng đăng xuất bằng nút Logout và quay về màn hình Home.

## 5. Luồng lỗi

| Trường hợp | Kết quả hiển thị |
|---|---|
| Vào đường dẫn nội bộ khi chưa đăng nhập | Chuyển về Login; sau khi đăng nhập mở lại đúng trang nếu được phép |
| Vào đường dẫn của vai trò khác | Trang 403 "Access denied" kèm nút về trang chủ của vai trò |
| Vào đường dẫn không tồn tại (gồm các đường dẫn đã gỡ) | Chuyển về trang chủ của vai trò |
| Tài khoản có vai trò không hợp lệ | "No role assigned", chỉ có nút Logout |
| Gọi API ngoài quyền | Backend trả 403 và không gọi tới GitHub Integration Service |
| Gọi route chưa có quy tắc quyền hoặc route drift | Backend trả 403 (từ chối mặc định) |
| Phiên hết hạn | Quay về Login kèm thông báo phiên hết hạn |

## 6. Quy tắc nghiệp vụ

- Ẩn nút và menu ở frontend chỉ để thuận tiện cho người dùng; backend mới là nơi từ chối yêu cầu. Ma trận là giới hạn trên: GitHub Integration Service vẫn kiểm tra thêm quyền sở hữu tài liệu, quyền `DOCUMENT_*` và thành viên workspace.
- Ma trận tồn tại ở hai nơi (`frontend/src/rbac/permissions.js` và `ScreenPermissions.java`); một kiểm thử so sánh hai bản và thất bại khi chúng khác nhau.
- Chỉ Administrator gán vai trò; Register luôn tạo Developer.
- Chưa theo ma trận một cách có chủ ý: workspace tự quản (`/api/managed-workspaces`) và hồ sơ (`/api/profile`) vẫn kiểm tra theo chủ sở hữu và thành viên, vì áp dụng dòng #25 sẽ làm hỏng việc chọn workspace của Developer trong trang Repository.
- Technical Lead và Administrator dùng flow tạm (có đánh dấu `provisional` trong mã và nhãn "Provisional flow" trên giao diện); các quyền đọc của Technical Lead được BFF cho phép nhưng GitHub Integration Service chưa cấp quyền `DOCUMENT_*` tương ứng.
- Các điểm của ma trận chưa khớp hoàn toàn với đặc tả gốc đã được nhóm quyết định và ghi trong `Docs/rbac-screen-flow.md` (mục 5).

## 7. Tiêu chí chấp nhận

- **AC-FE-RBAC.1:** Chưa đăng nhập chỉ thấy Home, Login, Register; vào đường dẫn nội bộ bị chuyển về Login.
- **AC-FE-RBAC.2:** Mỗi vai trò đăng nhập thấy đúng menu theo flow của vai trò, không thừa không thiếu, và vào đúng trang chủ của vai trò.
- **AC-FE-RBAC.3:** Gõ đường dẫn của vai trò khác bị chặn (403); các nút thao tác chỉ hiện khi ma trận cho phép.
- **AC-FE-RBAC.4:** Màn hình chưa xây dựng hiển thị trang "Chưa triển khai" đúng vị trí trong flow.
- **AC-FE-RBAC.5:** Gọi API ngoài quyền nhận 403 từ Backend; route drift và route chưa có quy tắc bị từ chối.
- **AC-FE-RBAC.6:** Thêm màn hình mới chỉ cần sửa cấu hình quyền và flow.
- **AC-FE-RBAC.7:** Giao diện hiển thị theo phong cách mới, hiệu ứng tắt khi bật giảm chuyển động, nội dung lớn hơn 50% và không bị tràn ngang.

## 8. Kiểm thử

Kiểm thử gồm `npm test` (56 kiểm thử cho ma trận, flow và route guard), `tests/test_rbac_screen_flow.py` và các kịch bản Playwright cũ đã cập nhật theo điều hướng mới (168 đạt, 1 xfail; 2 kiểm thử không chạy được trên máy phát triển vì thiếu thư viện và tham số môi trường), và 346 kiểm thử Backend (gồm 249 trường hợp vai trò × route, kiểm thử so khớp ma trận Java với `permissions.js`, kiểm thử BFF và chuỗi bảo mật, `UserRepositoryPostgresTest` trên PostgreSQL). Các job CI Frontend E2E được chạy lại với CPU chậm gấp 6 lần để tìm lỗi phụ thuộc thời gian. Đã đăng nhập thử 5 tài khoản test trên ngăn xếp Docker thật và gọi API theo từng vai trò. Mã nguồn nằm trong pull request #153 trên GitHub.
