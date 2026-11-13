# CLAUDE.md — frontend/

Bổ sung cho [../CLAUDE.md](../CLAUDE.md) (quy tắc an toàn Git, secrets, security, quy trình AI áp dụng đầy đủ). Chỉ chứa thông tin đã xác minh trong `frontend/`.

## 1. Overview
React SPA của LivingDocs: đăng nhập, kết nối GitHub, quản lý repository, sinh/quản lý tài liệu, search, drift, và review/approval (Staff Queue, Manager Queue, AI Suggestion Review). Giao diện bằng **tiếng Anh**.

## 2. Stack
React 19, Vite 8 (`@vitejs/plugin-react`), ESLint 10 (flat config `eslint.config.js`, react-hooks + react-refresh). JavaScript/JSX thuần — **không TypeScript, không router, không state library, không unit test framework**. Style bằng CSS thuần (`src/App.css` ~4500 dòng, `index.css`).

## 3. Cấu trúc `src/`
- `main.jsx` → `App.jsx`: điều hướng bằng state `page` (`login`, `repository`, `documentation`, `search`, `drift`, …); khôi phục session qua `GET /api/auth/me` (lấy `id`, `role`).
- Màn hình (mỗi file một tính năng): `Register`, `Profile`, `NotificationPreferences`, `GitHubConnection`, `RepositoryManagement`, `DocumentationManagement` (lớn, ~1370 dòng; nhúng `DocumentationSuggestionReview`, `StaffReviewQueue`, `ManagerApprovalQueue`), `DocumentationTemplates`, `DocumentationSearch`, `DocumentationDrift`.
- Helper: `githubApi.js`, `csrf.js`, `errorMessages.js`, `templateApi.js`.
- Truyền `userId` và `userRole` qua props từ `App.jsx`.

## 4. Lệnh (chạy trong `frontend/`)
- `npm ci` · `npm run dev` (Vite, proxy `/api`, `/oauth2`, `/login/oauth2` → `http://localhost:8080`) · `npm run lint` · `npm run build` · `npm run preview`.
- CI chạy `npm ci`, `npm run lint`, `npm run build` (Node 24).
- E2E (từ thư mục gốc repo): build, `npx vite preview --port 3000 --strictPort --host 127.0.0.1`, rồi `python -m pytest -v tests/test_<tên>.py` (Playwright, API được mock bằng route intercept). `FRONTEND_URL` mặc định `http://localhost:3000`.
- Docker: image nginx phục vụ `dist/`; `nginx.conf` proxy `/api/`, `/oauth2/`, `/login/oauth2/` → `backend:8080`. Không chạy compose khi chưa được yêu cầu.

## 5. Quy tắc gọi API
- Mọi gọi tới service GitHub Integration đi qua `githubApi(path, { method, body, userId })` / `githubApiText` (text/markdown). Không dùng `fetch` thẳng trừ các route auth trong `App.jsx`.
- `githubApi` đã: dùng `VITE_API_BASE_URL` (mặc định cùng origin), `credentials: 'include'`, tự lấy CSRF token (`/api/auth/csrf` → header `X-XSRF-TOKEN`) cho POST/PUT/PATCH/DELETE, timeout 180s, trả `null` với 204, và lỗi có `status`, `code`, `retryAfter`.
- 401 **không có** `code` ⇒ phát sự kiện `livingdocs:unauthenticated` (hết session); 401 có `code` (vd `GITHUB_REAUTH_REQUIRED`) chỉ nghĩa là cần kết nối lại GitHub.
- Thông báo lỗi: thêm mã mới vào `MESSAGES_BY_CODE` trong `errorMessages.js` (tiếng Anh cố định theo `code`), không hiển thị text tiếng Việt từ service.
- Frontend không được tự đặt `X-User-Id` làm bằng chứng danh tính; Backend suy ra danh tính từ session.
- Browser chỉ gọi Backend (`/api/...`), không gọi trực tiếp :8082/:8001/:8000. BFF chỉ proxy GET/POST/PUT/DELETE (không PATCH).
- Endpoint workflow đang dùng: `/api/document-workflows/{staff|manager}/queue`, `history-accessible`, `{id}/document|evidence|review-evidence|review-comparison|history|claim|release|staff-review|approve|reject|rollback`. Hiển thị lỗi 403/409 từ backend, không giả lập thành công.

## 6. Quy ước code
- Function component + hooks; theo style file lân cận (dấu nháy đơn, không TS). Giữ ESLint sạch.
- Không thêm dependency, router hay state library khi chưa được duyệt.
- Không hardcode dữ liệu để che lỗi API; mock chỉ nằm trong `tests/`.
- Sửa `App.css`/`DocumentationManagement.jsx` cần cẩn thận: file lớn, nhiều tính năng dùng chung; không refactor ngoài phạm vi task.
- Phân quyền hiển thị UI (theo `userRole`) chỉ là UX; quyền thật do backend enforce.
- `userId` hiện còn lưu `sessionStorage` (`livingdocs.userId`); không lưu secret/token vào storage.

## 7. Kiểm chứng
- Mọi thay đổi UI: `npm run lint` + `npm run build`, và chạy file E2E liên quan trong `tests/` (`test_staff_review_queue.py`, `test_manager_approval.py`, `test_documentation_suggestion_review.py`, `test_frontend_drift.py`, `test_frontend_templates.py`, `test_documentation_preview_editing.py`, `test_frontend.py`). Chỉ báo "pass" khi đã chạy thật.
- E2E dùng build đã dựng ở cổng 3000: build lại trước khi test nếu đã sửa `src/`.

## 8. Giới hạn đã biết (xác minh bằng đọc code ngày 2026-11-13)
Cập nhật mục này (và commit) mỗi khi một điểm dưới đây thay đổi.
1. **UI chưa nối với khâu tạo workflow**: không có chỗ nào trong `frontend/src` gọi `POST /api/documentation/jobs/{jobId}/document`, `POST /api/document-workflows` hay `POST …/{id}/submit`. `DocumentationManagement` chỉ sinh/sửa/xem tài liệu ở client; Staff Queue, Manager Queue, Suggestion Review chỉ hiển thị workflow đã được tạo qua API. Với luồng UI hiện tại, người dùng không tự tạo/nộp workflow được. Đừng giả lập khâu này bằng dữ liệu cứng; cần task/Jira riêng.
2. **`Profile.jsx` và `NotificationPreferences.jsx` chỉ là demo**: dữ liệu nằm trong state, không gọi API ("Demo only / Backend is not connected"). Trang login có link "View demo profile".
3. **Workspace**: `DocumentationManagement`, `DocumentationSearch`, `DocumentationDrift` luôn dùng workspace cá nhân `ws-${userId}`. Chỉ `RepositoryManagement` đọc `/api/managed-workspaces` (chỉ GET; thêm/sync/xóa/chuyển repo nếu là OWNER). Chưa có UI tạo workspace hay quản lý member, và chưa có UI admin (user/role) dù backend đã có API.
Ngoài ra (cùng đợt kiểm tra): các thao tác "Save draft", "Create version", "Compare", "Restore" ở `DocumentationManagement` chỉ là state React, mất khi tải lại trang; request sinh tài liệu gửi cứng `outputLanguage: 'vi'`.

## 9. Tài liệu liên quan
- [../services/github-integration-service/docs/frontend-api-guide.md](../services/github-integration-service/docs/frontend-api-guide.md), `backend-bff-authentication.md` (lưu ý: một phần đã lỗi thời so với BFF hiện tại)
- [docs/documentation-preview-editing-test-report.md](docs/documentation-preview-editing-test-report.md) (đang có thay đổi chưa commit)
- [../Docs/PROJECT_STATUS.md](../Docs/PROJECT_STATUS.md)
