# FR-BE7-316 Giao diện quản trị hệ thống và bảng điều khiển (Administration & Dashboard)

| Mục | Nội dung |
|---|---|
| Epic Jira | LD-286 Frontend Implementation |
| Task Jira | LD-316 [Administration & Dashboard Interface] Implement Administration & Dashboard Interface |
| Task đã làm | LD-317 (Implement User & Role Management UI), LD-318 (Implement Workspace & Repository Administration UI), LD-319 (Implement System Configuration UI), LD-320 (Implement System Monitoring & Health UI), LD-321 (Implement Audit, Analytics & Notification UI) |
| Người thực hiện | Nguyễn Lê Minh |
| Nhánh / PR & Trạng thái | Nhánh tính năng `LD-316` (mô tả theo snapshot nhánh tính năng; đối chiếu trạng thái merge trên `main` trước khi nghiệm thu) |
| Thành phần | Frontend LivingDocs Web (`frontend/src/AdminDashboard.jsx`, `frontend/src/rbac/AppShell.jsx`, `frontend/src/rbac/flows/administrator.flow.js`, `frontend/src/rbac/permissions.js`); Backend BFF (`AdminUserController`, `AdminRoleController`, `AdminWorkspaceController`, `AdminSystemConfigController`, `AdminHealthController`, `AdminSystemAnalyticsController`, `AdminNotificationPolicyController`) |
| Tác nhân | Quản trị viên hệ thống (`ADMINISTRATOR`), Backend BFF (cổng 8080), GitHub Integration Service & AI Service (truy vấn gián tiếp qua BFF) |

## 1. Mô tả

Hệ thống cung cấp giao diện quản trị tập trung (`AdminDashboard`) dành riêng cho vai trò Quản trị viên (`ADMINISTRATOR`) trên ứng dụng web LivingDocs. Thông qua thanh điều hướng phân quyền (`AppShell`), quản trị viên truy cập 6 phân khu chức năng trên một bảng điều khiển thống nhất: quản lý người dùng và phân quyền vai trò (`Users & roles`), quản trị danh mục workspace và repository toàn hệ thống (`Workspaces & repositories`), cấu hình tham số vận hành (`System configuration`), giám sát trạng thái sức khỏe các dịch vụ (`Health & monitoring`), theo dõi thống kê hoạt động và nhật ký kiểm toán (`Audit & analytics`), và thiết lập chính sách thông báo theo sự kiện (`Notifications`).

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-FE-04.1 | (LD-316) Chỉ hiển thị các mục điều hướng quản trị trên thanh menu bên trái (`AppShell`) cho người dùng có vai trò `ADMINISTRATOR` (`/admin/users`, `/admin/workspaces`, `/admin/configuration`, `/admin/monitoring`, `/admin/notification-policies`); người dùng thuộc vai trò khác truy cập trực tiếp qua URL bị chặn bởi route guard (`Access denied`). |
| FR-FE-04.2 | (LD-316) Mở đúng tab chức năng tương ứng khi người dùng chọn từng mục trên menu quản trị (`user-management` → `Users & roles`, `workspace-administration` → `Workspaces & repositories`, `system-configuration` → `System configuration`, `monitoring` → `Health & monitoring`, `notification-policies` → `Notifications`) và cho phép chuyển đổi qua lại giữa tất cả 6 tab ngay trên trang `Administration`. |
| FR-FE-04.3 | (LD-317) Hiển thị danh sách tài khoản người dùng có phân trang (10 người dùng/trang), hỗ trợ tìm kiếm theo tên, username hoặc email và lọc theo vai trò (`DEVELOPER`, `STAFF`, `MANAGER`, `TECHNICAL_LEAD`, `ADMINISTRATOR`) hoặc trạng thái hoạt động (`Active`, `Disabled`). |
| FR-FE-04.4 | (LD-317) Cho phép thay đổi vai trò chính của người dùng và khóa (`Disable`, có hộp thoại xác nhận) hoặc mở khóa (`Enable`) tài khoản người dùng khác; vô hiệu hóa nút đổi vai trò và nút khóa tài khoản đối với chính tài khoản quản trị viên đang đăng nhập. |
| FR-FE-04.5 | (LD-317) Hiển thị danh mục các vai trò hệ thống cùng số lượng và danh sách mã quyền (`permissions`) được gán; cho phép đánh dấu chọn/bỏ chọn từng quyền và lưu cấu hình phân quyền cho vai trò. |
| FR-FE-04.6 | (LD-318) Hiển thị danh sách toàn bộ workspace được quản lý trên hệ thống (kèm email/username chủ sở hữu và số lượng thành viên) cùng workspace cá nhân (`ws-<userId>`), hỗ trợ lọc nhanh theo tên workspace hoặc thông tin chủ sở hữu. |
| FR-FE-04.7 | (LD-318) Cho phép chỉnh sửa tên (`name`, 1–100 ký tự) và mô tả (`description`, tối đa 1.000 ký tự) của workspace được quản lý. |
| FR-FE-04.8 | (LD-318) Hiển thị danh sách repository đã kết nối của workspace đang chọn (tên repository, nhánh mặc định, chế độ hiển thị `Public`/`Private`, trạng thái, thời điểm đồng bộ gần nhất) và cho phép kích hoạt đồng bộ thủ công (`Sync`) hoặc gỡ repository khỏi workspace (`Remove`, có hộp thoại xác nhận). |
| FR-FE-04.9 | (LD-318) Hiển thị danh sách thành viên hiện tại của workspace được quản lý; cho phép chọn người dùng đang hoạt động (`active=true`) chưa thuộc workspace (và không phải chủ sở hữu workspace) để thêm vào hoặc gỡ thành viên khỏi workspace. |
| FR-FE-04.10 | (LD-319) Hiển thị và cho phép cập nhật thời gian lưu trữ nhật ký kiểm toán (`auditRetentionDays`, số nguyên từ `0` đến `3650`, trong đó `0` là lưu vĩnh viễn) cùng lịch dọn dẹp tự động (`0 0 0 * * * UTC`). |
| FR-FE-04.11 | (LD-319) Hiển thị thông tin cấu hình bảo mật và tích hợp runtime ở chế độ chỉ đọc: `Frontend URL`, `Session cookie SameSite`, `Session cookie Secure`, trạng thái cấu hình `GitHub OAuth2 client`, `GitHub Integration URL`, trạng thái `Internal BFF secret`, thời gian chờ kết nối/đọc (`connectTimeoutSeconds`, `readTimeoutSeconds`) và `API base URL`. |
| FR-FE-04.12 | (LD-319) Hiển thị bảng quy tắc mức độ nghiêm trọng của sai lệch tài liệu (`Documentation drift severity rules`: cấp độ, dải điểm, ý nghĩa, hành động khuyến nghị) và cho phép mở rộng xem cấu trúc JSON gốc. |
| FR-FE-04.13 | (LD-320) Kiểm tra và hiển thị tình trạng sức khỏe (`Up`, `Down`, `Auth error`) của các thành phần dịch vụ qua Backend BFF (`Backend API`, `Backend Database`, `GitHub Integration Service`, cùng các thành phần con `AI Service`, `Code Analyzer` nếu có), kèm mã HTTP, thời gian phản hồi (ms), chi tiết trạng thái và thời điểm kiểm tra gần nhất. |
| FR-FE-04.14 | (LD-320) Cho phép kiểm tra lại sức khỏe hệ thống thủ công (`Check again`) và phân biệt rõ lỗi xác thực/phân quyền (`401`/`403`) với lỗi dịch vụ ngừng hoạt động hoặc mất kết nối. |
| FR-FE-04.15 | (LD-321) Hiển thị thống kê hoạt động hệ thống theo khoảng thời gian chọn sẵn (`Last 24 hours`, `Last 7 days`, `Last 30 days`) và nút làm mới (`Refresh metrics`): số repository đã kết nối, số tài liệu đã tạo, số job AI hoàn thành/thất bại (kèm mốc quan sát tiến trình hiện tại `observedSince`), và số lượng sự kiện audit theo nhóm (`Administration`, `Document workflow`, `Document version`). |
| FR-FE-04.16 | (LD-321) Hiển thị nhật ký kiểm toán quản trị (`Administrative audit log`) có phân trang (20 bản ghi/trang) gồm thời gian xảy ra, hành động (`action`), người thực hiện (`actorId`), đối tượng tác động (`User #id`, `Role`, hoặc `Event`) và giá trị trước/sau thay đổi. |
| FR-FE-04.17 | (LD-321) Hiển thị danh sách các sự kiện hỗ trợ thông báo (`REPOSITORY_CONNECTED`, `DOCUMENT_SUBMITTED`, `DOCUMENT_APPROVED`, `DOCUMENT_REJECTED`, `AI_JOB_COMPLETED`, `AI_JOB_FAILED`) kèm nhãn trạng thái (`Enabled`, `Disabled`, `Not configured`). |
| FR-FE-04.18 | (LD-321) Cho phép nhập danh sách email người nhận (phân tách bằng dấu phẩy, chấm phẩy hoặc khoảng trắng), bật/tắt trạng thái kích hoạt và lưu (`Save policy`) hoặc xóa (`Delete policy`) chính sách thông báo cho từng sự kiện. |

## 3. Giao diện và API tích hợp

### Thành phần giao diện (`AdminDashboard.jsx`)

| Tab / Thành phần | Nội dung hiển thị và thao tác | Yêu cầu |
|---|---|---|
| `Users & roles` (`UsersPanel`, `RolesPanel`) | Thanh tìm kiếm & lọc user, bảng tài khoản phân trang, dropdown đổi vai trò, nút khóa/mở khóa, danh sách thẻ vai trò kèm checkbox phân quyền và nút lưu | FR-FE-04.3 – 04.5 |
| `Workspaces & repositories` (`WorkspacesPanel`, `WorkspaceDetail`, `WorkspaceMembersAdmin`) | Ô lọc & dropdown chọn workspace, form sửa tên/mô tả workspace, bảng repository kèm nút `Sync` và `Remove`, danh sách thành viên kèm form thêm/gỡ | FR-FE-04.6 – 04.9 |
| `System configuration` (`ConfigPanel`) | Form chỉnh sửa `auditRetentionDays`, danh sách thông số bảo mật/tích hợp runtime, bảng `Documentation drift severity rules` và khối JSON chi tiết | FR-FE-04.10 – 04.12 |
| `Health & monitoring` (`HealthPanel`) | Nút `Check again`, thời điểm kiểm tra, bảng trạng thái từng dịch vụ (`Status`, `HTTP`, `Response`, `Detail`) | FR-FE-04.13 – 04.14 |
| `Audit & analytics` (`SystemAnalyticsSection`, `AuditPanel`) | Bộ chọn khoảng thời gian (`24h`, `7d`, `30d`), nút `Refresh metrics`, lưới thẻ số liệu thống kê, bảng nhật ký kiểm toán phân trang | FR-FE-04.15 – 04.16 |
| `Notifications` (`NotificationPoliciesPanel`, `NotificationPolicyRow`) | Danh sách sự kiện hệ thống dạng accordion, ô nhập danh sách email người nhận, checkbox `Enabled`, nút `Save policy` và `Delete policy` | FR-FE-04.17 – 04.18 |

### Endpoint Backend BFF sử dụng

| Method | Endpoint | Chức năng | Yêu cầu |
|---|---|---|---|
| `GET` | `/api/admin/users` | Liệt kê, tìm kiếm và lọc danh sách tài khoản có phân trang | FR-FE-04.3 |
| `PATCH` | `/api/admin/users/{id}/role` | Cập nhật vai trò chính của tài khoản | FR-FE-04.4 |
| `PATCH` | `/api/admin/users/{id}/status` | Khóa hoặc mở khóa tài khoản (`active: true/false`) | FR-FE-04.4 |
| `GET` | `/api/admin/roles`, `/api/admin/permissions` | Lấy danh sách vai trò và danh mục mã quyền | FR-FE-04.5 |
| `PUT` | `/api/admin/roles/{name}/permissions` | Cập nhật tập mã quyền gắn với vai trò | FR-FE-04.5 |
| `GET` | `/api/admin/workspaces` | Lấy danh sách toàn bộ workspace được quản lý trên hệ thống | FR-FE-04.6 |
| `PUT` | `/api/admin/workspaces/{workspaceId}` | Cập nhật tên và mô tả workspace | FR-FE-04.7 |
| `GET` / `POST` / `DELETE` | `/api/admin/workspaces/{workspaceId}/members[/{userId}]` | Xem, thêm và gỡ thành viên khỏi workspace | FR-FE-04.9 |
| `GET` | `/api/workspaces/{workspaceId}/repositories` | Lấy danh sách repository đã kết nối của workspace | FR-FE-04.8 |
| `POST` / `DELETE` | `/api/repositories/{id}/sync`, `/api/repositories/{id}` | Đồng bộ thủ công hoặc gỡ repository khỏi workspace | FR-FE-04.8 |
| `GET` / `PATCH` | `/api/admin/system-config` | Đọc cấu hình runtime và cập nhật `auditRetentionDays` | FR-FE-04.10 – 04.11 |
| `GET` | `/api/documentation/drift/severity-rules` | Lấy danh mục quy tắc mức độ nghiêm trọng của drift | FR-FE-04.12 |
| `GET` | `/api/admin/health` | Kiểm tra tình trạng hoạt động tổng hợp của các dịch vụ | FR-FE-04.13 – 04.14 |
| `GET` | `/api/admin/system-analytics` | Lấy thống kê hoạt động hệ thống trong khoảng `[from, to)` | FR-FE-04.15 |
| `GET` | `/api/admin/users/audit` | Lấy danh sách nhật ký kiểm toán quản trị có phân trang | FR-FE-04.16 |
| `GET` / `PUT` / `DELETE` | `/api/admin/notification-policies[/{event}]` | Xem, tạo/cập nhật và xóa chính sách thông báo theo sự kiện | FR-FE-04.17 – 04.18 |

## 4. Luồng chính

1. Người dùng đăng nhập bằng tài khoản có vai trò `ADMINISTRATOR`; `AppShell` hiển thị các mục quản trị trên sidebar.
2. Quản trị viên chọn một mục quản trị trên menu (hoặc chuyển trực tiếp giữa các tab trên trang `Administration`).
3. Component của tab tương ứng gọi API Backend BFF qua `adminApi` / `probeHealth` kèm cookie phiên (`credentials: 'include'`) và hiển thị trạng thái `Loading…` cho đến khi nhận dữ liệu.
4. Khi thực hiện thao tác thay đổi dữ liệu (`POST`, `PUT`, `PATCH`, `DELETE`), frontend tự động lấy token CSRF (`/api/auth/csrf` → header `X-XSRF-TOKEN`), gửi yêu cầu, hiển thị thông báo thành công và tải lại dữ liệu mới nhất.

## 5. Luồng lỗi

| Trường hợp | HTTP / Trạng thái | Kết quả hiển thị |
|---|---|---|
| Phiên đăng nhập hết hạn hoặc chưa xác thực | `401` | Phát sự kiện `livingdocs:unauthenticated` để chuyển về màn hình đăng nhập; trên tab `Health & monitoring` hiển thị nhãn `Auth error` và thông báo yêu cầu đăng nhập |
| Tài khoản không có quyền `ADMINISTRATOR` | `403` | Route guard hiển thị màn hình `Access denied`; nếu gọi API trả `403` thì hiển thị thông báo từ chối truy cập |
| Dữ liệu đầu vào không hợp lệ (số ngày lưu trữ ngoài `0..3650`, danh sách email rỗng/sai định dạng, tên workspace rỗng) | `400` / Validate client | Hiển thị thông báo lỗi cụ thể ngay tại khu vực thao tác (`role="alert"`), không ghi đè dữ liệu hiện tại |
| Tự đổi vai trò hoặc khóa chính tài khoản quản trị đang đăng nhập | `403` (và khóa trên UI) | Các điều khiển đổi vai trò và khóa của dòng tài khoản hiện tại bị `disabled`; backend từ chối nếu gửi trực tiếp |
| Dịch vụ phụ thuộc (GitHub Integration, AI Service, Database) ngừng hoạt động hoặc mất kết nối | `503` / Timeout / Lỗi mạng | Tab `Health & monitoring` đánh dấu dịch vụ tương ứng là `Down` kèm mã HTTP và chi tiết lỗi; tab `Audit & analytics` hiển thị thông báo lỗi truy vấn thay vì hiển thị số `0` giả |

## 6. Quy tắc nghiệp vụ

- Mọi request từ trình duyệt chỉ đi qua Backend BFF (`/api/...`), không gọi trực tiếp sang GitHub Integration Service (`:8082`), AI Service (`:8001`) hay Code Analyzer (`:8000`).
- Tất cả các phương thức thay đổi dữ liệu (`POST`, `PUT`, `PATCH`, `DELETE`) bắt buộc gửi kèm header `X-XSRF-TOKEN` và cookie phiên.
- Phân quyền hiển thị trên giao diện (`administrator.flow.js`, `permissions.js`) chỉ phục vụ trải nghiệm người dùng; quyền thực thi thực tế được Backend kiểm soát qua `@PreAuthorize` và `SystemAdminAccess`.
- Quản trị viên không thể tự thay đổi vai trò chính hoặc tự khóa tài khoản của chính mình, và không thể gỡ bỏ các quyền cốt lõi của vai trò `ADMINISTRATOR` (`USER_VIEW`, `USER_UPDATE`, `USER_DISABLE`, `USER_ASSIGN_ROLE`, `USER_AUDIT_VIEW`, `ROLE_VIEW`, `PERMISSION_VIEW`, `ROLE_ASSIGN_PERMISSION`, `DOCUMENT_REASSIGN`).
- Chính sách thông báo yêu cầu từ 1 đến 50 địa chỉ email hợp lệ khi lưu (backend tự động loại bỏ email trùng lặp); danh sách email được tách tự động qua dấu phẩy, chấm phẩy hoặc khoảng trắng, và mọi thao tác lưu/xóa đều ghi nhận vào `admin_user_audit`.

## 7. Tiêu chí chấp nhận

- **AC-FE-04.1:** Tài khoản `ADMINISTRATOR` nhìn thấy đầy đủ 5 mục quản trị trên sidebar và mở đúng tab tương ứng trên trang `Administration`; tài khoản `DEVELOPER` không thấy các mục này và bị từ chối (`Access denied`) khi truy cập trực tiếp `#/admin/users`.
- **AC-FE-04.2:** Quản trị viên tìm kiếm/lọc được danh sách người dùng, đổi vai trò của người dùng khác sang `STAFF`, khóa/mở khóa tài khoản khác, trong khi các điều khiển tương ứng trên chính dòng tài khoản của quản trị viên bị vô hiệu hóa.
- **AC-FE-04.3:** Quản trị viên mở rộng một vai trò (ví dụ `DEVELOPER`), chọn thêm quyền và bấm `Save permissions` thì hệ thống gọi `PUT /api/admin/roles/{name}/permissions` và hiển thị thông báo `Permissions saved.`.
- **AC-FE-04.4:** Quản trị viên xem được danh sách workspace toàn hệ thống, cập nhật thông tin workspace, quản lý thành viên, xem danh sách repository kết nối và kích hoạt đồng bộ thủ công (`Sync`).
- **AC-FE-04.5:** Quản trị viên cập nhật `auditRetentionDays` trong khoảng `0..3650`, xem thông số runtime và bảng quy tắc mức độ nghiêm trọng của documentation drift.
- **AC-FE-04.6:** Tab `Health & monitoring` hiển thị đúng trạng thái `Up`, `Down` hoặc `Auth error` cho từng dịch vụ phản hồi từ `/api/admin/health` và cho phép kiểm tra lại qua nút `Check again`.
- **AC-FE-04.7:** Quản trị viên xem được số liệu thống kê theo khoảng thời gian, tra cứu nhật ký kiểm toán quản trị phân trang và cấu hình (lưu/xóa) chính sách thông báo email cho từng sự kiện hệ thống.

## 8. Kiểm thử

- **Kiểm thử E2E giao diện (Playwright):** `tests/test_frontend_admin.py` (kiểm tra phân quyền hiển thị menu, điều hướng 5 mục quản trị sang từng tab, lọc/đổi vai trò/khóa tài khoản, chỉnh sửa quyền vai trò, quản trị workspace & đồng bộ repository, kiểm tra sức khỏe dịch vụ với các trạng thái `403`/`DEGRADED`/`UP`, cấu hình `auditRetentionDays`, thống kê hệ thống, audit log và chính sách thông báo) và `tests/test_rbac_screen_flow.py`.
- **Kiểm thử tĩnh & đóng gói Frontend:** `cd frontend && npm run lint && npm run build`.
- **Kiểm thử Backend liên quan:** `backend/src/main/tests/java/com/cnpm/backend/AdminUserControllerTest.java`, `AdminRoleControllerTest.java`, `AdminMonitoringPostgresTest.java`, `WorkspaceControllerTest.java`, `security/BackendSecurityFilterChainTest.java`.