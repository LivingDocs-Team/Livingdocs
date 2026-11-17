# LivingDocs — Đặc tả tái tạo chức năng LD-316: Administration & Dashboard Interface

## 1. Mục tiêu

Triển khai giao diện Administration & Dashboard cho ứng dụng web LivingDocs, tập trung vào sáu nhóm chức năng:
1. Quản lý user, role và permission.
2. Quản trị workspace và repository.
3. Xem cấu hình hệ thống.
4. Theo dõi tình trạng hoạt động và monitoring.
5. Xem audit log và system analytics.
6. Cấu hình notification.

Giao diện được triển khai trong `frontend/src/AdminDashboard.jsx`, sử dụng các API hiện có. Code có chú thích rõ các khu vực mà backend chưa cung cấp API quản trị đầy đủ.

## 2. Thành phần và vị trí mã nguồn

### Frontend

- `frontend/src/AdminDashboard.jsx`: trang Administration, tab navigation và các panel Users, Roles, Workspaces, Configuration, Health, Audit/Analytics, Notifications.
- `frontend/src/NotificationPreferences.jsx`: giao diện notification preferences được nhúng trong tab Notifications.
- `frontend/src/RepositoryManagement.jsx`: giao diện repository/workspace hiện có, gồm chọn workspace, lọc repository, thêm/xóa/chuyển repository và sync.
- `frontend/src/githubApi.js`: helper gọi GitHub Integration API.
- `frontend/src/csrf.js`: tạo CSRF headers cho request thay đổi dữ liệu.
- `frontend/src/errorMessages.js`: chuẩn hóa thông báo lỗi API.
- `frontend/src/App.jsx`: tích hợp điều hướng và hiển thị AdminDashboard theo ứng dụng.

### Backend

- `backend/src/main/java/com/cnpm/backend/controller/AdminUserController.java`: danh sách, xem, sửa user, trạng thái, role và user audit.
- `backend/src/main/java/com/cnpm/backend/controller/AdminRoleController.java`: role và permission.
- `backend/src/main/java/com/cnpm/backend/controller/AdminNotificationPolicyController.java`: notification policies.
- `backend/src/main/java/com/cnpm/backend/controller/AdminSystemAnalyticsController.java`: system analytics.
- `backend/src/main/java/com/cnpm/backend/entity/Role.java`, `Permission.java`, `AdminUserAudit.java`: mô hình role, permission và audit.
- `backend/src/main/java/com/cnpm/backend/repository/RoleRepository.java`, `PermissionRepository.java`, `AdminUserAuditRepository.java`: truy vấn dữ liệu quản trị.
- `backend/src/main/java/com/cnpm/backend/security/SystemAdminAccess.java` và `SecurityConfig.java`: kiểm soát quyền truy cập.
- `backend/src/main/resources/db/notification-policies-postgresql.sql`: schema notification policy.

## 3. Cấu trúc giao diện Administration

`AdminDashboard` có tiêu đề Administration và sáu tab:

| Tab | Component / chức năng |
|---|---|
| Users & roles | `UsersPanel`, `RolesPanel` |
| Workspaces & repositories | `WorkspacesPanel`, `WorkspaceDetail`, `WorkspaceMembers` |
| System configuration | `ConfigPanel` |
| Health & monitoring | `HealthPanel` |
| Audit & analytics | `AuditPanel`, `WorkflowHistory`, `StatTile` |
| Notifications | `NotificationPreferences` |

Tab được quản lý bằng state `tab`; nội dung tương ứng hiển thị trong vùng `tabpanel`.

Helper `adminApi`:
- Gọi API với `credentials: include`.
- Request có body dùng JSON và CSRF headers.
- Timeout request là 60 giây.
- HTTP 401 phát event `livingdocs:unauthenticated`.
- Lỗi được chuyển thành thông báo qua `apiErrorMessage`.

Hook `useApi` quản lý loading, error, data và reload để các panel tải lại dữ liệu sau thao tác.

## 4. User, Role & Permission Management (LD-317)

### 4.1 Users panel

Giao diện hỗ trợ:
- Tìm kiếm theo name, username hoặc email.
- Lọc theo role: `DEVELOPER`, `STAFF`, `MANAGER`, `TECHNICAL_LEAD`, `ADMINISTRATOR`.
- Lọc trạng thái Active/Disabled.
- Hiển thị user, email, role, status và created date.
- Phân trang Previous/Next, page size 10 ở frontend.
- Thay đổi role bằng select.
- Enable/Disable tài khoản.
- Có hộp xác nhận trước khi disable user.
- Hiển thị loading, lỗi và thông báo sau thao tác.

Không cho phép administrator tự đổi role hoặc tự đổi trạng thái tài khoản của chính mình trên UI. Backend cũng từ chối thao tác self-change tương ứng.

### 4.2 Users API

Các endpoint được frontend sử dụng:
- `GET /api/admin/users?page={page}&size=10&search={search}&role={role}&active={active}`
- `PATCH /api/admin/users/{id}/role` với body `{ "role": "..." }`
- `PATCH /api/admin/users/{id}/status` với body `{ "active": true|false }`

Backend hỗ trợ phân trang và lọc. Controller giới hạn `page` không âm và `size` trong khoảng 1–100; kết quả sắp xếp theo `createdAt` giảm dần. Các authority được kiểm tra riêng cho từng thao tác, gồm `USER_VIEW`, `USER_UPDATE`, `USER_DISABLE`, `USER_ASSIGN_ROLE`, `USER_AUDIT_VIEW`.

Backend còn có:
- `GET /api/admin/users/{id}` để lấy chi tiết user.
- `GET /api/admin/users/audit?page={page}&size={size}` để xem audit user.
- `PATCH /api/admin/users/{id}` để cập nhật username, email, first name và last name.
Các API này không đồng nghĩa toàn bộ thao tác đều được thể hiện trong panel hiện tại.

### 4.3 Roles & permissions

`RolesPanel` tải:
- `GET /api/admin/roles`
- `GET /api/admin/permissions`

Mỗi `RoleCard` hiển thị tên role, description và số permission. Administrator có thể mở role, bật/tắt checkbox permission và lưu bằng:

`PUT /api/admin/roles/{roleName}/permissions`

Request body:

```json
{
  "permissionCodes": ["USER_VIEW", "USER_UPDATE"]
}
```

Sau khi lưu thành công, panel tải lại role list. Backend controller bảo vệ thao tác role/permission theo authority quản trị tương ứng.

## 5. Workspace & Repository Administration (LD-318)

### 5.1 Workspace selection

`WorkspacesPanel` tải danh sách bằng `GET /api/managed-workspaces` và tạo thêm personal workspace với ID `ws-{userId}`. Người dùng có thể chọn workspace và xem repository tương ứng.

Giao diện thể hiện một giới hạn quan trọng: danh sách chỉ gồm workspace mà administrator account sở hữu hoặc là thành viên. Workspace của user khác không hiển thị vì backend chưa cung cấp administrator-wide workspace listing.

### 5.2 Repository detail

`WorkspaceDetail` gọi:

`GET /api/workspaces/{workspaceId}/repositories`

Bảng repository hiển thị:
- Full name.
- Default branch.
- Visibility (Private/Public).
- Status.
- Last synced time.
- Nút Sync nếu tài khoản có `OWNER` access.

Sync gọi:

`POST /api/repositories/{repositoryId}/sync`

Khi thành công, giao diện hiển thị thông báo và reload danh sách. Lỗi sync được hiển thị trong panel.

### 5.3 Workspace members

Đối với workspace không phải personal workspace, `WorkspaceMembers` gọi:

`GET /api/managed-workspaces/{workspaceId}/members`

Hiển thị display name/username của các thành viên; nếu không có member thì hiển thị trạng thái rỗng.

### 5.4 RepositoryManagement hiện có

`frontend/src/RepositoryManagement.jsx` bổ sung luồng quản lý repository trong workspace:
- Chọn workspace và kiểm tra quyền OWNER.
- Tải managed workspaces, GitHub connection, repository thuộc workspace và repository khả dụng trên GitHub.
- Tìm kiếm theo full name và lọc visibility.
- Chọn nhiều repository và thêm vào workspace.
- Kết nối GitHub nếu chưa connected.
- Sync repository.
- Xóa repository khỏi workspace.
- Chuyển repository sang workspace khác.
- Hiển thị lỗi riêng cho từng thao tác sync và trạng thái loading.

Các API được gọi gồm `/api/managed-workspaces`, `/api/github/connection`, `/api/github/repos/available`, `/api/workspaces/{id}/repositories`, `POST /api/workspaces/{id}/repositories`, `POST /api/repositories/{id}/sync`, `DELETE /api/repositories/{id}` và `PUT /api/workspaces/{targetId}/repositories/{repositoryId}`.

## 6. System Configuration (LD-319)

`ConfigPanel` hiện là read-only, không phải form chỉnh sửa cấu hình.

Panel hiển thị:
- Frontend API base URL (`VITE_API_BASE_URL` hoặc same-origin/proxy).
- Build mode (`import.meta.env.MODE`).
- Documentation drift severity rules lấy từ `GET /api/documentation/drift/severity-rules`, hiển thị JSON.

Code có ghi rõ rằng việc thay đổi settings cần backend configuration API, nhưng API đó chưa tồn tại trong snapshot LD-316. Vì vậy:
- Không có thao tác lưu cấu hình trong panel này.
- Không được mô tả panel như một màn hình cấu hình có thể chỉnh sửa.
- Phần cấu hình chỉ phản ánh dữ liệu runtime và drift severity rules mà API hiện có trả về.

## 7. System Health & Monitoring (LD-320)

### 7.1 Health checks

`HealthPanel` kiểm tra ba endpoint từ trình duyệt:

| Tên hiển thị | Path |
|---|---|
| Backend API | `/api/auth/csrf` |
| Authentication session | `/api/auth/me` |
| GitHub Integration Service | `/api/github/connection` |

Mỗi probe:
1. Ghi nhận thời điểm bắt đầu bằng `performance.now()`.
2. Gửi fetch với credentials và timeout 10 giây.
3. Nếu HTTP status nhỏ hơn 500, đánh dấu `Up`; từ 500 trở lên hoặc không nhận được response thì đánh dấu `Down`.
4. Hiển thị HTTP status hoặc `No response`.
5. Tính response time theo milliseconds.

Panel hiển thị thời điểm kiểm tra gần nhất và nút `Check again` để chạy lại các probe.

### 7.2 Giới hạn monitoring

Comment trong source nêu rõ AI Service, Code Analyzer và databases chưa có health endpoint có thể truy cập từ browser trong luồng này, nên không được liệt kê. Đây là browser-level checks qua backend, không phải monitoring đầy đủ của toàn bộ hạ tầng.

## 8. Audit Log & System Analytics (LD-321)

### 8.1 Analytics tiles

`AuditPanel` hiển thị các tile:
- Total users.
- Active users.
- Disabled users.
- Số lượng theo từng system role: Developer, Staff, Manager, Technical Lead, Administrator.

Mỗi `StatTile` gọi `GET /api/admin/users?size=1{filter}` và lấy `totalElements` để hiển thị tổng số phù hợp với filter.

### 8.2 Document workflow audit

Panel gọi:

`GET /api/document-workflows/history-accessible?page={page}&size=10`

Bảng hiển thị:
- Document title hoặc document ID.
- Workflow status.
- Owner user ID.
- Updated time.
- Nút History để mở/ẩn audit trail.

`WorkflowHistory` gọi:

`GET /api/document-workflows/{id}/history`

Audit trail hiển thị action, previous/new status, actor role, actor user ID, timestamp và comment nếu có.

### 8.3 Giới hạn audit

UI ghi rõ đây là document review workflows và audit trail có thể truy cập theo quyền document view/review/approval. Các thao tác administrator như đổi role chưa được đưa vào audit panel này. Dù backend có user audit endpoint và `AdminUserAudit` entity, panel Audit hiện tại không gọi endpoint `/api/admin/users/audit`.

Backend còn có `GET /api/admin/system-analytics?from={from}&to={to}`. Endpoint yêu cầu khoảng thời gian hợp lệ, gọi GitHub Integration internal analytics và kết hợp số liệu admin-user audit; nếu GitHub Integration/AI analytics không sẵn sàng thì trả service unavailable. Snapshot UI hiện không gọi endpoint system analytics này; các tile trên UI lấy số lượng user.

## 9. Notification Configuration

Tab Notifications nhúng component `NotificationPreferences` từ `frontend/src/NotificationPreferences.jsx`.

Backend có `AdminNotificationPolicyController` tại `/api/admin/notification-policies`:
- `GET /api/admin/notification-policies`: trả danh sách event và policies.
- `PUT /api/admin/notification-policies/{event}`: tạo/cập nhật recipients và enabled.
- `DELETE /api/admin/notification-policies/{event}`: xóa policy.
- Khi lưu/xóa policy, backend ghi nhận admin user audit event.

Các event enum được định nghĩa trong controller. Request validate recipients; recipients được loại trùng trước khi lưu. Policy lưu event, recipients, enabled và updated timestamp.

Cần phân biệt notification preferences của người dùng trong component frontend với notification policies quản trị ở backend; không mặc định chúng là cùng một API hoặc cùng một loại thiết lập.

## 10. Quyền truy cập và bảo mật

- Admin API sử dụng session/cookie credentials.
- Request thay đổi dữ liệu gửi CSRF headers.
- Backend dùng `@PreAuthorize`/`SystemAdminAccess` và authority cụ thể.
- Người dùng không được tự disable hoặc tự đổi primary role qua AdminUserController.
- Frontend xử lý HTTP 401 bằng event `livingdocs:unauthenticated`, để ứng dụng chuyển về luồng xác thực.
- Không đưa thông tin bí mật vào dashboard hoặc log UI.

## 11. Kiểm thử và tiêu chí chấp nhận

Snapshot có `tests/test_frontend_admin.py` và các backend tests liên quan như:
- `AdminRoleControllerTest.java`
- `AdminUserControllerTest.java`
- `AdminMonitoringPostgresTest.java`
- `AdminUserAuditRetentionTest.java`
- `RoleCatalogInitializerTest.java`

Tiêu chí kiểm tra:
1. Dashboard hiển thị đủ sáu tab.
2. User list hỗ trợ search, role/status filters và pagination.
3. Có thể đổi role hoặc enable/disable user khác; không thể tự thay đổi role/status.
4. Roles và permissions được tải, cập nhật và reload sau khi lưu.
5. Workspace/repository hiển thị theo quyền và phạm vi endpoint hiện có.
6. Repository owner có thể sync repository và thấy kết quả/lỗi.
7. System configuration hiển thị runtime values và drift severity rules ở chế độ read-only.
8. Health panel chạy ba probe đã khai báo, hiển thị trạng thái, response time và thời điểm kiểm tra.
9. Audit panel phân trang workflow history và mở được audit trail của workflow.
10. Analytics tiles hiển thị tổng user theo trạng thái/role.
11. Notification preferences được hiển thị; notification policy API hỗ trợ list/upsert/delete.
12. Loading, error, empty state và success notice được hiển thị phù hợp.
13. API được bảo vệ bằng session, CSRF và backend authorization.

## 12. Các giới hạn cần giữ nguyên khi tái tạo

- Workspace administration chưa phải global administrator view; chỉ hiển thị workspace account hiện tại sở hữu/tham gia.
- System Configuration chỉ read-only; backend configuration API không có trong snapshot LD-316.
- Health monitoring chỉ kiểm tra Backend API, Authentication session và GitHub Integration Service; không bao gồm AI Service, Code Analyzer hoặc database.
- Audit UI tập trung vào document workflow history; admin role changes chưa được hiển thị trong audit panel.
- Analytics tiles là thống kê user theo filter, không phải toàn bộ system analytics endpoint.
- Backend có system analytics endpoint riêng nhưng frontend snapshot không gọi endpoint đó.
- NotificationPreferences là component UI hiện có; backend notification policies là API quản trị riêng.
- Không tự mở rộng các phần còn thiếu thành tính năng đã hoàn thiện.

## 13. Hướng dẫn cho AI tái tạo code

- Giữ cấu trúc tab và tách panel theo nhóm nghiệp vụ trong `AdminDashboard.jsx`.
- Dùng `adminApi`/`useApi` để thống nhất credentials, CSRF, timeout, loading và error handling.
- Giữ đúng API paths, query parameters, request bodies và quyền truy cập được mô tả.
- Không cho phép administrator tự đổi role hoặc trạng thái tài khoản của mình.
- Giữ workspace visibility theo quyền hiện có; không giả lập danh sách workspace toàn hệ thống.
- Giữ ConfigPanel read-only cho đến khi có backend configuration API.
- Chỉ hiển thị ba health probes được triển khai; không tự suy ra health của các service khác.
- Phân biệt document workflow audit, user audit và system analytics.
- Phân biệt notification preferences của user với notification policies quản trị.
- Khi bổ sung backend API mới, cập nhật đặc tả và test thay vì giả định endpoint đã tồn tại.
