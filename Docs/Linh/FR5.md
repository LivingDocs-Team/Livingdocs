# FR-AI-05 Mẫu tài liệu (documentation templates)

| Mục | Nội dung |
|---|---|
| Story Jira | LD-96 Implement Documentation Templates; LD-223 (LD-224 – LD-228) |
| Task đã làm | LD-97 Liệt kê các mẫu, LD-98 Chọn mẫu, LD-99 Áp dụng mẫu, LD-100 Quản lý mẫu; LD-227 Phiên bản mẫu, LD-228 Kiểm thử quản lý mẫu |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service (`app/templates.py`, `app/models.py`, `main.py`); GitHub Integration Service (`DocumentationTemplateController`, `DocumentationTemplateService`); Backend BFF (chuyển tiếp `PUT`; quy tắc quyền route trong `ApiRoutePermissions`); Frontend (`DocumentationTemplates.jsx`, `templateApi.js`, `DocumentationManagement.jsx`) |
| Tác nhân | Người dùng đã đăng nhập |

## 1. Mô tả

Người dùng xem các mẫu tài liệu có sẵn, chọn một mẫu trước khi sinh tài liệu, và có thể tạo, sửa, xoá mẫu riêng. Mẫu quyết định tài liệu của mỗi file gồm **những mục nào, theo thứ tự nào**, và **phong cách viết** mà AI phải theo. Tài liệu sinh ra luôn đúng mẫu đã chọn.

LD-227: mỗi lần sửa mẫu riêng lưu một **phiên bản mới**; các phiên bản cũ được giữ nguyên, xem lại được, dùng lại được để sinh tài liệu và khôi phục được (khôi phục cũng tạo phiên bản mới, không xoá lịch sử). Job, báo cáo và tài liệu ghi lại phiên bản mẫu đã dùng.

Đối chiếu task của LD-223 với yêu cầu: LD-224 List Available Documentation Templates = FR-AI-05.4; LD-225 Create and Edit Documentation Templates = FR-AI-05.11 – 05.13; LD-226 Define Documentation Template Structure = FR-AI-05.1 – 05.2, 05.7; LD-227 Manage Documentation Template Versions = FR-AI-05.15 – 05.20; LD-228 Test Documentation Template Management = mục 8.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AI-05.1 | Một mẫu gồm: `id`, `name` (1–80 ký tự, không trống, **không trùng** không phân biệt hoa thường), `description` (tối đa 300 ký tự), `instructions` (hướng dẫn viết cho AI, 1–4.000 ký tự, không trống), `sections` (ít nhất 1 mục, có thứ tự), `built_in`, `created_at`, `updated_at`. Khoảng trắng đầu cuối được cắt. |
| FR-AI-05.2 | Mục cho phép: `Overview`, `Classes`, `Functions`, `API Endpoints`. Nhận mọi kiểu hoa thường (`api endpoints`) và lưu theo cách viết chuẩn. Mục lạ hoặc lặp → từ chối, báo mục nào sai và các mục được phép. |
| FR-AI-05.3 | Ba mẫu có sẵn, chỉ xem được, không sửa hay xoá: `default` "Standard technical docs" (Overview, Classes, Functions, API Endpoints; giải thích mục đích, từng tham số, giá trị trả về, không bịa hành vi); `api-reference` "API reference" (Overview, API Endpoints; chỉ API công khai: method, path, mục đích, bảng tham số, request, response, ví dụ gọi); `brief` "Brief summary" (Overview, Classes, Functions; tối đa 2 câu mỗi mục). |
| FR-AI-05.4 | **Xem mẫu (LD-97):** danh sách gồm mẫu có sẵn trước (theo thứ tự trên), rồi mẫu riêng theo tên A–Z. Xem được từng mẫu và danh sách mục cho phép (kèm loại thực thể mỗi mục mô tả: Classes → class, method; Functions → function; API Endpoints → endpoint). |
| FR-AI-05.5 | **Chọn mẫu (LD-98):** trang Documentation hiện mỗi mẫu là một thẻ chọn (radio): tên, nhãn `Built-in` hoặc `Custom`, mô tả, các mục nối bằng `→`. Bên dưới là chi tiết mẫu đang chọn: "Sections in every file" và "Writing instructions". Mặc định chọn `default`. Mẫu được gửi khi bấm Generate (`{"templateId": "<id>", "outputLanguage": "vi"}`). |
| FR-AI-05.6 | Không tải được danh sách mẫu từ server → vẫn hiện 3 mẫu có sẵn kèm dòng "Could not load templates from the server. Showing the built-in templates." Chưa đăng nhập thì không gọi API. Mẫu đang chọn không còn trong danh sách → báo lỗi và khoá nút Generate. |
| FR-AI-05.7 | **Áp dụng mẫu (LD-99):** tài liệu mỗi file chỉ có các mục của mẫu, đúng thứ tự của mẫu (mục không có nội dung thì không in). Prompt nói rõ: "This template contains these sections, in order: …. Fill in: …. Leave these empty (they are not part of the template): …". `instructions` của mẫu được đưa vào prompt làm phong cách viết. |
| FR-AI-05.8 | Cảnh báo "AI gave no description" và điểm tin cậy (FR-AI-04) chỉ tính các thực thể thuộc mục của mẫu (ví dụ `api-reference` chỉ chấm endpoint). |
| FR-AI-05.9 | Khi tạo job, mẫu được **chụp lại**: job lưu `template_id`, `template_name`, `template_sections`; báo cáo lưu `template_id`, `template_name`. Sửa hoặc xoá mẫu sau đó không ảnh hưởng job đã tạo. Trang tổng quan ghi "Mẫu tài liệu: **<tên>**"; frontend báo "Documentation generated from <repo> using the "<tên>" template." |
| FR-AI-05.10 | Sinh tài liệu với mẫu không tồn tại → GitHub Integration trả `400 TEMPLATE_NOT_FOUND`; frontend tải lại danh sách mẫu và chọn lại `default`. |
| FR-AI-05.11 | **Quản lý mẫu (LD-100):** nút "Manage templates" mở khung quản lý: danh sách mẫu riêng (tên, các mục, nút Edit, Delete), nút "New template", ghi chú "Built-in templates are read-only. Custom templates are shared by everyone in this LivingDocs installation." |
| FR-AI-05.12 | Form tạo/sửa: Name, Description, Sections (checkbox cho 4 mục, mặc định chỉ Overview; thứ tự = thứ tự tick, đổi bằng nút ↑ ↓), "Writing instructions for the AI". Kiểm tra trước khi gửi: có tên, có hướng dẫn, ít nhất 1 mục. Lưu xong: báo `Template "<tên>" saved.`, tải lại danh sách và chọn mẫu vừa lưu. Lỗi từ server (ví dụ trùng tên) hiện đúng thông báo của server. |
| FR-AI-05.13 | Xoá cần bấm 2 lần ("Delete" → "Confirm delete"). Xoá xong báo `Template "<tên>" deleted.`; nếu đang chọn mẫu đó thì chọn lại `default`. |
| FR-AI-05.15 | (LD-227) Mỗi mẫu có `version` (số phiên bản hiện tại). Tạo mẫu → phiên bản 1. Mỗi `PUT` làm **đổi nội dung** (`name`, `description`, `instructions`, `sections`) lưu phiên bản tiếp theo (2, 3, …) với `created_at`; `PUT` với nội dung giống hệt không tạo phiên bản mới. Mẫu có sẵn luôn ở phiên bản 1. |
| FR-AI-05.16 | (LD-227) `GET /templates/{id}/versions`: mọi phiên bản, mới nhất trước; mỗi phiên bản gồm `template_id`, `version`, `name`, `description`, `instructions`, `sections`, `created_at`, `restored_from`. `GET /templates/{id}/versions/{n}`: một phiên bản. Phiên bản đã lưu không bao giờ bị sửa. |
| FR-AI-05.17 | (LD-227) `POST /templates/{id}/versions/{n}/restore`: lưu nội dung của phiên bản `n` thành **phiên bản mới** (`restored_from = n`), trả mẫu hiện tại; khôi phục đúng phiên bản hiện tại không tạo phiên bản mới. Tên của phiên bản cũ đã bị mẫu khác dùng → `409`; mẫu có sẵn → `403`. |
| FR-AI-05.18 | (LD-227) Sinh tài liệu có thể chọn phiên bản cũ bằng `template_version` trong body `/generate` (mặc định: phiên bản hiện tại); phiên bản không có → `404` "Template '<id>' version <n> not found". Job (`template_version`), báo cáo (`template_version`) và tài liệu lưu (`template_version`) ghi phiên bản đã dùng. |
| FR-AI-05.19 | (LD-227) Lịch sử phiên bản được lưu cùng file `TEMPLATES_FILE` (khoá `history`). File cũ chưa có lịch sử → mỗi mẫu được đọc là phiên bản 1. Xoá mẫu thì xoá luôn lịch sử của nó (tài liệu đã sinh vẫn giữ bản chụp mẫu, FR-AI-05.9). |
| FR-AI-05.20 | (LD-227) GitHub Integration chuyển tiếp `GET /api/documentation/templates/{id}/versions`, `GET …/versions/{n}`, `POST …/versions/{n}/restore`. Backend BFF: xem phiên bản cần quyền xem màn hình Templates (#22 R: Developer, Staff, Technical Lead); khôi phục cần quyền sửa (#22 U: Technical Lead). |
| FR-AI-05.14 | Mẫu riêng được lưu vào file JSON `TEMPLATES_FILE` (mặc định `data/templates.json`; Docker: `/app/data/templates.json` trên volume `ai-templates`), ghi kiểu nguyên tử (ghi file tạm rồi thay), nên còn sau khi khởi động lại. `TEMPLATES_FILE` rỗng → chỉ lưu trong bộ nhớ. File hỏng → đổi tên thành `templates.corrupt-<thời gian>.json`, service chạy với 3 mẫu có sẵn. File không thể ghi đè mẫu có sẵn. |

## 3. API

AI Service (cổng 8001):

| Method | Endpoint | Kết quả |
|---|---|---|
| GET | `/templates` | Danh sách mẫu |
| GET | `/templates/sections` | `{"sections": [...], "documents": {"Classes": ["class", "method"], ...}}` |
| GET | `/templates/{id}` | Một mẫu |
| POST | `/templates` | `201` + mẫu mới (`id` = 8 ký tự hex) |
| PUT | `/templates/{id}` | Mẫu đã sửa (`created_at` giữ nguyên, `updated_at` mới) |
| DELETE | `/templates/{id}` | `204` |
| GET | `/templates/{id}/versions` | (LD-227) Các phiên bản, mới nhất trước |
| GET | `/templates/{id}/versions/{n}` | (LD-227) Một phiên bản |
| POST | `/templates/{id}/versions/{n}/restore` | (LD-227) Mẫu hiện tại sau khi khôi phục (phiên bản mới) |

Frontend gọi qua Backend BFF → GitHub Integration, cùng cấu trúc dưới `/api/documentation/templates` (`GET`, `GET /sections`, `GET /{id}`, `POST`, `PUT /{id}`, `DELETE /{id}`, và từ LD-227 `GET /{id}/versions`, `GET /{id}/versions/{n}`, `POST /{id}/versions/{n}/restore`). Body POST/PUT:

```json
{"name": "Onboarding", "description": "For new team members",
 "instructions": "One sentence per function.", "sections": ["Functions", "Overview"]}
```

## 4. Luồng chính

1. Người dùng mở trang Documentation; frontend tải `/api/documentation/templates` và hiện các thẻ mẫu.
2. Người dùng chọn mẫu (hoặc tạo mẫu mới trong "Manage templates"), xem chi tiết mục và hướng dẫn.
3. Bấm Generate: `templateId` đi qua GitHub Integration thành `template_id` của `POST /generate`.
4. AI Service chụp lại mẫu, sinh tài liệu đúng các mục và thứ tự của mẫu; trang báo đã dùng mẫu nào.

## 5. Luồng lỗi

| Trường hợp | AI Service | GitHub Integration (trả cho frontend) |
|---|---|---|
| Mẫu sai (mục lạ, lặp, tên trống, quá dài) | 422 | `400 TEMPLATE_INVALID`, message nêu trường và lý do, ví dụ `sections: Value error, unknown section 'Changelog'; …` |
| Trùng tên | 409 | `409 TEMPLATE_NAME_TAKEN` |
| Sửa/xoá mẫu có sẵn | 403 | `403 TEMPLATE_READ_ONLY` |
| Mẫu không tồn tại | 404 | `404 TEMPLATE_NOT_FOUND` |
| Phiên bản mẫu không tồn tại (LD-227) | 404 | `404 TEMPLATE_NOT_FOUND`, message "Documentation template version not found." |
| Khôi phục phiên bản mà tên đã bị mẫu khác dùng (LD-227) | 409 | `409 TEMPLATE_NAME_TAKEN` |
| Khôi phục mẫu có sẵn (LD-227) | 403 | `403 TEMPLATE_READ_ONLY` |
| Sinh tài liệu với mẫu không tồn tại | 404 ở `/generate` | `400 TEMPLATE_NOT_FOUND` |
| Cài đặt sinh tài liệu sai (ví dụ ngôn ngữ) | 422 ở `/generate` | `400 GENERATION_REQUEST_INVALID` |
| AI Service không phản hồi / lỗi 5xx | – | `502 AI_SERVICE_FAILED`; trả về sai định dạng → `502 AI_SERVICE_INVALID_RESPONSE` |

## 6. Quy tắc nghiệp vụ

- Mẫu dùng chung cho mọi người dùng (AI Service không có tài khoản người dùng).
- Body gửi sang AI Service chỉ gồm các trường có giá trị (bỏ trường `null`).
- Backend BFF cho phép `GET`, `POST`, `PUT`, `DELETE` tới `/api/documentation/**` và yêu cầu CSRF token cho các lệnh thay đổi dữ liệu.

## 7. Tiêu chí chấp nhận

- **AC-AI-05.1:** `GET /templates` → 3 phần tử đầu là `default`, `api-reference`, `brief`; mẫu riêng sau đó theo tên A–Z.
- **AC-AI-05.2:** Mỗi mẫu có sẵn sinh ra tài liệu có đúng các tiêu đề `##` của mẫu, đúng thứ tự (ví dụ `api-reference` → "Tổng quan", "API Endpoints").
- **AC-AI-05.3:** Mẫu riêng `["API Endpoints", "Functions", "Overview"]` → tiêu đề theo đúng thứ tự đó; không có lớp nào trong tài liệu.
- **AC-AI-05.4:** Tạo mẫu với mục `Changelog` → `422` (qua GitHub Integration: `400 TEMPLATE_INVALID`); tạo `"standard TECHNICAL docs"` → `409`.
- **AC-AI-05.5:** `PUT`/`DELETE` mẫu `default` → `403`.
- **AC-AI-05.6:** Tạo mẫu, khởi động lại service → mẫu vẫn còn.
- **AC-AI-05.7:** Tạo job với mẫu riêng, xoá mẫu, chạy job → job vẫn `completed` theo mẫu cũ.
- **AC-AI-05.9 (LD-227):** Tạo mẫu (phiên bản 1), sửa mục thành `["Overview"]` (phiên bản 2), sửa hướng dẫn (phiên bản 3) → `GET …/versions` trả `[3, 2, 1]`, phiên bản 1 vẫn có `["Overview", "Functions"]`.
- **AC-AI-05.10 (LD-227):** Khôi phục phiên bản 1 → mẫu ở phiên bản 3 (mới), nội dung giống phiên bản 1, `restored_from = 1`; lịch sử còn đủ phiên bản 1 và 2.
- **AC-AI-05.11 (LD-227):** Sinh tài liệu với `template_version = 1` sau khi mẫu đã ở phiên bản 2 → tài liệu theo các mục của phiên bản 1; job, báo cáo, tài liệu lưu ghi `template_version = 1`.
- **AC-AI-05.8:** Trên giao diện: chọn "API reference", Generate → request có `templateId = "api-reference"`, thông báo nêu tên mẫu; tạo "Onboarding" (Functions trước Overview) → mẫu được chọn ngay; xoá cần xác nhận và trả lựa chọn về mẫu mặc định.

## 8. Kiểm thử

- AI Service (LD-227): `ai-service/tests/test_template_versions.py` (11 test: phiên bản 1, mỗi lần sửa một phiên bản, nội dung giống không tạo phiên bản, khôi phục, trùng tên khi khôi phục, mẫu có sẵn, 404, job/báo cáo/tài liệu ghi phiên bản, sinh theo phiên bản cũ, lưu file và file cũ, xoá mẫu).
- AI Service: `ai-service/tests/test_templates.py` (24 test: xem, kiểm tra hợp lệ, trùng tên, sửa/xoá, mẫu có sẵn chỉ đọc, lưu file và khởi động lại, file hỏng, tài liệu đúng mục và thứ tự, phạm vi prompt và điểm, chụp mẫu cho job).
- GitHub Integration: `DocumentationTemplateServiceTest` (thêm `listsReadsAndRestoresTemplateVersions`, `mapsMissingVersionAndReadOnlyRestore`), `DocumentationTemplateControllerTest` (thêm `listsReadsAndRestoresVersions`), `DocumentationGenerationServiceTest.reportsUnknownTemplateAsBadRequest`.
- Backend: `ApiRoutePermissionsTest` (quyền của 3 route phiên bản theo từng role).
- Frontend: `tests/test_frontend_templates.py` (Playwright, 3 test: xem và chọn mẫu, quản lý mẫu riêng, dự phòng khi server lỗi).
