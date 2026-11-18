# Các hạng mục triển khai đã đối chiếu — Nhân

Ngày đối chiếu 18/11/2026, tại [`main` `59aef13`](https://github.com/LivingDocs-Team/Livingdocs/commit/59aef13e64cac118895b381a5d872077ee8a657d). Phạm vi gồm lịch sử PR đã merge, commit trên `main`, ticket Jira kể cả lịch sử phân công và tài liệu trong `Docs/`. Tác giả PR và commit được đối chiếu với tài khoản GitHub [`nhanndt750402-max`](https://github.com/nhanndt750402-max) và assignee Nhân Nguyễn trên Jira. Việc bấm merge hoặc được giao ticket riêng lẻ chưa đủ để xác nhận phần triển khai. Kết quả kiểm thử dưới đây được ghi theo bằng chứng lịch sử tại PR hoặc commit.

## Đã merge vào main

### Tích hợp đăng ký và đăng nhập trên frontend

- [LD-389](https://ut-team-lvdocs.atlassian.net/browse/LD-389) · Jira Done · [#34](https://github.com/LivingDocs-Team/Livingdocs/pull/34) · [`78096bd`](https://github.com/LivingDocs-Team/Livingdocs/commit/78096bd).
- Nối form đăng ký và đăng nhập email/mật khẩu với API backend, dùng cookie phiên đăng nhập, hiển thị trạng thái gửi và lỗi. Bổ sung xử lý CORS/preflight cho frontend local. [FR-AUTH-01](../Huy/FR01.md) mô tả yêu cầu xác thực chung.
- PR ghi nhận ESLint và build Vite thành công, cùng 3 test controller đăng ký cho 201, 409 và 400. Kiểm thử trình duyệt với backend đang chạy chưa được thực hiện trong PR này.

### Quản lý người dùng, vai trò và quyền

- [LD-261](https://ut-team-lvdocs.atlassian.net/browse/LD-261), [LD-262](https://ut-team-lvdocs.atlassian.net/browse/LD-262), [LD-263](https://ut-team-lvdocs.atlassian.net/browse/LD-263), [LD-264](https://ut-team-lvdocs.atlassian.net/browse/LD-264), [LD-265](https://ut-team-lvdocs.atlassian.net/browse/LD-265), [LD-266](https://ut-team-lvdocs.atlassian.net/browse/LD-266) · Jira Done · [#107](https://github.com/LivingDocs-Team/Livingdocs/pull/107), [#109](https://github.com/LivingDocs-Team/Livingdocs/pull/109) · [`5a4bf2f`](https://github.com/LivingDocs-Team/Livingdocs/commit/5a4bf2f), [`ecb480b`](https://github.com/LivingDocs-Team/Livingdocs/commit/ecb480b).
- Quản trị viên có thể tra cứu, cập nhật và khóa/mở khóa tài khoản. Tài khoản bị khóa bị chặn đăng nhập và mất hiệu lực phiên đang dùng. Bổ sung danh mục vai trò, quyền, gán quyền và kiểm tra quyền theo danh tính xuyên Backend và GitHub Integration. Phần workflow trong #109 đặt nền cho luồng Developer gửi, Staff review và Manager quyết định. [Screen flow](../rbac-screen-flow.md) mô tả phần giao diện.
- #107 ghi nhận 25 test Maven và 7 job CI thành công. #109 ghi nhận 17 test workflow, test khởi tạo danh mục vai trò và biên dịch Java 21 thành công. Phần kiểm chứng của #109 còn để ngỏ migration trên cơ sở dữ liệu đang chạy và E2E toàn hệ thống.

### Lịch sử phê duyệt

- [LD-251](https://ut-team-lvdocs.atlassian.net/browse/LD-251), [LD-252](https://ut-team-lvdocs.atlassian.net/browse/LD-252), [LD-253](https://ut-team-lvdocs.atlassian.net/browse/LD-253), [LD-254](https://ut-team-lvdocs.atlassian.net/browse/LD-254), [LD-255](https://ut-team-lvdocs.atlassian.net/browse/LD-255), [LD-256](https://ut-team-lvdocs.atlassian.net/browse/LD-256) · Jira Done · [#113](https://github.com/LivingDocs-Team/Livingdocs/pull/113) · [`6c57a87`](https://github.com/LivingDocs-Team/Livingdocs/commit/6c57a87), [`9892f65`](https://github.com/LivingDocs-Team/Livingdocs/commit/9892f65).
- Lưu quyết định, người phê duyệt, vai trò đã xác thực, thời điểm và lý do. Bản ghi cũ có thể thiếu vai trò. Phân trang danh sách workflow theo quyền xem lịch sử và hiển thị quyết định đã lưu trên giao diện. Xem vị trí màn hình trong [screen flow](../rbac-screen-flow.md).
- PR ghi nhận 25 test Backend gồm 22 test service và 3 test persistence H2, cùng ESLint và build Vite thành công.

### Quản trị workspace và repository

- [LD-267](https://ut-team-lvdocs.atlassian.net/browse/LD-267), [LD-268](https://ut-team-lvdocs.atlassian.net/browse/LD-268), [LD-269](https://ut-team-lvdocs.atlassian.net/browse/LD-269), [LD-270](https://ut-team-lvdocs.atlassian.net/browse/LD-270), [LD-271](https://ut-team-lvdocs.atlassian.net/browse/LD-271), [LD-272](https://ut-team-lvdocs.atlassian.net/browse/LD-272) · Jira Done · [#114](https://github.com/LivingDocs-Team/Livingdocs/pull/114) · [`00281cc`](https://github.com/LivingDocs-Team/Livingdocs/commit/00281cc), [`b7f410d`](https://github.com/LivingDocs-Team/Livingdocs/commit/b7f410d).
- Bổ sung tạo, liệt kê, xem và sửa workspace, quản lý thành viên theo quyền OWNER/MEMBER, kiểm tra liên kết trùng, chuyển repository giữa workspace và bảo vệ thao tác quản trị. [FR-GH-02](../Đăng/FR2.md) mô tả luồng quản lý repository dùng chung.
- PR ghi nhận 25 test mock Backend, 11 test mock GitHub Integration, 9 test Repository Sync trên H2, ESLint và build Vite thành công. PR chưa xác minh persistence workspace/thành viên trên cơ sở dữ liệu riêng hoặc ghi liên kết đồng thời trên PostgreSQL.

### Hồi quy phân quyền và GitHub OAuth

- [LD-399](https://ut-team-lvdocs.atlassian.net/browse/LD-399), [LD-400](https://ut-team-lvdocs.atlassian.net/browse/LD-400) · Jira Done · [#119](https://github.com/LivingDocs-Team/Livingdocs/pull/119) · [`79c4755`](https://github.com/LivingDocs-Team/Livingdocs/commit/79c4755). Jira LD-400 có nhắc PR #94 trong tiêu đề. PR #119 và commit trên `main` là bằng chứng cho phần kiểm thử ở đây.
- Kiểm thử callback OAuth và khôi phục phiên qua `GET /api/auth/me` với phản hồi không chứa token. Kiểm tra từ chối đổi token, vô hiệu phiên khi khóa tài khoản, phản hồi 401/403, CSRF và quyền trên workspace/repository.
- PR ghi nhận 60 test Backend và 50 test GitHub Integration thành công. Bộ Backend bỏ qua `BackendApplicationTests.contextLoads` do schema PostgreSQL local thiếu cột `roles_permissions.roles_name`. Callback dùng GitHub mock, còn chạy OAuth với GitHub thật trên trình duyệt được ghi là đang chờ.

### Tổ chức lại mã xác thực và thư mục kiểm thử Backend

- [#120](https://github.com/LivingDocs-Team/Livingdocs/pull/120), [#121](https://github.com/LivingDocs-Team/Livingdocs/pull/121) · [`014d5bf`](https://github.com/LivingDocs-Team/Livingdocs/commit/014d5bf), [`362dc5b`](https://github.com/LivingDocs-Team/Livingdocs/commit/362dc5b). Chưa xác minh mã Jira riêng cho hai PR.
- #120 gom code xác thực vào package `auth`, cấu hình bảo mật/CSRF vào `security` và chuyển các test tương ứng. #121 chuyển 12 tệp test vào `backend/src/main/tests/java` và cập nhật đường dẫn test của Maven.
- Mỗi PR ghi nhận 60 test Backend thành công, với cùng ngoại lệ `contextLoads` như #119. #121 kiểm tra JAR ứng dụng không chứa test class hoặc thư viện test.

### Audit, giám sát và chính sách thông báo

- [LD-280](https://ut-team-lvdocs.atlassian.net/browse/LD-280), [LD-281](https://ut-team-lvdocs.atlassian.net/browse/LD-281), [LD-282](https://ut-team-lvdocs.atlassian.net/browse/LD-282), [LD-283](https://ut-team-lvdocs.atlassian.net/browse/LD-283), [LD-284](https://ut-team-lvdocs.atlassian.net/browse/LD-284), [LD-285](https://ut-team-lvdocs.atlassian.net/browse/LD-285) · Jira Done · [#141](https://github.com/LivingDocs-Team/Livingdocs/pull/141) · [`dfc83d3`](https://github.com/LivingDocs-Team/Livingdocs/commit/dfc83d3).
- Ghi trạng thái tác vụ AI và kết quả webhook, kiểm tra tình trạng phụ thuộc giữa các service, ghi audit thao tác quản trị và dọn bản ghi hết hạn. Thêm API quản trị thống kê theo khoảng thời gian và cấu hình chính sách thông báo. Việc gửi thông báo ra ngoài nằm ngoài phạm vi xác minh của PR.
- PR ghi nhận 82 test Backend trên PostgreSQL 18, 260 test GitHub Integration thành công và 1 bỏ qua, 264 test AI thành công và 23 bỏ qua. Kiểm tra khởi động lại AI service xác nhận truy vấn job trở về 404 sau restart. Chưa xác minh triển khai Compose E2E.

### Bình luận review, yêu cầu sửa và nộp lại tài liệu

- [LD-245](https://ut-team-lvdocs.atlassian.net/browse/LD-245), [LD-246](https://ut-team-lvdocs.atlassian.net/browse/LD-246), [LD-247](https://ut-team-lvdocs.atlassian.net/browse/LD-247), [LD-248](https://ut-team-lvdocs.atlassian.net/browse/LD-248), [LD-249](https://ut-team-lvdocs.atlassian.net/browse/LD-249), [LD-250](https://ut-team-lvdocs.atlassian.net/browse/LD-250) · Jira Done · [#154](https://github.com/LivingDocs-Team/Livingdocs/pull/154) · [`804ae91`](https://github.com/LivingDocs-Team/Livingdocs/commit/804ae91).
- Staff được phân công có thể bình luận theo phiên bản và trích đoạn văn bản. Yêu cầu sửa giữ lịch sử nhận xét của phiên bản liên quan. Developer đọc góp ý, lưu bản sửa với kiểm tra phiên bản và nộp lại trong cùng workflow để Staff và Manager tiếp tục xử lý.
- PR ghi nhận 298 test GitHub Integration thành công và 1 bỏ qua, 294 test Backend, 72 browser test thành công và 1 lỗi dự kiến đã có, 56 test Node, 27 test AI và 6 lịch sử nâng cấp migration PostgreSQL 18 thành công. Build frontend thành công. Browser test dùng API mô phỏng, kịch bản persistence dùng H2 và AI mock.

### Collections và phân công người phụ trách tài liệu

- [LD-219](https://ut-team-lvdocs.atlassian.net/browse/LD-219), [LD-220](https://ut-team-lvdocs.atlassian.net/browse/LD-220), [LD-221](https://ut-team-lvdocs.atlassian.net/browse/LD-221) · Jira To Do, chưa có assignee tại thời điểm đối chiếu · [#155](https://github.com/LivingDocs-Team/Livingdocs/pull/155) đã merge vào `main` · [`69bc7db`](https://github.com/LivingDocs-Team/Livingdocs/commit/69bc7db), [`fc9cace`](https://github.com/LivingDocs-Team/Livingdocs/commit/fc9cace).
- Luồng liệt kê, tạo, quản lý, liên kết repository và phân công đã có tài liệu tại [Documentation Collections & Ownership](../rbac-screen-flow.md#5-điểm-chưa-khớp-để-nhóm-quyết-định). Bản cập nhật ở đây ghi nhận nguồn triển khai và kiểm thử. Document Ownership dùng chung giữa các collection trong workspace. Chưa xác minh ticket riêng cho phần phân công.
- PR ghi nhận 57 test RBAC frontend, build, ESLint, 17 test Backend BFF và 2 test PostgreSQL thành công. Các test PostgreSQL kiểm tra từ chối đổi repository khi còn tài liệu, giữ các liên kết, sửa metadata, và đổi repository sau khi gỡ tài liệu cuối.

## Đã có tài liệu

| Hạng mục | Tài liệu và bằng chứng đối chiếu |
|---|---|
| Đăng ký ([LD-20](https://ut-team-lvdocs.atlassian.net/browse/LD-20), [LD-21](https://ut-team-lvdocs.atlassian.net/browse/LD-21), [LD-35](https://ut-team-lvdocs.atlassian.net/browse/LD-35), [LD-36](https://ut-team-lvdocs.atlassian.net/browse/LD-36), [LD-37](https://ut-team-lvdocs.atlassian.net/browse/LD-37)), đăng nhập/đăng xuất ([LD-38](https://ut-team-lvdocs.atlassian.net/browse/LD-38), [LD-39](https://ut-team-lvdocs.atlassian.net/browse/LD-39), [LD-40](https://ut-team-lvdocs.atlassian.net/browse/LD-40), [LD-41](https://ut-team-lvdocs.atlassian.net/browse/LD-41), [LD-42](https://ut-team-lvdocs.atlassian.net/browse/LD-42)) và GitHub OAuth ([LD-43](https://ut-team-lvdocs.atlassian.net/browse/LD-43), [LD-44](https://ut-team-lvdocs.atlassian.net/browse/LD-44), [LD-45](https://ut-team-lvdocs.atlassian.net/browse/LD-45), [LD-46](https://ut-team-lvdocs.atlassian.net/browse/LD-46), [LD-47](https://ut-team-lvdocs.atlassian.net/browse/LD-47)) | [FR-AUTH-01](../Huy/FR01.md) đã ghi các luồng xác thực. Phần Backend của Nhân được xác nhận qua [#12](https://github.com/LivingDocs-Team/Livingdocs/pull/12), [#13](https://github.com/LivingDocs-Team/Livingdocs/pull/13), [#14](https://github.com/LivingDocs-Team/Livingdocs/pull/14) và Jira. |
| CI build/test ([LD-364](https://ut-team-lvdocs.atlassian.net/browse/LD-364), [LD-365](https://ut-team-lvdocs.atlassian.net/browse/LD-365), [LD-366](https://ut-team-lvdocs.atlassian.net/browse/LD-366), [LD-367](https://ut-team-lvdocs.atlassian.net/browse/LD-367), [LD-368](https://ut-team-lvdocs.atlassian.net/browse/LD-368)) và Compose ([LD-369](https://ut-team-lvdocs.atlassian.net/browse/LD-369), [LD-382](https://ut-team-lvdocs.atlassian.net/browse/LD-382), [LD-397](https://ut-team-lvdocs.atlassian.net/browse/LD-397)) | [CI dự án](../Huy/README.md), [ENG-OPS-01](ENG-OPS-01-Docker-Compose-CI-Validation.md) và [ENG-OPS-02](ENG-OPS-02-Code-Analyzer-Docker-Compose.md). Các PR của Nhân gồm [#3](https://github.com/LivingDocs-Team/Livingdocs/pull/3), [#15](https://github.com/LivingDocs-Team/Livingdocs/pull/15), [#16](https://github.com/LivingDocs-Team/Livingdocs/pull/16), [#17](https://github.com/LivingDocs-Team/Livingdocs/pull/17), [#33](https://github.com/LivingDocs-Team/Livingdocs/pull/33). LD-397 có assignee khác và đã có tài liệu vận hành. |
| Đồng bộ repository và hợp đồng dữ liệu phân tích ([LD-63](https://ut-team-lvdocs.atlassian.net/browse/LD-63), [LD-395](https://ut-team-lvdocs.atlassian.net/browse/LD-395)) | [FR2](FR2.md), [FR3](FR3.md) và [FR-GH-04](../Đăng/FR4.md). [#29](https://github.com/LivingDocs-Team/Livingdocs/pull/29) xác nhận phần chỉnh hợp đồng dữ liệu trong LD-396. LD-395 có assignee khác. |
| Điều phối sinh tài liệu và phục hồi OAuth/session ([LD-396](https://ut-team-lvdocs.atlassian.net/browse/LD-396)) | [FR1](FR1.md) đã ghi luồng điều phối, đồng bộ lại khi cache miss và phục hồi phiên, đối chiếu với [#29](https://github.com/LivingDocs-Team/Livingdocs/pull/29), [#35](https://github.com/LivingDocs-Team/Livingdocs/pull/35), [#75](https://github.com/LivingDocs-Team/Livingdocs/pull/75). |
| Trích xuất mã Python/Java và mẫu tài liệu dự phòng | [FR-AST-02](../Huy/FR02.md) và [FR-AI-02](../Linh/FR2.md) đã ghi các khả năng tương ứng. Phần chỉnh sửa trực tiếp của Nhân có commit [`6a1c51f`](https://github.com/LivingDocs-Team/Livingdocs/commit/6a1c51f) và [`cca53e8`](https://github.com/LivingDocs-Team/Livingdocs/commit/cca53e8). Chưa xác minh mã Jira riêng cho hai commit. |

## Draft hoặc chưa merge

PR #155 từng là Draft và hiện đã merge. PR [#1](https://github.com/LivingDocs-Team/Livingdocs/pull/1) đã đóng khi chưa merge, thuộc phần khởi tạo repository.

## Chưa đủ bằng chứng để ghi nhận phần triển khai riêng

- [LD-111](https://ut-team-lvdocs.atlassian.net/browse/LD-111) có assignee Nhân Nguyễn. [#108](https://github.com/LivingDocs-Team/Livingdocs/pull/108) liên quan Evidence & Submission và việc merge có dấu vết của Nhân, nhưng chưa tìm được commit triển khai của Nhân trong PR đó. Phần chức năng đã có tại [FR-EVI-04](../Huy/FR04.md) và [FR-AI-10](../Huy/FR10.md).
- [LD-371](https://ut-team-lvdocs.atlassian.net/browse/LD-371), [LD-388](https://ut-team-lvdocs.atlassian.net/browse/LD-388), [LD-392](https://ut-team-lvdocs.atlassian.net/browse/LD-392), [LD-393](https://ut-team-lvdocs.atlassian.net/browse/LD-393), [LD-398](https://ut-team-lvdocs.atlassian.net/browse/LD-398) được đánh dấu Done và có assignee Nhân Nguyễn. Các PR đã dẫn xác nhận một số kiểm thử Backend và tích hợp cụ thể. Chưa có bằng chứng gắn từng ticket này với kết quả riêng cho Backend Unit Testing, kiểm thử E2E toàn hệ thống, nghiệm thu hoặc ổn định demo.
- PR [#2](https://github.com/LivingDocs-Team/Livingdocs/pull/2) hoàn tác một commit lúc khởi tạo. Cùng với PR #1 và commit README ban đầu, đây là lịch sử thiết lập repository, chưa có Jira hay hạng mục chức năng độc lập để ghi nhận.
