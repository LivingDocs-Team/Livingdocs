# Phân quyền (RBAC) và Screen Flow theo vai trò — Frontend

Tài liệu này mô tả cách frontend hiển thị menu, màn hình và nút theo 5 vai trò, và cách thêm vai trò / màn hình / quyền mới. Mã nguồn nằm trong `frontend/src/rbac/`.

> **Phạm vi:** frontend (menu, chặn URL, ẩn nút) và backend (BFF chặn theo cùng ma trận, xem mục 9). Ẩn nút ở frontend chỉ để tiện cho người dùng; backend mới là nơi từ chối request.

## 1. Kiến trúc

| Thành phần | File | Vai trò |
|---|---|---|
| Ma trận quyền (single source of truth) | `rbac/permissions.js` | 24 dòng Screen × 5 role (giữ số dòng gốc; #4, #14, #15 và #16 đã xoá) → tập action `C R U D A E`. Hàm `can(role, screenKey, action)`, `canAccess()`, `allowedActions()`. |
| Vai trò | `rbac/roles.js` | Tên role, nhãn, `normalizeRole()` (legacy `ADMIN` → `ADMINISTRATOR`). |
| Screen flow | `rbac/flows/*.flow.js` | Mỗi role một cây Module → Screen → Sub-screen. Node có `key`, `label`, `path`, `permissionKey`, `status`. |
| Route guard | `rbac/guard.js` | `resolveRoute({ path, role, isAuthenticated })` → public / redirect / screen / forbidden / no-role. Hàm thuần, có test. |
| Hook / component | `rbac/usePermission.js`, `rbac/Can.jsx` | `usePermission().can(screen, action)`; `<Can screen action>` ẩn nút (hoặc truyền function để disable). |
| App shell | `rbac/AppShell.jsx`, `rbac/PageFrame.jsx` | Menu + breadcrumb render từ flow; bảng `SCREENS` (tên `component` → component thật); khung trang dùng chung. **Menu chỉ liệt kê các màn hình chính**: sub-screen không hiện ở menu, mục cha vẫn sáng khi đang ở một sub-screen. Sub-screen là một phần của trang cha mở bằng URL/breadcrumb; sub-screen là một trang riêng (Staff › Document Editor) hiện thành nút ở đầu trang cha; Profile & Settings hiện hai ô chọn (Profile, Notification Preferences). |
| Placeholder / 403 | `rbac/PlaceholderScreen.jsx`, `rbac/ForbiddenScreen.jsx` | Trang "Chưa triển khai" chung và trang "Access denied". |
| Router | `rbac/hashRoute.js` | Hash router nhỏ (`#/review/queue`), không thêm dependency, không phải sửa nginx. |
| Cờ giao diện | `rbac/config.js` | `dimPlaceholders`: làm mờ mục placeholder trong menu (rê chuột hiện "Chưa triển khai"). |

Không có `if (role === ...)` trong menu hay guard: mọi quyết định đọc từ `permissions.js` và `flows/`.

**Vì sao chọn cách này:** dự án không dùng router/state library và CLAUDE.md không cho tự thêm dependency, nên dùng hash router tự viết (gõ URL trực tiếp vẫn chạy, không phải cấu hình nginx). Phần cấu hình và guard là JS thuần nên test bằng `node --test` có sẵn trong Node 24 (không cần vitest). Các component cũ được giữ nguyên và gắn vào node `implemented`; chỉ bọc `<Can>` quanh nút ở những component dùng chung nhiều role.

## 2. Luồng trang

- **Màn hình 1 (chưa đăng nhập):** chỉ `#/` Home, `#/login` Login, `#/register` Register. Register luôn tạo tài khoản **Developer** (backend gán `DEVELOPER`); role khác do Administrator gán.
- Vào URL nội bộ khi chưa đăng nhập (hoặc phiên hết hạn) → chuyển về Login; đăng nhập xong (mật khẩu, phiên khôi phục hoặc GitHub OAuth) mở lại trang đã yêu cầu nếu role được phép, ngược lại về landing page của role.
- **Màn hình 2 (đã đăng nhập):** sidebar theo flow của role, breadcrumb, nút Logout. Vào trang công khai khi đã đăng nhập → landing page.
- URL nội bộ thuộc role khác → trang 403 "Access denied" (có nút về trang chủ của role). URL không tồn tại → landing page.
- Logout → về Home (`#/`). Phiên hết hạn → Login với thông báo.
- Tài khoản không có role hợp lệ → trang "No role assigned", không có menu.

Landing page: Developer `#/github/connection`, Staff `#/review/queue`, Manager `#/approval/queue`, Technical Lead `#/knowledge/search`, Administrator `#/account/profile`.

## 3. Cách thêm mới

**Thêm màn hình vào một role**
1. Nếu cần quyền mới: thêm một dòng vào `ROWS` trong `permissions.js` (key, label, typical actions, 5 ô).
2. Thêm node vào file flow của role:
   - Chưa có chức năng: `placeholder('key', 'Label', '/duong-dan', 'permissionKey')`.
   - Đã có component: `implemented('key', 'Label', '/duong-dan', 'permissionKey', 'TenComponent')` và thêm `TenComponent: { Component: TenComponent }` vào bảng `SCREENS` trong `AppShell.jsx` (component nhận prop `userId`).
   - Sub-screen là một phần của trang cha: `section('key', 'Label', '/duong-dan', 'permissionKey')` trong `children` của màn hình cha (tự dùng component của cha).
   - Profile & Settings dùng chung cho mọi role: `profileSettings()`.
3. Chạy `npm test` (test sẽ báo nếu role không có quyền trên `permissionKey`, trùng key/path…), rồi cập nhật danh sách menu mong đợi trong `tests/test_rbac_screen_flow.py` và `src/rbac/__tests__/flows.test.js` (với role có flow chính thức).

Không cần sửa guard, sidebar hay breadcrumb.

**Khi chức năng placeholder được xây xong:** đổi `placeholder(...)` thành `implemented(..., 'TenComponent')` và thêm component vào `SCREENS`.

**Thêm/sửa quyền:** chỉ sửa ô trong `permissions.js`; nút bọc `<Can>` và guard tự đổi theo. Cập nhật bảng `SPEC` trong `__tests__/permissions.test.js` cho khớp đặc tả.

**Ẩn nút theo quyền trong component:**
```jsx
import Can from './rbac/Can';
<Can screen="templates" action="U"><button>Manage templates</button></Can>
<Can screen="staffReview" action="A">{(allowed) => <button disabled={!allowed}>Approve</button>}</Can>
```

**Thêm role mới:** thêm vào `ROLES`/`ROLE_ORDER`/`ROLE_LABELS` (`roles.js`), thêm một cột vào mỗi dòng `ROWS`, tạo `flows/<role>.flow.js` và đăng ký trong `flows/index.js`. Backend cũng phải có role đó (`RoleCatalogInitializer`, `AdminUserController`).

## 4. Ánh xạ Screen ↔ ma trận (`permissionKey`)

Sub-screen ghi "(phần của …)" là một phần của trang có sẵn; mở sub-screen sẽ mở trang đó.

### Developer (flow chính thức, đã bỏ Dashboard, Automatic Update, Drift Review và Repository & Collections)
| Module | Screen | Dòng | Trạng thái |
|---|---|---|---|
| Account Management | Profile & Settings → Profile, Notification Preferences | #2 | implemented (Profile, NotificationPreferences) |
| | Notifications → Notification Details | #3 | implemented (`Notifications`; chi tiết là phần của trang) |
| GitHub Integration | GitHub Connection | #5 | implemented |
| | Repository List → Repository Selection, Repository Details, Repository Synchronization | #6 | implemented (RepositoryManagement) |
| | PR & Commit List | #7 | implemented (phần RepositoryActivity trong Repository Management) |
| Documentation Generation | (đã bỏ mục Generation Request và Template Selection 2026-11-18: trang tạo tài liệu mở từ Generated Documents) | | |
| | Coverage Gaps | #8 | implemented (`CoverageGaps`, API `GET /api/repositories/{id}/coverage-gaps`) |
| | Generated Documents → Preview & Editor, Grounding Evidence | #8 | implemented (DocumentationManagement) |
| | → Submit for Review | #9 | implemented |
| | → Review Feedback | #10 | implemented (Approval History trong DocumentationManagement) |
| Versions & Change Log | Version History → Version Comparison | #18 | implemented (phần của DocumentationManagement) |
| | → Document Rollback | #19 | implemented (Restore this version) |
| | Change Log | #18 | implemented (`ChangeLog`) |
| Knowledge Base | Documentation Collections | #21 | implemented (DocumentationCollections, đọc) |
| | Knowledge Search → Search Results, Doc-to-Code Relationships | #20 | implemented (DocumentationSearch) |
| | Template Library | #22 | implemented (`TemplateLibrary`; Developer chỉ xem) |

### Staff (flow chính thức)
| Module | Screen | Dòng | Trạng thái |
|---|---|---|---|
| Account Management | Profile & Settings → Profile, Notification Preferences | #2 | implemented |
| Document Review | Review Queue → Review Workspace, Grounding Evidence, Comments & Change Requests, Review Decision | #10 | implemented (StaffReviewQueue) |
| | → Version Comparison | #18 | implemented (phần của StaffReviewQueue) |
| | → Change Log | #18 | placeholder |
| | → Template & Code Check | #22 | placeholder |
| | → Document Editor | #8 | implemented (DocumentationManagement: AI Suggestion Review, chỉnh sửa đề xuất) |
| | Review History | #13 | implemented (`ApprovalAudit`) |

### Manager (flow chính thức)
| Module | Screen | Dòng | Trạng thái |
|---|---|---|---|
| Account Management | Profile & Settings → Profile, Notification Preferences | #2 | implemented |
| Final Approval | Approval Queue → Approval Workspace, Approval Decision | #11 | implemented (ManagerApprovalQueue) |
| | → Staff Comments & Evidence | #10 | implemented (phần của ManagerApprovalQueue) |
| | → Audit Trail | #13 | implemented (phần của ManagerApprovalQueue) |
| | → Version Rollback | #19 | implemented (Request rollback) |
| | Approval History | #13 | implemented (Manager decision history) |
| | Approval Delegation | #11 | implemented (`ApprovalDelegation`) |
| Approval Policies | Approval Policy, Merge Policy | #12 | implemented (`ApprovalPolicies`) |

### Technical Lead và Administrator — **flow TẠM (provisional)**
Nhóm chưa có screen flow cho 2 role này. `technicalLead.flow.js` và `administrator.flow.js` có `provisional: true` và comment `// TODO: thay bằng screen flow chính thức của nhóm`. Hai flow được dựng **chỉ** từ các dòng ma trận mà role có quyền (mỗi dòng một màn hình, gom theo module), giao diện hiển thị badge "Provisional flow".

Chỉ gắn component có sẵn khi component đó không có hành động vượt quyền của role:
- Technical Lead: Profile, Notification Preferences, Documentation Collections (#21, CRUD và phân công), Knowledge Search (#20, DocumentationSearch), Documentation Templates (#22, CRUD → `TemplateLibrary` dùng lại TemplateManager). Mọi màn hình khác là placeholder (ví dụ Documentation #8 chỉ R trong khi trang Documentation Management có nút tạo).
- Administrator: Profile, Notification Preferences. Các màn hình Administration và Monitoring (#24 Users, Roles & Permissions, #25 Workspace & Repository Administration, #26 System Configuration, #27 Monitoring, Audit Logs & Analytics, #28 Notification Policies) dùng chung component `AdminDashboard` (LD-316) và mở đúng tab của mình; test: `tests/test_frontend_admin.py`. Repository Management (#6) và Approval Audit Trail (#13) là placeholder; Repository Management chưa nối vì trang hiện có cũng hiển thị PR/commit (#7) mà Administrator không có quyền.

## 5. Điểm chưa khớp (để nhóm quyết định)

**Đã quyết định (2026-11-17) — ma trận trong code khác bảng đặc tả gốc ở các ô sau**
- Bỏ quyền ở các dòng mà flow chính thức của role không có màn hình nào, nên role không thấy và không dùng được ở bất kỳ đâu (kể cả trong trang dùng chung):
  Developer #11; Staff #7, #9, #11, #15, #16; Manager #7, #8, #9, #15, #16, #18.
- Dòng #8 thêm action **E** (nút "Export Markdown" trong trình soạn tài liệu), chỉ cho **Developer** (người tạo/chỉnh tài liệu, màn hình Preview & Editor). Staff (Document Editor, #8 R-U) không thấy nút này.
- **Xoá khỏi web cho mọi role (2026-11-17):** #4 Dashboard / Health views, #14 Auto-Update Settings & Policies, #15 Auto-Update Review, #16 Drift Alerts & Review. Các dòng này bị bỏ khỏi `permissions.js` (các dòng còn lại giữ số gốc), các màn hình liên quan bị bỏ khỏi mọi flow; URL cũ (`#/dashboard`, `#/auto-update/*`, `#/drift/alerts|analysis|history`) giờ là trang không tồn tại và chuyển về landing page. Trang Documentation Drift (`DocumentationDrift.jsx`), CSS riêng của nó và test `tests/test_frontend_drift.py` đã bị xoá; API drift ở backend/AI service không đổi. Technical Lead vẫn giữ Drift Policies & Thresholds (#17).
- Test `flows.test.js` giờ kiểm tra cả 5 role: mỗi dòng role có quyền phải có ít nhất một màn hình trong flow, và ngược lại.

**Documentation Collections & Ownership (#21)**

- Knowledge Base → Documentation Collections (`#/knowledge/collections`). Developer có quyền đọc. Technical Lead có quyền tạo, sửa, xóa collection, thêm hoặc gỡ tài liệu và phân công người phụ trách.
- Collection thuộc một workspace và có thể liên kết với một repository trong workspace đó. API trả HTTP 409 khi đổi hoặc gỡ repository của collection còn tài liệu. Giao diện khóa trường repository trong trường hợp này và các liên kết tài liệu được giữ lại. Nếu repository được chuyển workspace hoặc ngắt kết nối, tài liệu của repository không còn xuất hiện trong collection.
- API `/api/workspaces/{workspaceId}/collections` kiểm tra cả quyền theo vai trò và quyền truy cập workspace. Technical Lead là thành viên có thể quản lý collection trong workspace chung. Người phụ trách phải là tài khoản đang hoạt động và có quyền truy cập cùng workspace tại lúc phân công.
- Mỗi tài liệu có tối đa một người phụ trách trong một workspace. Phân công dùng chung giữa các collection và tách khỏi chủ sở hữu phục vụ kiểm tra quyền chỉnh sửa, review và phê duyệt. Màn hình hiển thị tiêu đề từ tài liệu đã lập chỉ mục và mã tài khoản được phân công.
- Migration Flyway `V12__documentation_collections.sql` nằm trong thư mục migration dùng chung. Kiểm thử tích hợp `DocumentationCollectionsPostgresTest` dùng một cơ sở dữ liệu PostgreSQL rỗng qua các biến `COLLECTIONS_TEST_DB_URL`, `COLLECTIONS_TEST_DB_USER` và `COLLECTIONS_TEST_DB_PASSWORD`.

**Ánh xạ screen → dòng là lựa chọn (đặc tả không ghi rõ), cần nhóm xác nhận**
- Developer: Coverage Gaps → #8; Review Feedback → #10.
- Staff: Grounding Evidence → #10; Template & Code Check → #22; Document Editor → #8; Review History → #13.
- Manager: Staff Comments & Evidence → #10; Audit Trail, Approval History → #13; Approval Delegation → #11.

**Hành vi hiện có khác ma trận**
- Developer trước đây mở được "Manage templates" trong Documentation Management. Dòng #22 chỉ cho Developer **R**, nên nút này nay chỉ hiện khi `can(role,'templates','U')`; quản lý template chuyển sang Technical Lead (Documentation Templates). Chức năng không bị xoá.
- Staff vào Documentation Management qua "Document Editor" (#8 R-U): nút Generate (#8 C), Export Markdown (#8 E), Submit for review (#9), Manage templates (#22 U) và Restore this version (#19 U) bị ẩn theo ma trận.
- "Save code links" (liên kết tài liệu ↔ code) nằm trong trang chỉnh sửa (#8 U), trong khi #20 chỉ R — giữ nguyên.
- Dòng #1 Authentication là ✓ cho mọi role nhưng Register chỉ dành cho Developer: Register là trang công khai, backend luôn tạo `DEVELOPER`.
- Sub-screen dùng chung trang cha mở toàn bộ trang, chưa cuộn tới đúng phần.
- Trước đây người chưa đăng nhập thấy "Quick access", "View profile" và "Notification preferences" trên trang Login; theo yêu cầu màn hình 1 các mục này đã bỏ khỏi trang Login và chỉ có sau khi đăng nhập (qua menu).

## 6. Tài khoản test

`scripts/rbac-test-accounts.example.json` chứa 5 tài khoản (mỗi role một tài khoản, mật khẩu chỉ dùng cho môi trường local). Tạo chúng bằng API có sẵn:

1. Backend không có admin mặc định, nên Administrator phải được nâng quyền một lần: chạy script (bước 2) để đăng ký, rồi trên DB local:
   `docker compose exec backend-db psql -U <DB_USERNAME> -d cnpm -c "UPDATE users SET role='ADMINISTRATOR' WHERE email='admin.rbac@livingdocs.test';"`
   (`<DB_USERNAME>` lấy trong `.env` của bạn; không ghi giá trị vào tài liệu.)
2. `python scripts/seed_rbac_test_accounts.py --base-url http://localhost:3000` — đăng ký 5 tài khoản (đã tồn tại thì bỏ qua) và dùng tài khoản Administrator gán role cho 4 tài khoản còn lại qua `PATCH /api/admin/users/{id}/role`.

Lỗi backend đã sửa (2026-11-18): `GET /api/admin/users` không có tham số `search` từng trả 500 trên PostgreSQL (`function lower(bytea) does not exist`, vì tham số null được gửi dưới dạng bytea). `UserRepository.searchForAdministration` giờ ép `search` về chuỗi (`cast(:search as string)`); test hồi quy: `UserRepositoryPostgresTest` (cần PostgreSQL thật).

Đã tạo trên stack Docker local ngày 2026-11-17 (5 tài khoản trong file mẫu, đăng nhập thử trên web thật: đúng landing page và menu của từng role).

## 7. Kiểm thử

- `cd frontend && npm test` — `node --test`: `can()` với toàn bộ ma trận (24 dòng × 5 role × 6 action, và các dòng đã xoá không role nào truy cập được), cấu trúc flow, menu 3 flow chính thức, độ phủ của 2 flow tạm, route guard cho mọi role × mọi đường dẫn nội bộ.
- `python -m pytest -v tests/test_rbac_screen_flow.py` — E2E Playwright: màn hình công khai, chuyển về Login, menu từng role, chặn URL trực tiếp (403), placeholder, Register chỉ Developer, nút theo `can()`.
- Backend: `mvnw test` (xem mục 9).

## 8. Giao diện (theme tối) — 2026-11-18

- **Bảng màu:** `src/index.css` định nghĩa biến màu (`--bg`, `--surface`, `--line`, `--text`, `--accent`, ...). `App.css` đọc màu từ các biến này (đã đổi từ nền sáng bằng script theo từng loại thuộc tính; bố cục không đổi). `src/theme.css` chứa phần bố cục mới: nền động, màn hình công khai, khung ứng dụng, menu, ô chức năng, hiệu ứng.
- **Màn hình công khai** (`PublicShell.jsx`): header Home/Login/Register, hero bên trái, thẻ Home/Login/Register bên phải (`AuthField.jsx`, `HeroArt.jsx`, `icons.jsx`). Không có chức năng nội bộ.
- **Hiệu ứng:** nền chấm sao nối nhau + hai quầng sáng trôi (`AnimatedBackground.jsx`), minh họa hero chuyển động, chuyển trang mờ dần từ dưới lên, ô chức năng nhấc lên/viền sáng/vệt sáng theo chuột (`spotlight.js`; danh sách class trong `SPOTLIGHT_SELECTOR` và trong `theme.css` phải khớp). Tất cả tắt khi hệ điều hành bật "giảm chuyển động"; nền tạm dừng khi tab bị ẩn.
- **Menu:** nhãn nhóm in đậm cỡ lớn, chức năng chữ mảnh; xem mục 1 về việc chỉ liệt kê màn hình chính.
- **Phông chữ:** dùng bộ phông hệ thống (Inter nếu máy đã cài, không tải từ ngoài) để trình duyệt chỉ gọi Backend cùng origin.

### Kích thước giao diện (phóng 150%) — 2026-11-18

- Mọi thứ hiển thị lớn hơn 1,5 lần, giống phóng to trình duyệt 150%. Hệ số nằm ở `--ui-scale` trong `src/index.css`; `theme.css` áp dụng bằng `zoom` lên các lớp nhìn thấy (`.public-shell`, `.app`, `.session-check`). Lớp nền động không bị phóng (luôn phủ kín cửa sổ).
- **Điểm ngắt giao diện (`@media`) trong `App.css` và `theme.css` đã được nhân 1,5** (ví dụ 960px → 1440px) vì media query đọc chiều rộng cửa sổ thật, không đọc chiều rộng sau khi phóng. Vì vậy cửa sổ rộng dưới khoảng 1440px sẽ xếp menu lên trên nội dung, giống trình duyệt phóng 150%.
- `100vh` trong vùng đã phóng được viết `calc(100vh / var(--ui-scale))`, và `spotlight.js` chia tọa độ chuột cho hệ số phóng.
- **Đổi hệ số:** sửa `--ui-scale` rồi nhân lại các điểm ngắt `@media` và kiểm tra lại (script đã dùng nằm ngoài repo); chỉ sửa biến sẽ làm điểm ngắt lệch.

## 9. Kiểm tra quyền ở backend (BFF) — 2026-11-18

Mọi request của trình duyệt tới `/api/github|workspaces|repositories|documentation|document-workflows/**` đi qua `GitHubIntegrationBffController`. Trước khi chuyển tiếp, BFF kiểm tra role của tài khoản theo ma trận; không có quyền → **403**, không gọi GitHub Integration.

| Thành phần | File | Vai trò |
|---|---|---|
| Ma trận | `backend/.../security/ScreenPermissions.java` | Bản Java của `permissions.js` (24 dòng × 5 role). `ADMIN` (cũ) = `ADMINISTRATOR`. |
| Quy tắc route | `backend/.../security/ApiRoutePermissions.java` | Mỗi (method, đường dẫn) cần **ít nhất một** cặp (dòng ma trận, action). Route chưa có quy tắc bị từ chối (deny by default), nên route mới phải được thêm vào đây. |
| Gắn vào BFF | `GitHubIntegrationBffController.proxy()` | Chạy sau khi xác định người dùng, trước kiểm tra workspace. |

- Ma trận là **giới hạn trên**. GitHub Integration vẫn kiểm tra thêm (chủ sở hữu tài liệu, quyền `DOCUMENT_*`, thành viên workspace), nên kết quả cuối là phần giao của hai bên.
- Các màn hình cùng đọc một dữ liệu dùng nhiều dòng (ví dụ danh sách repository cần #6 R **hoặc** #8 R **hoặc** #7 R **hoặc** #20 R) để Staff (chỉ có #8) và Technical Lead (chỉ có #20) vẫn mở được màn hình của mình.
- Các route drift (`/api/repositories/{id}/drift/**`) bị từ chối với mọi role vì dòng #16 đã bị gỡ; `GET /api/documentation/drift/severity-rules` cần #17 R (Technical Lead). Reassign review cần #24 U (Administrator) và `DOCUMENT_REASSIGN` như trước.
- `/api/admin/**` giữ nguyên: chỉ ADMIN/ADMINISTRATOR và `@PreAuthorize` theo quyền (khớp các dòng #24, #27, #28 chỉ có Administrator).
- **Chưa theo ma trận (cố ý):** `/api/managed-workspaces/**` (`WorkspaceController`) và `/api/profile/**` kiểm tra theo chủ sở hữu/thành viên, không theo role. Dòng #25 chỉ cho Administrator, nhưng Developer đang dùng workspace tự quản trong trang Repository; áp dụng #25 sẽ làm hỏng chức năng đó nên cần nhóm quyết định. Các quyền đọc của Technical Lead (#7–#11, #13) đã được BFF cho phép nhưng GitHub Integration chưa cấp quyền `DOCUMENT_*` tương ứng cho role này; sẽ nối khi màn hình của Technical Lead được xây.
- **Giữ ma trận hai nơi đồng bộ:** `ScreenPermissionsParityTest` đọc `frontend/src/rbac/permissions.js` và `roles.js` rồi so với bản Java; đổi quyền ở một nơi mà quên nơi kia sẽ làm test fail. `ApiRoutePermissionsTest` kiểm tra các route đại diện với cả 5 role theo bảng viết tay từ ma trận.
- Frontend: khung "Staff Review Queue" nhúng trong trang Documentation chỉ hiện cho role có #10 U (Staff); Developer chỉ đọc phản hồi duyệt (#10 R) nên không còn thấy khung này (trước đó bấm vào sẽ báo 403).

## 10. Bốn màn hình Developer đã triển khai (nhánh `LD-Developer-remaining-screens`)

Flow Developer không còn màn hình placeholder. Các màn hình dùng dữ liệu thật, không mock, không đổi schema hay migration.

| Màn hình | Nguồn dữ liệu | Hành vi |
|---|---|---|
| Notifications (#3) | `GET /api/document-workflows/history-accessible` và `GET /api/profile/notification-preferences` | Backend chưa có bảng thông báo nên danh sách được suy ra từ workflow của người dùng: đã gửi duyệt, Staff nhận duyệt, kết quả Staff, quyết định Manager. Loại thông báo tắt trong Notification Preferences bị ẩn (có ô hiện lại). Trạng thái đã đọc lưu ở `localStorage` của trình duyệt. Chọn một thông báo để xem chi tiết (Notification Details mở cùng trang). |
| Coverage Gaps (#8) | `GET /api/repositories/{id}/coverage-gaps` (mới, GitHub Integration Service) | Chọn repository; hiển thị % entity code đã có tài liệu liên kết và danh sách entity chưa có, nhóm theo file, lọc theo loại. Mới là một truy vấn đọc (`not exists` trên `documentation_code_relationships`), BFF cần `documentation` R. |
| Change Log (#18) | `GET /api/document-workflows/history-accessible` và `GET /api/document-workflows/{id}/versions` | Chọn tài liệu, xem từng phiên bản mới nhất trước: nguồn, người tạo, ghi chú, các thay đổi theo phần. Chỉ đọc. |
| Template Library (#22) | `GET /api/documentation/templates` | Vai trò chỉ có R (Developer) chỉ xem danh sách mẫu; vai trò có C/U/D (Technical Lead) vẫn dùng bộ quản lý mẫu. |

Kiểm thử: `tests/test_developer_screens.py` (16 kịch bản), `DocumentationCodeRelationshipApiTest` (kiểm thử coverage gaps), `ApiRoutePermissionsTest` (route mới theo vai trò).

## 11. Review History, Approval Audit Trail và Repository Management (Administrator)

| Màn hình | Vai trò | Cách làm |
|---|---|---|
| Review History (#13) | Staff | `ApprovalAudit`: danh sách workflow mà Staff truy cập được (`history-accessible`) và chuỗi sự kiện của từng workflow (`/history`): hành động, người làm và vai trò, trạng thái trước và sau, nhận xét. |
| Approval Audit Trail & History (#13) | Administrator | Cùng trang `ApprovalAudit`, tên lấy từ node của flow. Chỉ hiện các workflow mà quyền `DOCUMENT_*` của Administrator cho đọc. |
| Repository Management & Synchronization (#6) | Administrator | Dùng lại `RepositoryManagement`. Nút "PRs & commits" và panel hoạt động được bọc `can('pullRequests','R')` nên Administrator (không có #7) không thấy và không gọi API PR. |

Còn là placeholder: Staff › Review Queue › Change Log và Template & Code Check (màn hình con, mở bằng URL). Kiểm thử: `tests/test_role_screens.py`.

## 12. Manager (chính sách, ủy quyền) và Technical Lead (giám sát)

Mọi màn hình trong flow Manager và Technical Lead đã triển khai. Cần thêm backend (GitHub Integration Service) nên có một migration mới (`db/migration-common/V18__approval_policies_and_delegations.sql`: bảng `approval_policies`, `approval_delegations`), hai nhóm route mới và quy tắc BFF tương ứng.

### Manager
| Màn hình | API | Hành vi và phần được thi hành |
|---|---|---|
| Approval Policy (#12) | `GET/PUT /api/approval/policies/approval` | `requireStaffComment`: Staff phải ghi nhận xét với mọi kết quả duyệt; `requireManagerComment`: Manager phải ghi nhận xét khi phê duyệt. Được thi hành trong `DocumentWorkflowService` (trả 400 nếu thiếu). Mặc định cả hai tắt, đúng hành vi cũ. |
| Merge Policy (#12) | `GET/PUT /api/approval/policies/merge` | `allowCommitBack`: cho phép hay không việc đưa tài liệu đã duyệt lên GitHub (tắt thì `github-commit` trả 409); `commitMessageTemplate` với `{document}`, `{version}` là nội dung commit khi đưa lên GitHub. Được thi hành trong `DocumentCommitBackService`. |
| Approval Delegation (#11) | `GET/POST /api/approval/delegations`, `DELETE /api/approval/delegations/{id}` | Manager ghi nhận Manager khác (nhập ID người dùng) thay mình duyệt tối đa 90 ngày, tối đa 10 ủy quyền còn hiệu lực; cả hai bên đều thấy; chỉ người ủy quyền thu hồi được. Hàng đợi duyệt dùng chung cho mọi Manager nên ủy quyền chỉ là bản ghi hiển thị, không đổi ai được quyết định. |

### Technical Lead (đọc, trừ Drift Policies)
Quyền đọc dựa trên quyền `DOCUMENT_TECHNICAL_REVIEW` mà vai trò này đã có (không thêm quyền mới vào danh mục): `history-accessible` và các route đọc workflow trả mọi workflow (chỉ đọc; duyệt, từ chối, rollback vẫn chỉ Manager). Các route `/api/oversight/**` yêu cầu quyền này (hoặc Administrator).

| Màn hình | API | Hành vi |
|---|---|---|
| Pull Requests & Commits (#7) | `GET /api/oversight/repositories`, `.../{id}/pull-requests`, `.../{id}/commits` | Chọn repository bất kỳ, xem PR và commit đã nhận. |
| Documentation (#8) | `GET /api/oversight/documentation[/{id}]` | Danh sách tối đa 200 tài liệu mới nhất, lọc theo tên, xem nội dung Markdown (chỉ đọc). |
| Workflow Status (#9), Staff Review (#10), Manager Approval (#11) | `history-accessible`, `/history` | `WorkflowOversight`: danh sách workflow nhóm theo trạng thái (Staff Review: chờ hoặc đang duyệt; Manager Approval: chờ, đã duyệt hoặc từ chối), chi tiết và lịch sử sự kiện. Không có nút thao tác. |
| Approval Audit Trail & History (#13) | `history-accessible`, `/history` | Trang `ApprovalAudit` dùng chung. |
| Drift Policies & Thresholds (#17) | `GET/PUT /api/oversight/repositories/{id}/drift-policies` | Sửa quy tắc auto-update (commit hoặc PR nào làm mới tài liệu nào) của bất kỳ repository nào, dùng lại `AutoUpdatePolicyEditor`; đây là chính sách drift đang được thi hành. |
| Version History & Comparison (#18) | `/versions`, `/comparison` | Dùng lại `DocumentVersionComparison`. |
| Document Rollback (#19) | `/versions`, `/history` | Danh sách phiên bản và các yêu cầu rollback đã có; không có nút rollback vì rollback là quyết định của Manager (matrix cho Technical Lead U nhưng service chỉ cho Manager). |
| Health Metrics, Dependency Graph & Reports (#23) | `GET /api/oversight/health` | Số repository, tài liệu, code entity, % phủ tài liệu, workflow theo trạng thái, đồ thị tài liệu → file (tối đa 300 liên kết mạnh nhất, hiển thị dạng danh sách mở rộng được). Export JSON và CSV (nút bọc `<Can healthReports E>`; CSV vô hiệu hóa ô bắt đầu bằng `=`, `+`, `-`, `@`). |

Kiểm thử: `tests/test_governance_screens.py` (19 kịch bản), `ApprovalGovernanceAndOversightApiTest` (11, GitHub Integration Service), `ApiRoutePermissionsTest` (route mới theo vai trò), `FlywayMigrationLineageSelectorTest` (V18).

Giới hạn đã biết: ủy quyền chưa đổi quyền quyết định (xem trên); ô nhập Manager dùng ID người dùng vì chưa có API liệt kê Manager cho vai trò Manager; chưa có phân loại severity/threshold riêng cho drift ngoài quy tắc auto-update.
