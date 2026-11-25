# LivingDocs — Project Requirements (yêu cầu của giảng viên)

Nguồn: `Project_CNPM.docx.md` (đề cương chính thức, mục 3.2 a–g). Đây là **bản tóm tắt có đánh dấu trạng thái**; khi mâu thuẫn, tài liệu gốc của giảng viên là chuẩn.
Đối chiếu với code ngày 2026-11-13 (branch `LD-310-…`), bằng đọc/grep code; **chưa chạy test**.
Ký hiệu: ✅ hoàn thành (có code + test) · 🟡 đang triển khai/một phần · ❌ chưa triển khai (không thấy trong code) · ❔ chưa đủ bằng chứng.
Quy tắc: mọi task phải đối chiếu (1) yêu cầu giảng viên ở đây, (2) code hiện tại, (3) acceptance criteria Jira. Mâu thuẫn → báo cáo và hỏi chủ dự án trước khi triển khai.

## Mục tiêu
Hệ thống tài liệu tự cập nhật có AI cho đội kỹ sư: phát hiện documentation drift từ Pull Request (AST + RAG + LLM), sinh tài liệu từ code theo template, tự cập nhật khi code đổi, và đưa qua workflow Staff review → Manager approval, có change log theo vai trò (AI/Staff/Manager) và rollback.

## A. Functional requirements

### 1. Developer
| Yêu cầu | TT | Bằng chứng / ghi chú |
|---|---|---|
| Register/login/logout email+password | ✅ | `UserRegistrationController`, `UserLoginController`, `UserLoginLogoutTest` |
| Login GitHub OAuth | 🟡 | `GitHubOAuth2UserService`, test có; thay đổi OAuth redirect đang uncommitted |
| Profile & notification preferences | ❌ | `Profile.jsx`, `NotificationPreferences.jsx` chỉ là **demo** (state cục bộ, thông báo "Demo only / Backend is not connected"), không gọi API |
| Kết nối GitHub (OAuth/App), cấp scope, ngắt kết nối | ✅ | `GitHubConnectionController`, `GitHubConnectionControllerTest`, `GitHubConnection.jsx` |
| Chọn repo, thêm vào workspace; xem trạng thái/default branch/last sync | ✅ | `RepositoryController`, `RepositoryManagement.jsx`, `RepositoryManagementServiceTest` |
| Re-sync thủ công | ✅ | `RepositorySyncController`, `RepositorySyncApiTest` |
| Xem danh sách PR & commit đã ingest | ❌/🟡 | Bảng `github_pull_requests/github_commits` + `GitHubClientPullRequestApiTest`, nhưng không có controller/UI liệt kê |
| Thông báo khi token/webhook hỏng | ❌ | Không có webhook/notification code |
| Sinh tài liệu (file/module/repo), chọn template | ✅ | `DocumentationGenerationController`, `ai-service/app/generator.py`, `DocumentationTemplates.jsx` |
| Xem coverage gaps (entity chưa có doc) | ❌ | Không thấy |
| Preview/edit draft, grounding evidence | 🟡 | `DocumentationManagement.jsx`: preview/edit/export chạy ở client; "Save draft" chỉ lưu trong state trang |
| **Lưu tài liệu & submit vào workflow từ UI** | ❌ | Frontend **không gọi** `POST /api/documentation/jobs/{id}/document`, `POST /api/document-workflows` hay `/submit` (grep toàn `frontend/src`). API backend có, UI chưa nối → Staff Queue chỉ có dữ liệu nếu tạo qua API |
| Xem trạng thái workflow | 🟡 | Có "Approval History" + chọn workflow; "Published" không có trong enum (chỉ `APPROVED`) |
| Tự cập nhật doc khi PR/commit đổi; bật/tắt auto-update; xem diff trigger | ❌ | Không có webhook/GitHub Actions/auto-update; chỉ có drift analysis thủ công |
| Compare AI-update vs published; accept/edit/dismiss | 🟡 | `review-comparison` endpoint + `DocumentationSuggestionReview.jsx` (LD-312); "dismiss" ❔ |
| Regenerate on demand | ❔ | Có thể gọi generate lại; chưa xác nhận luồng "re-update entity" |
| Drift alerts từ PR, evidence, classification (Referential/Signature/Semantic), severity | ✅ | `ai-service/app/drift*.py`, `DriftAnalysisController`, `DocumentationDrift.jsx`, test drift |
| Trigger drift analysis thủ công; lịch sử drift | ✅/🟡 | `POST …/drift/analyze`, `GET …/drift/reports`; "resolution status" ❔ |
| Version timeline, diff 2 version, role AI/Staff/Manager, rollback | 🟡 | Backend: AI service `versions.py`, `/documents/{id}/versions|history`, rollback ở workflow. **UI Versions/Compare/Restore chỉ là state React cục bộ** (mất khi reload, UI tự ghi chú); frontend không gọi `/documents/*` |
| Knowledge base: search doc + code entity | 🟡 | `DocumentationSearch*` (có test service); điều hướng doc↔code, relationship ❌ (chỉ có bảng SQL) |

### 2. Staff
| Yêu cầu | TT | Bằng chứng |
|---|---|---|
| Queue chờ review, mở doc + evidence, so sánh với bản approved | ✅ | `StaffReviewQueue.jsx`, `/document-workflows/staff/queue`, `review-evidence`, `review-comparison`, `tests/test_staff_review_queue.py` |
| Claim/release/reassign | ✅ | endpoint + `DocumentWorkflowServiceTest` |
| Comment/request changes, edit nhỏ, approve → manager, reject về author | ✅ | `staff-review`, `PUT …/document`, status `CHANGES_REQUESTED` |
| Comment theo từng section | ❔ | Chưa xác nhận (comment cấp document) |
| Verify theo template / nhất quán code | 🟡 | Do con người thực hiện; có evidence hỗ trợ |
| Filter/sort queue theo repo/template/severity/date | ❔ | UI chỉ thấy phân trang (`page`,`size`) |
| Lịch sử review & trạng thái | ✅ | `history`, `history-accessible` |

### 3. Manager
| Yêu cầu | TT | Bằng chứng |
|---|---|---|
| Queue chờ approval, xem comment + evidence + audit trail | ✅ | `ManagerApprovalQueue.jsx`, `/manager/queue`, `/evidence`, `/history`, `tests/test_manager_approval.py` |
| Approve / reject / rollback | ✅ | `approve`, `reject`, `rollback` |
| Publish/commit vào repo chỉ sau approval | ❔ | Không thấy code commit tài liệu lên GitHub |
| Cấu hình loại doc cần approval; merge policy (warn/block PR) | ❌ | Không thấy |
| Delegate/reassign approval cho manager khác | ❌ | `reassign` chỉ cho **ADMINISTRATOR** chuyển claim review giữa các Staff (`DocumentWorkflowService.reassign`); không có reassign cho Manager và frontend không có UI reassign |

### 4. Technical Lead / Documentation Owner
| Yêu cầu | TT | Ghi chú |
|---|---|---|
| Collections, ownership, drift policy/threshold | ❌ | Chỉ có `/api/documentation/drift/severity-rules` (đọc) |
| Health dashboard, quality metrics, dependency graph, export report | ❌ | Không thấy |
| Template CRUD, default templates, preview | ✅ | `DocumentationTemplateController`, `templates.py`, `DocumentationTemplates.jsx`, `tests/test_frontend_templates.py` |
| Clone template, template versioning/rollback, gán default cho collection | ❔ | Chưa xác nhận |
| Auto-update policy, lọc change log theo role/date | ❌ | Không thấy |
| Technical review endpoint | ❌ | Chỉ có permission `DOCUMENT_TECHNICAL_REVIEW` |

### 5. Administrator
| Yêu cầu | TT | Ghi chú |
|---|---|---|
| Quản lý user/role/permission | 🟡 | Backend ✅ (`AdminUserController`, `AdminRoleController` + test); **không có UI admin** trong frontend |
| Quản lý workspace & repository | 🟡 | Backend ✅; UI `RepositoryManagement` có chọn workspace, add/sync/remove/move repo; **không có UI tạo workspace / quản lý member** (chỉ `GET /api/managed-workspaces`) |
| Cấu hình GitHub App/OAuth | 🟡 | Qua biến môi trường, không có UI admin |
| GitHub Actions/webhook, Jira/Slack/GitLab | ❌ | Không thấy |
| Ngôn ngữ hỗ trợ, template/trigger mặc định, AI settings, retention, indexing | ❌ | Analyzer hỗ trợ Python/Java (tree-sitter-java) nhưng không có màn cấu hình |
| Giám sát job/pipeline, audit log, analytics, notification policy | 🟡 | `document_workflow_audit` + `/documentation/jobs/*`; không có dashboard admin |

## B. Non-functional requirements
| NFR | TT | Ghi chú |
|---|---|---|
| Drift ≤2 phút/PR (≤100k LOC); 20 PR đồng thời; API ≤2s; search ≤1s; 99.5% availability | ❔ | Không có test hiệu năng/tải |
| Retry job AI; DLQ; Kafka consumers/event-driven | ❌ | Không có Kafka/RabbitMQ/DLQ; `jobs.py` là job nội bộ |
| Horizontal scaling AI | ❔ | AI Service lưu file JSON → khó scale ngang |
| Drift deterministic | 🟡 | Rule-based (`drift_rules.py`, `drift_severity.py`); chưa có test determinism riêng đã xác nhận |
| Audit log & traceability (role, commit/PR, timestamp) | ✅/🟡 | `DocumentWorkflowAudit` (+actor role, V4); "tamper-evident" ❔ |
| Auth OAuth2/OIDC; RBAC | 🟡 | Session + GitHub OAuth2, RBAC role/permission ✅; không dùng OIDC/JWT |
| HTTPS/TLS | ❔ | Compose chạy HTTP; `SESSION_COOKIE_SECURE` cấu hình được |
| Encrypted secrets | ✅ | `TokenEncryptor`, `EncryptedStringConverter` + test; secret qua env |
| Admin operations audit | 🟡 | Chưa xác nhận cho thao tác admin user/role |
| Microservice + REST + OpenAPI | ✅ | 4 service, `OpenApiConfig`/springdoc, FastAPI docs |
| CI/CD build+test | 🟡 | `.github/workflows/ci.yml` (build/test); không có deploy; backend/UI-int tests chạy trong CI ❔ |
| UI responsive desktop/tablet; ≤3 thao tác review | ❔ | Chưa kiểm tra |
| Severity hiển thị trực quan | ✅ | `DocumentationDrift.jsx`, `test_frontend_drift.py` |
| GitHub chính; mở rộng GitLab/Azure | ✅/❌ | GitHub ✅; GitLab chưa (chỉ yêu cầu "extensible") |
| AI: grounding evidence, confidence score, human review | ✅ | `evidence.py`, `confidence.py`, workflow bắt buộc review |
| Auto-update phải qua Staff+Manager trừ khi auto-apply | ❌ | Chưa có auto-update |
| Rollback bất kỳ version | 🟡 | Có rollback; "bất kỳ version" ❔ |

## C. Technology/Deliverables (mục e, f, g)
- ✅ Spring Boot microservices, Python FastAPI AI, PostgreSQL, Docker, React (Vite).
- ❌ Redis (chỉ tên `OAuthStateStore`, không dùng Redis — chưa xác minh sâu), Kafka/RabbitMQ.
- Deliverables: API backend ✅, web app 🟡, AI engine ✅, PostgreSQL ✅ (2 DB riêng + `workspace`, không phải "multi-tenant isolated schema").
- Tài liệu bắt buộc (UML, SRS, thiết kế, báo cáo): Confluence/`Docs/<member>/FR*.md`; UML/Detail Design ❔.

## D. Mâu thuẫn / điểm lạ cần chủ dự án quyết định
1. **Đề cương nhắc Zalo OA Webhook, VietQR Payment, Mobile App (Task Package 3), "Customers"** — không liên quan LivingDocs, không có trong code; có vẻ copy từ đề tài khác. Cần xác nhận có bị bỏ qua không.
2. **Kafka/RabbitMQ/Redis/DLQ** bắt buộc trong NFR nhưng code không dùng → cần quyết định phạm vi.
3. **OAuth2/OIDC & JWT** vs thực tế **session + CSRF cookie**.
4. **Trạng thái "Published"** trong đề cương vs enum workflow chỉ có `APPROVED`; chưa có bước publish/commit lên repo.
5. **"Multi-tenant isolated schema"** vs kiến trúc hiện tại (2 DB, tách theo workspace).
6. **Auto-update khi PR/commit đổi + GitHub Actions** là điểm cốt lõi của đề cương nhưng **chưa có** (chỉ drift analysis gọi tay).
7. **Manager delegate/reassign** (đề cương) — code chỉ có Administrator reassign claim của Staff; không có cho Manager.
8. **Reject → trả về revise** (đề cương mục Manager): workflow `REJECTED` là trạng thái cuối, `submit` chỉ nhận `DRAFT`/`CHANGES_REQUESTED` (`DocumentWorkflowService.submit`) nên tài liệu bị Manager reject không thể sửa và nộp lại.
9. **Accept/dismiss suggestion** (đề cương Developer) — UI `DocumentationSuggestionReview.jsx` ghi rõ không có API accept/dismiss; chỉ có edit khi `CHANGES_REQUESTED`.
10. **Staff edit nhỏ khi review** (đề cương Staff) — Staff UI/API không cho sửa nội dung; chỉ owner sửa sau khi bị request changes.
