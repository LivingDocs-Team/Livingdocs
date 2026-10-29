# FR-AUTH-01: GitHub OAuth Authentication & Repository Connection

| Mục | Nội dung |
| :--- | :--- |
| **Story Jira** | `LD-43`: GitHub OAuth Authentication & `LD-53`: Repository Connection |
| **Task đã làm** | `LD-20`, `LD-38`, `LD-43`, `LD-53`, `LD-63`, `LD-292` |
| **Người thực hiện** | Lâm Gia Huy |
| **Thành phần** | Backend Gateway, Frontend Web App, GitHub OAuth API |
| **Tác nhân (Actor)** | GitHub OAuth Gateway |

## 1. Mô tả
Cho phép người dùng thực hiện đăng ký, đăng nhập hệ thống thông qua tài khoản GitHub (OAuth2), kết nối tài khoản GitHub cá nhân và chọn đồng bộ các Repository mã nguồn vào hệ thống LivingDocs.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
| :--- | :--- |
| **FR-AUTH-01.1** | Cho phép người dùng đăng nhập bằng tài khoản GitHub qua quy trình OAuth2 Client Credentials & Authorization Code flow. |
| **FR-AUTH-01.2** | Lưu trữ bảo mật Access Token và Refresh Token của GitHub đã được mã hóa. |
| **FR-AUTH-01.3** | Lấy danh sách các Repository thuộc quyền sở hữu của tài khoản GitHub đã kết nối. |
| **FR-AUTH-01.4** | Cho phép chọn một hoặc nhiều Repository để thêm vào Workspace theo dõi tài liệu. |
| **FR-AUTH-01.5** | Kích hoạt webhook lắng nghe các sự kiện `push` và `pull_request` từ GitHub. |

## 3. API Endpoints

| Method | Endpoint | Kết quả | Yêu cầu |
| :--- | :--- | :--- | :--- |
| **GET** | `/api/v1/auth/github/login` | Redirect to GitHub OAuth | FR-AUTH-01.1 |
| **GET** | `/api/v1/auth/github/callback` | `200 OK` + JWT Token | FR-AUTH-01.2 |
| **GET** | `/api/v1/repositories/github` | `200 OK` (List Repositories) | FR-AUTH-01.3 |
| **POST** | `/api/v1/workspaces/sync` | `201 Created` | FR-AUTH-01.4 |

## 4. Quy tắc nghiệp vụ
* Mọi GitHub Token phải được lưu mã hóa bằng thuật toán AES-256.
* Khi Token hết hạn hoặc bị thu hồi, hệ thống phải phát cảnh báo yêu cầu người dùng re-authorize.

## 5. Tiêu chí chấp nhận (Acceptance Criteria)
* **AC-AUTH-01.1:** Đăng nhập thành công trả về JWT Token trong thời gian dưới 2 giây.
* **AC-AUTH-01.2:** Danh sách Repositories hiển thị đúng tên branch mặc định và trạng thái sync gần nhất.
