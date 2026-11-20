# FR-WORKSPACE — Quản trị workspace và repository

| Mục | Nội dung |
|---|---|
| Story / Task Jira | [LD-267](https://ut-team-lvdocs.atlassian.net/browse/LD-267), [LD-268](https://ut-team-lvdocs.atlassian.net/browse/LD-268), [LD-269](https://ut-team-lvdocs.atlassian.net/browse/LD-269), [LD-270](https://ut-team-lvdocs.atlassian.net/browse/LD-270), [LD-271](https://ut-team-lvdocs.atlassian.net/browse/LD-271), [LD-272](https://ut-team-lvdocs.atlassian.net/browse/LD-272) |
| Trạng thái Jira (18/11/2026) | Done |
| Người thực hiện | Nhân Nguyễn ([nhanndt750402-max](https://github.com/nhanndt750402-max), đối chiếu theo PR và commit) |
| Thành phần | Backend, GitHub Integration, Frontend |
| Tác nhân | OWNER, MEMBER |
| Phụ thuộc | [FR5 — RBAC](FR5.md), [luồng repository dùng chung](../Đăng/FR2.md) |
| Mục tiêu | Quản lý thành viên và vị trí của repository trong workspace. |

## 1. Mô tả

Workspace tập hợp repository và thành viên. Quyền theo membership chi phối thao tác trên workspace và việc chuyển repository.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-WORKSPACE.1 | Tạo, liệt kê, xem và sửa workspace trong phạm vi quyền. |
| FR-WORKSPACE.2 | Quản lý thành viên theo vai trò OWNER/MEMBER. |
| FR-WORKSPACE.3 | Kiểm tra liên kết repository trùng và kiểm tra quyền khi chuyển repository giữa workspace. |

## 3. API và luồng xử lý

Backend dùng `/api/managed-workspaces` để tạo và liệt kê, `GET` và `PUT` trên `/{workspaceId}` để xem và sửa. Dùng `GET` và `POST` trên `/{workspaceId}/members` và `DELETE` trên `/{workspaceId}/members/{userId}` để quản lý thành viên. Luồng chuyển repository kiểm tra quyền trước khi thay đổi liên kết.

### Quyền và luồng API

| Thao tác | Chủ workspace | Thành viên |
|---|---|---|
| Tạo workspace | Người dùng đã xác thực có thể tạo và trở thành `OWNER`. | Người dùng có thể tạo workspace riêng. |
| Đọc workspace | Có trong danh sách và truy cập được chi tiết. | Có trong danh sách và truy cập được chi tiết với `accessRole=MEMBER`. |
| Sửa metadata hoặc thêm/gỡ thành viên | Kiểm tra chủ workspace trước khi ghi. | Không được thực hiện. |

- **FR-WORKSPACE.4 — Validate metadata.** `POST /api/managed-workspaces` và `PUT /api/managed-workspaces/{workspaceId}` nhận `name` khác rỗng, tối đa 100 ký tự và `description` tùy chọn tối đa 1000 ký tự. Tạo thành công trả `201`. Phản hồi gồm `id`, `name`, `description`, `ownerId`, `createdAt`, `updatedAt`, `accessRole`; `ownerId` là null khi gọi với tư cách thành viên.
- **FR-WORKSPACE.5 — Validate thành viên.** `POST /api/managed-workspaces/{workspaceId}/members` nhận `{"userId":42}` với ID dương, trả `201`. ID không tồn tại trả `404`; thêm chủ sở hữu trả `400`; thêm membership đã có trả `409`. Gỡ thành viên hợp lệ trả `204`.
- **FR-WORKSPACE.6 — Chuyển repository.** `PUT /api/workspaces/{workspaceId}/repositories/{id}` dùng `workspaceId` làm đích và `id` làm ID liên kết repository hiện có. Xác minh quyền sở hữu với cả nguồn lẫn đích, kiểm tra trùng và cập nhật liên kết hiện có khi hợp lệ.

## 4. Luồng lỗi

Từ chối thao tác quản trị khi thiếu quyền và từ chối liên kết trùng.

## 5. Tiêu chí chấp nhận

- **AC-WORKSPACE.1:** OWNER có thể quản lý thành viên trong workspace của mình.
- **AC-WORKSPACE.2:** MEMBER không thực hiện được thao tác dành riêng cho OWNER.
- **AC-WORKSPACE.3:** Một lần chuyển hợp lệ cập nhật liên kết; lần chuyển không hợp lệ giữ liên kết cũ.

| Ca chấp nhận | Thiết lập và thao tác | Kết quả quan sát |
|---|---|---|
| AC-WORKSPACE.4 | Owner thêm user B, rồi B đọc workspace. | B nhận `accessRole=MEMBER` và `ownerId=null`; OWNER vẫn đọc được với quyền sở hữu. |
| AC-WORKSPACE.5 | Thêm B lần hai hoặc yêu cầu thêm chính owner. | Trả lần lượt `409`, `400`; danh sách thành viên chỉ có một bản ghi B. |
| AC-WORKSPACE.6 | Người gọi sở hữu nguồn nhưng chỉ là thành viên ở đích. | Chuyển repository bị từ chối; đọc lại nguồn vẫn thấy liên kết. |

## 6. Kiểm thử và PR

- **GitHub:** Đã merge vào `main` tại thời điểm đối chiếu. [#114](https://github.com/LivingDocs-Team/Livingdocs/pull/114) · [`00281cc`](https://github.com/LivingDocs-Team/Livingdocs/commit/00281cc), [`b7f410d`](https://github.com/LivingDocs-Team/Livingdocs/commit/b7f410d).
- **Kiểm thử ghi nhận trong PR:** PR ghi nhận 25 test mock Backend, 11 test mock GitHub Integration, 9 test Repository Sync trên H2, ESLint và build Vite thành công. PR chưa xác minh persistence workspace/thành viên trên cơ sở dữ liệu riêng hoặc ghi liên kết đồng thời trên PostgreSQL.
