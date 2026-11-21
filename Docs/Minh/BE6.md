# FR-LD-273 Cấu hình hệ thống LivingDocs

| Mục | Nội dung |
|---|---|
| **Story Jira** | LD-273 – Implement System Configuration |
| **Task liên quan** | Configure AI & Retrieval Settings; Configure Automatic Update Policies; Configure Documentation Generation Settings; Configure GitHub Actions & Webhooks; Configure GitHub App & OAuth |
| **Thành phần** | GitHub Integration Service; AI Service; Frontend; GitHub Actions CI; cấu hình môi trường (`application.yml`, `.env`) |
| **Tác nhân** | Quản trị viên/vận hành hệ thống; người dùng kết nối GitHub; hệ thống AI sinh tài liệu và xử lý cập nhật tự động |
| **Phạm vi** | Cấu hình tích hợp GitHub, ngôn ngữ mã nguồn, sinh tài liệu, chính sách cập nhật tự động, lưu trữ log, mô hình AI và cơ chế indexing/retrieval. |

## 1. Mô tả

LD-273 yêu cầu xây dựng khả năng cấu hình các thành phần vận hành của LivingDocs, bao gồm tích hợp GitHub, ngôn ngữ mã nguồn được hỗ trợ, thiết lập sinh tài liệu, chính sách cập nhật tự động, thời hạn lưu change log/audit log, mô hình AI, embedding model, confidence threshold, token budget và cấu hình indexing/retrieval.

Qua đối chiếu mã nguồn trong gói `Livingdocs-LD-273-Implement-System-Configuration`, hệ thống hiện có một số cơ chế cấu hình ở cấp triển khai và một số chức năng cấu hình ở cấp ứng dụng:

- GitHub App, OAuth, webhook secret, URL dịch vụ, CORS và kết nối cơ sở dữ liệu được cấu hình qua biến môi trường và `application.yml`.
- Người dùng có thể kết nối/ngắt kết nối tài khoản GitHub qua giao diện GitHub Integration.
- Ngôn ngữ mã nguồn được nhận diện theo phần mở rộng file bằng danh sách ánh xạ cố định trong `LanguageDetector`.
- Thiết lập sinh tài liệu có thể lựa chọn template; người dùng có thể tạo, sửa và xóa custom template.
- AI model, số token tối đa, timeout và số lần thử được đọc từ biến môi trường của AI Service.
- Retrieval hiện sử dụng TF-IDF cosine similarity và các hệ số/ràng buộc được định nghĩa cố định trong mã nguồn; chưa thấy cấu hình embedding model hoặc giao diện quản trị các tham số retrieval.
- Webhook nhận sự kiện GitHub và kiểm tra chữ ký; luồng ingestion xử lý các thay đổi từ GitHub.
- Trong phạm vi mã nguồn đã kiểm tra, chưa tìm thấy màn hình/cơ chế cấu hình tập trung cho retention của change log/audit log hoặc toàn bộ automatic update policies.

Vì vậy, tài liệu mô tả cả yêu cầu nghiệp vụ của LD-273 và phạm vi đã có bằng chứng triển khai; các phần chưa được xác nhận được đánh dấu rõ, không xem yêu cầu Jira là chức năng đã hoàn thành.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| **FR-LD-273.1** | **Cấu hình GitHub App:** Cho phép khai báo thông tin GitHub App gồm Client ID, Client Secret, App Slug và Redirect URI để LivingDocs thực hiện OAuth/installation flow. Trong code hiện tại, các giá trị được đọc từ biến môi trường thông qua `application.yml`. |
| **FR-LD-273.2** | **Cấu hình OAuth:** Cấu hình URL OAuth, GitHub API URL và redirect URL; xử lý callback sau khi người dùng cấp quyền; cho phép xem trạng thái kết nối và ngắt kết nối GitHub. |
| **FR-LD-273.3** | **Cấu hình webhook:** Khai báo webhook secret để xác minh chữ ký `X-Hub-Signature-256`; nhận sự kiện webhook từ GitHub App tại endpoint `/api/github/webhook`. |
| **FR-LD-273.4** | **Cấu hình GitHub Actions:** Hỗ trợ quy trình CI của repository thông qua GitHub Actions workflow. Trong code được cung cấp có workflow CI (`.github/workflows/ci.yml`); chưa thấy giao diện cấu hình workflow hoặc chính sách Actions trong LivingDocs. |
| **FR-LD-273.5** | **Cấu hình ngôn ngữ mã nguồn:** Xác định các ngôn ngữ được hỗ trợ khi đồng bộ/phân tích repository. Hiện tại danh sách phần mở rộng và ngôn ngữ tương ứng được khai báo cố định trong `LanguageDetector`. |
| **FR-LD-273.6** | **Cấu hình sinh tài liệu:** Cho phép lựa chọn template khi sinh tài liệu; template xác định tên, mô tả, hướng dẫn viết và danh sách section. Hệ thống có template built-in và custom template. |
| **FR-LD-273.7** | **Cấu hình cập nhật tài liệu tự động:** Nhận các sự kiện thay đổi từ GitHub webhook và chuyển tiếp vào luồng ingestion/đánh giá thay đổi tài liệu. Yêu cầu cấu hình trigger và policy tự động ở cấp quản trị chưa được xác nhận là đã có màn hình hoặc kho cấu hình riêng. |
| **FR-LD-273.8** | **Cấu hình retention:** Yêu cầu cho phép cấu hình thời gian lưu change log và audit log. Chưa tìm thấy biến cấu hình, API hoặc màn hình quản trị retention tương ứng trong gói code đã kiểm tra. |
| **FR-LD-273.9** | **Cấu hình AI model:** Cho phép xác định model sinh tài liệu, API key, timeout và số lần thử. Code hiện tại hỗ trợ các biến môi trường `ANTHROPIC_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT`, `LLM_MAX_TOKENS` và `LLM_MAX_ATTEMPTS`. |
| **FR-LD-273.10** | **Cấu hình confidence threshold:** Hệ thống tính confidence score và phân loại `high`, `medium`, `low`. Ngưỡng hiện tại được định nghĩa cố định: high từ `0.75`, medium từ `0.50`; chưa thấy cơ chế cấu hình các ngưỡng này từ giao diện hoặc file cấu hình riêng. |
| **FR-LD-273.11** | **Cấu hình token budget:** Cho phép kiểm soát số token tối đa gửi cho AI model. Code hiện tại đọc `LLM_MAX_TOKENS`, mặc định `4096`. |
| **FR-LD-273.12** | **Cấu hình embedding model:** Yêu cầu cho phép lựa chọn embedding model phục vụ indexing/retrieval. Trong `retrieval.py` hiện tại, retrieval dùng TF-IDF cosine similarity, không thấy tích hợp embedding model hoặc tham số chọn embedding model. |
| **FR-LD-273.13** | **Cấu hình indexing:** Hệ thống xây dựng index từ class, method, function, endpoint trong các file phân tích hợp lệ và các tài liệu context được gửi kèm yêu cầu sinh tài liệu. |
| **FR-LD-273.14** | **Cấu hình retrieval:** Hệ thống tìm code liên quan và đoạn tài liệu liên quan dựa trên TF-IDF cosine similarity, identifier-aware tokenization và các bonus/threshold được định nghĩa trong code. Có API preview để xem index và kết quả retrieval. |

## 3. Các nhóm cấu hình

### 3.1. GitHub App và OAuth

Các thuộc tính GitHub được khai báo trong `GitHubProperties` với prefix `github`:

| Thuộc tính | Biến môi trường | Giá trị mặc định / Ý nghĩa |
|---|---|---|
| `client-id` | `GITHUB_CLIENT_ID` | Client ID của GitHub App; mặc định rỗng. |
| `client-secret` | `GITHUB_CLIENT_SECRET` | Client Secret; mặc định rỗng. |
| `app-slug` | `GITHUB_APP_SLUG` | Slug của GitHub App; mặc định `livingdocs-dev-hai`. |
| `redirect-uri` | `GITHUB_REDIRECT_URI` | Callback URI; mặc định `http://localhost:8082/api/github/callback`. |
| `oauth-base-url` | Không có biến riêng trong YAML hiện tại | Mặc định `https://github.com`. |
| `api-base-url` | Không có biến riêng trong YAML hiện tại | Mặc định `https://api.github.com`. |
| `webhook-secret` | `GITHUB_WEBHOOK_SECRET` | Secret dùng để xác minh webhook; mặc định rỗng. |

Các cấu hình bảo mật liên quan:

| Thuộc tính | Biến môi trường | Ý nghĩa |
|---|---|---|
| Token encryption key | `TOKEN_ENCRYPTION_KEY` | Khóa mã hóa token GitHub được lưu trữ. |
| Internal API secret | `GITHUB_INTEGRATION_INTERNAL_SECRET` | Secret dùng cho giao tiếp nội bộ giữa các service. |
| Frontend URL | `FRONTEND_URL` | URL frontend nhận redirect sau OAuth callback; để trống thì callback trả JSON. |
| CORS origins | `CORS_ALLOWED_ORIGINS` | Danh sách origin được phép gọi API từ trình duyệt, phân tách bằng dấu phẩy. |

Frontend GitHub Connection hỗ trợ:
- Xem trạng thái kết nối GitHub của người dùng.
- Bắt đầu OAuth authorization.
- Mở installation URL để cài GitHub App khi cần.
- Hiển thị trạng thái connected/disconnected hoặc authorization expired.
- Ngắt kết nối GitHub.

### 3.2. Webhook và GitHub Actions

Webhook endpoint được khai báo tại:

`POST /api/github/webhook`

Các header được sử dụng:

| Header | Mục đích |
|---|---|
| `X-GitHub-Event` | Loại event do GitHub gửi. |
| `X-GitHub-Delivery` | Mã định danh delivery, hỗ trợ nhận diện delivery trùng. |
| `X-Hub-Signature-256` | Chữ ký HMAC SHA-256 để xác minh payload. |

Quy tắc xử lý thể hiện trong `GitHubWebhookController`:

- Nếu `GITHUB_WEBHOOK_SECRET` chưa được cấu hình, endpoint trả `503` với mã `WEBHOOK_NOT_CONFIGURED`.
- Nếu chữ ký thiếu hoặc không hợp lệ, endpoint trả `401` với mã `WEBHOOK_SIGNATURE_INVALID`.
- Event `ping` được xác minh thành công sẽ trả `200` với trạng thái `PONG`.
- Thiếu `X-GitHub-Event` hoặc `X-GitHub-Delivery` sẽ trả lỗi `400`.
- Payload JSON không hợp lệ sẽ trả lỗi `400`.
- Event hợp lệ được chuyển tới `IngestionService.handleWebhook(...)`; kết quả trả `202` với một trong các trạng thái do service trả về, ví dụ `PROCESSED`, `DUPLICATE` hoặc `IGNORED`.

GitHub Actions:
- Repository có file `.github/workflows/ci.yml` dùng cho quy trình CI.
- Đây là workflow CI của source repository; không phải màn hình cho phép người quản trị LivingDocs chỉnh sửa cấu hình GitHub Actions.
- Trong các file đã kiểm tra chưa xác định được API quản lý workflow Actions từ LivingDocs.

### 3.3. Ngôn ngữ mã nguồn được hỗ trợ

`LanguageDetector` nhận diện ngôn ngữ dựa trên phần mở rộng file. Danh sách được khai báo cố định:

| Phần mở rộng | Giá trị language |
|---|---|
| `.java` | `java` |
| `.py` | `python` |
| `.js`, `.jsx`, `.mjs`, `.cjs` | `javascript` |
| `.ts`, `.tsx` | `typescript` |
| `.kt`, `.kts` | `kotlin` |
| `.go` | `go` |
| `.rb` | `ruby` |
| `.php` | `php` |
| `.cs` | `csharp` |
| `.c`, `.h` | `c` |
| `.cpp`, `.cc`, `.cxx`, `.hpp` | `cpp` |
| `.rs` | `rust` |
| `.swift` | `swift` |
| `.scala` | `scala` |
| `.sql` | `sql` |

Quy tắc:
- Phần mở rộng được chuyển về chữ thường trước khi tra cứu.
- File không có phần mở rộng, file ẩn như `.gitignore` hoặc phần mở rộng không có trong danh sách sẽ trả về `null`.
- Danh sách ngôn ngữ hiện được hard-code, chưa thấy API hoặc giao diện để quản trị viên thêm/bớt ngôn ngữ.

### 3.4. Thiết lập sinh tài liệu

Hệ thống có hai nhóm template:

**Template built-in**

| ID | Tên | Sections |
|---|---|---|
| `default` | Standard technical docs | Overview, Classes, Functions, API Endpoints |
| `api-reference` | API reference | Overview, API Endpoints |
| `brief` | Brief summary | Overview, Classes, Functions |

Template built-in được định nghĩa trong `ai-service/app/templates.py` và chỉ đọc, không cho sửa/xóa qua Template Manager.

**Custom template**

Người dùng có thể:
- Tạo template mới.
- Sửa template đã tạo.
- Xóa custom template.
- Khai báo name, description, instructions.
- Chọn một hoặc nhiều section.
- Thay đổi thứ tự section.

Các section hiện được hỗ trợ:
- `Overview`
- `Classes`
- `Functions`
- `API Endpoints`

Validation ở giao diện:
- Name không được để trống, tối đa 80 ký tự.
- Description tối đa 300 ký tự.
- Instructions không được để trống, tối đa 4.000 ký tự.
- Phải chọn ít nhất một section.

Custom template được lưu vào file JSON; đường dẫn mặc định là `data/templates.json`, có thể được truyền qua `TEMPLATES_FILE` nếu cấu hình ở môi trường chạy.

### 3.5. AI model và token budget

AI Service sử dụng Anthropic client trong `ai-service/app/generator.py`.

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---:|---|
| `ANTHROPIC_API_KEY` | Không có | API key; nếu không có thì generator chạy offline. |
| `LLM_MODEL` | `claude-sonnet-5-5` | Tên model dùng để sinh tài liệu. |
| `LLM_MAX_TOKENS` | `4096` | Số token tối đa cho mỗi lần gọi model. |
| `LLM_TIMEOUT` | `60` | Timeout của request tới model, tính bằng giây. |
| `LLM_MAX_ATTEMPTS` | `3` | Số lần thử tối đa do `DocGenerator` quản lý. |

Quy tắc:
- Có `ANTHROPIC_API_KEY`: AI Service khởi tạo `AnthropicClient` và gọi model đã cấu hình.
- Không có API key: generator chuyển sang chế độ offline, tài liệu được dựng từ dữ liệu phân tích thay vì gọi AI.
- `LLM_MAX_TOKENS` được chuyển sang kiểu integer trước khi truyền vào Anthropic client.
- Các giá trị trên là cấu hình môi trường, không phải thiết lập có thể thay đổi trực tiếp trong giao diện người dùng.

### 3.6. Confidence threshold

Confidence score được tính trong `ai-service/app/confidence.py`.

| Mức | Ngưỡng |
|---|---|
| `high` | Score >= `0.75` |
| `medium` | Score >= `0.50` và nhỏ hơn `0.75` |
| `low` | Score < `0.50` |

Các trọng số trong công thức AI-written description:

| Thành phần | Trọng số |
|---|---:|
| Input quality | `0.30` |
| Evidence grounding | `0.30` |
| Described | `0.20` |
| AI self-assessment | `0.20` |
| Phạt mỗi evidence ID không hợp lệ | `0.10`, tối đa `0.30` |

Các quy tắc bổ sung:
- Khi không có AI description (offline hoặc fallback), score dựa trên `0.60 × input_quality`.
- Entity thiếu evidence riêng bị nhân hệ số `0.70`.
- Score được giới hạn trong khoảng `[0, 1]` và làm tròn half-up đến 2 chữ số thập phân.
- Ngưỡng và trọng số hiện được định nghĩa trong code, chưa thấy tham số cấu hình bên ngoài.

### 3.7. Indexing và Retrieval

Trong `ai-service/app/retrieval.py`, index được tạo từ:

- Class và thông tin class (fields, methods, bases).
- Method và function.
- HTTP endpoint.
- Các đoạn tài liệu context được gửi trong `GenerateRequest.context`.

Tài liệu context được chia theo heading Markdown; nội dung heading bên trong fenced code block được bỏ qua. Mỗi passage giữ heading path, ví dụ `Shop > Cart`.

Cơ chế retrieval:
- Sử dụng TF-IDF cosine similarity.
- Tokenization nhận diện identifier theo camelCase và snake_case.
- Chuẩn hóa chữ thường và bỏ dấu tiếng Việt để hỗ trợ đối chiếu từ khóa.
- Có các bonus cho quan hệ gọi code, sử dụng class, quan hệ caller và đoạn tài liệu nhắc tới entity.
- Chỉ lấy các kết quả đạt `MIN_SCORE`.
- Mỗi file được truy xuất tối đa 4 code chunks và 3 documentation chunks.
- Các kết quả được gắn reference `C1...` cho code và `D1...` cho documentation để AI sử dụng làm evidence.

Các hằng số hiện có:

| Hằng số | Giá trị | Ý nghĩa |
|---|---:|---|
| `MAX_DOC_CHUNK_CHARS` | `1200` | Độ dài tối đa của một documentation chunk. |
| `MAX_EXCERPT_CHARS` | `600` | Độ dài excerpt tối đa. |
| `MIN_SCORE` | `0.05` | Điểm similarity tối thiểu để giữ kết quả. |
| `CALL_BONUS` | `0.25` | Bonus khi file gọi code được truy xuất. |
| `CLASS_BONUS` | `0.10` | Bonus khi file sử dụng class. |
| `CALLER_BONUS` | `0.20` | Bonus cho quan hệ caller. |
| `DOC_MENTION_BONUS` | `0.15` | Bonus khi passage tài liệu nhắc tới entity. |
| `COMMON_PATH_SHARE` | `0.8` | Tỷ lệ file dùng chung path term để xem term là phổ biến. |
| `COMMON_PATH_MIN_FILES` | `4` | Số file tối thiểu trước khi áp dụng lọc common path terms. |

API preview retrieval cho phép kiểm tra thống kê index và kết quả truy xuất mà không sinh hoặc lưu tài liệu.

## 4. API và điểm cấu hình

### 4.1. GitHub Integration Service

| Method | Endpoint | Kết quả | Mục đích |
|---|---|---|---|
| **GET** | `/api/github/authorize-url` | `AuthorizeUrlResponse` | Tạo URL OAuth/installation cho người dùng hiện tại (đọc user ID từ header `X-User-Id`). |
| **GET** | `/api/github/callback` | JSON hoặc redirect `302` | Nhận callback sau khi người dùng cấp quyền GitHub. |
| **GET** | `/api/github/connection` | `ConnectionResponse` | Xem trạng thái kết nối GitHub của người dùng. |
| **DELETE** | `/api/github/connection` | `204 No Content` | Thu hồi/ngắt kết nối GitHub. |
| **POST** | `/api/github/webhook` | `202 Accepted` hoặc lỗi | Nhận và xác minh webhook từ GitHub App. |

### 4.2. AI Service – generation và retrieval

| Method | Endpoint | Kết quả | Mục đích |
|---|---|---|---|
| **POST** | `/generate` | `202 Accepted` + Job | Khởi tạo job sinh tài liệu; request có thể chỉ định `template_id` và `output_language`. |
| **POST** | `/retrieval/preview` | `RetrievalPreview` | Xem thống kê index và các code/document chunks được retrieval cho từng file; không sinh hoặc lưu tài liệu. |
| **GET** | `/templates` | Danh sách `Template` | Lấy danh sách template built-in và custom. |
| **GET** | `/templates/sections` | `TemplateSections` | Lấy danh sách section được hỗ trợ. |
| **GET** | `/templates/{template_id}` | `Template` | Lấy chi tiết template. |
| **POST** | `/templates` | `201 Created` + `Template` | Tạo custom template. |
| **PUT** | `/templates/{template_id}` | `Template` | Cập nhật custom template. |
| **DELETE** | `/templates/{template_id}` | Kết quả xóa | Xóa custom template. |

**Lưu ý:** Frontend gọi các API template qua BFF path `/api/documentation/templates`; các endpoint AI Service ở bảng trên là route được khai báo trong `ai-service/main.py`. Mapping proxy giữa hai lớp được thực hiện ở backend, không phải endpoint trực tiếp của trình duyệt.

## 5. Luồng chính

### 5.1. Cấu hình và kết nối GitHub

1. Người vận hành khai báo GitHub App credentials, redirect URI, webhook secret và các thông tin môi trường trong `.env`/`application.yml`.
2. GitHub Integration Service nạp các giá trị cấu hình khi khởi động.
3. Người dùng mở trang GitHub Integration và chọn Authorize GitHub hoặc Install GitHub App.
4. Frontend gọi `/api/github/authorize-url`, sau đó chuyển trình duyệt tới URL GitHub trả về.
5. GitHub chuyển về `/api/github/callback`; service xử lý OAuth callback và lưu trạng thái kết nối.
6. Frontend gọi `/api/github/connection` để hiển thị trạng thái kết nối. Người dùng có thể ngắt kết nối bằng DELETE endpoint.

### 5.2. Tiếp nhận webhook và xử lý thay đổi

1. GitHub gửi webhook đến `POST /api/github/webhook`.
2. Service kiểm tra webhook secret và chữ ký `X-Hub-Signature-256`.
3. Service kiểm tra event header, delivery ID và JSON payload.
4. Event hợp lệ được chuyển tới `IngestionService.handleWebhook(...)`.
5. Ingestion service xử lý event và trả kết quả `PROCESSED`, `DUPLICATE` hoặc `IGNORED` theo tình huống.
6. Các thay đổi từ repository có thể được chuyển tiếp vào các luồng phân tích source change và documentation drift hiện có.

### 5.3. Cấu hình và sử dụng template sinh tài liệu

1. Frontend tải danh sách template.
2. Người dùng chọn template built-in hoặc custom template để sinh tài liệu.
3. Nếu cần, người dùng mở Template Manager để tạo, sửa hoặc xóa custom template.
4. Khi gửi yêu cầu sinh tài liệu, `template_id` được gửi tới AI Service trong `GenerateRequest`.
5. AI Service lấy template tương ứng và dùng instructions/sections của template khi tạo nội dung.
6. Template custom được lưu trong file JSON để sử dụng lại sau khi service khởi động lại.

### 5.4. Sinh tài liệu và retrieval

1. AI Service đọc cấu hình model từ biến môi trường.
2. Nếu có API key, generator sử dụng Anthropic client; nếu không, generator chạy offline.
3. AI Service xây dựng index từ kết quả phân tích code và tài liệu context.
4. Retrieval tìm các code chunks và documentation chunks có liên quan tới từng file.
5. Các kết quả retrieval được đưa vào evidence catalog và prompt sinh tài liệu.
6. Generator gọi model với `LLM_MODEL` và `LLM_MAX_TOKENS`; kết quả được chấm confidence theo quy tắc hiện tại.
7. Người vận hành có thể gọi `/retrieval/preview` để xem index và kết quả retrieval.

## 6. Luồng lỗi

| Trường hợp | HTTP / Kết quả | Xử lý |
|---|---|---|
| GitHub App credentials chưa được khai báo hoặc không hợp lệ | Lỗi ở bước tạo URL/callback hoặc gọi GitHub API | Frontend hiển thị lỗi kết nối; cấu hình phải được kiểm tra ở môi trường triển khai. |
| Người dùng từ chối OAuth | `400` với mã `GITHUB_ACCESS_DENIED` | Frontend hiển thị thông báo cho phép kết nối lại. |
| Webhook secret chưa cấu hình | `503` – `WEBHOOK_NOT_CONFIGURED` | Không tiếp nhận webhook. |
| Webhook signature thiếu hoặc sai | `401` – `WEBHOOK_SIGNATURE_INVALID` | Từ chối payload. |
| Thiếu event hoặc delivery header | `400` | Từ chối request. |
| Webhook payload không phải JSON hợp lệ | `400` | Từ chối request. |
| Webhook delivery đã được xử lý | `202` với trạng thái `DUPLICATE` nếu ingestion service xác định trùng | Không xử lý lặp lại cùng delivery. |
| Repository không thuộc workspace hoặc event không được hỗ trợ | `202` với trạng thái `IGNORED` nếu ingestion service xác định bỏ qua | Không thực hiện ingestion cho event đó. |
| Không có `ANTHROPIC_API_KEY` | Không phải lỗi HTTP | Generator chuyển sang chế độ offline. |
| AI model lỗi trong quá trình sinh tài liệu | Theo cơ chế retry/fallback của generator | Có thể dùng fallback dựa trên dữ liệu phân tích; không đồng nghĩa toàn bộ service cấu hình bị lỗi. |
| Template không tồn tại hoặc dữ liệu template không hợp lệ | Lỗi validation/not found theo API template | Không thể sử dụng template không hợp lệ. |
| Không có kết quả retrieval đạt ngưỡng | Kết quả retrieval có thể rỗng | Generator tiếp tục với dữ liệu file và context sẵn có; không có cấu hình embedding fallback được xác nhận. |

## 7. Quy tắc nghiệp vụ

- Các giá trị bí mật như GitHub Client Secret, webhook secret, token encryption key và internal API secret được cung cấp qua biến môi trường; không commit file `.env` có giá trị thật.
- `application.yml` hỗ trợ import file `.env` tùy chọn.
- OAuth callback phải trùng Redirect URI đã khai báo trong cấu hình GitHub App.
- `FRONTEND_URL` quyết định callback redirect về frontend hay trả JSON trực tiếp.
- Webhook phải có secret và chữ ký hợp lệ trước khi xử lý event.
- Danh sách ngôn ngữ được hỗ trợ hiện là danh sách cố định theo extension trong `LanguageDetector`.
- Template built-in là read-only; custom template được lưu trong JSON file và dùng chung trong một cài đặt LivingDocs.
- Nếu không có Anthropic API key, AI Service hoạt động ở chế độ offline.
- Confidence thresholds và retrieval scoring parameters hiện được hard-code trong các module tương ứng.
- Retrieval hiện dùng TF-IDF cosine similarity; không có bằng chứng về embedding model trong code đã kiểm tra.
- Yêu cầu retention cho change log/audit log chưa có cấu hình được xác nhận trong gói code này.
- GitHub Actions workflow hiện diện trong source repository nhằm chạy CI; chưa xác nhận có chức năng quản trị workflow từ LivingDocs.

## 8. Tiêu chí chấp nhận

Các tiêu chí dưới đây được chia thành tiêu chí theo yêu cầu Jira và tiêu chí có thể đối chiếu với code hiện tại.

- **AC-LD-273.1:** GitHub App có thể được cấu hình bằng Client ID, Client Secret, App Slug và Redirect URI thông qua biến môi trường.
- **AC-LD-273.2:** Người dùng có thể khởi tạo OAuth, nhận callback, xem trạng thái kết nối và ngắt kết nối GitHub.
- **AC-LD-273.3:** Webhook chỉ được xử lý khi secret đã cấu hình và chữ ký `X-Hub-Signature-256` hợp lệ.
- **AC-LD-273.4:** Webhook `ping` hợp lệ trả về `PONG`; webhook event có delivery ID hợp lệ được chuyển tới ingestion service.
- **AC-LD-273.5:** File có phần mở rộng nằm trong danh sách hỗ trợ được ánh xạ về language tương ứng; extension không hỗ trợ trả về `null`.
- **AC-LD-273.6:** Người dùng có thể xem và chọn các template built-in để sinh tài liệu.
- **AC-LD-273.7:** Người dùng có thể tạo, cập nhật và xóa custom template; template built-in không được chỉnh sửa hoặc xóa.
- **AC-LD-273.8:** AI Service sử dụng `LLM_MODEL` và `LLM_MAX_TOKENS` theo cấu hình môi trường; nếu thiếu API key thì chuyển sang chế độ offline.
- **AC-LD-273.9:** Confidence score được giới hạn trong `[0, 1]`, làm tròn 2 chữ số và phân loại theo các ngưỡng high `0.75`, medium `0.50`.
- **AC-LD-273.10:** Retrieval index bao gồm code entities và context documents; API `/retrieval/preview` trả về thống kê index cùng các kết quả retrieval.
- **AC-LD-273.11:** Các tham số retrieval hiện tại được áp dụng đúng theo hằng số định nghĩa trong `retrieval.py`.
- **AC-LD-273.12:** Các cấu hình embedding model, retention và automatic update policies phải có cơ chế quản lý riêng nếu cần đáp ứng đầy đủ yêu cầu quản trị tổng thể của LD-273; các cơ chế này chưa được xác nhận trong code được cung cấp.

## 9. Kiểm thử

Các file test có liên quan trong gói source:

**GitHub App, OAuth và bảo mật**
- `services/github-integration-service/src/test/java/com/livingdocs/github/security/OAuthStateStoreTest.java`
- `services/github-integration-service/src/test/java/com/livingdocs/github/security/TokenEncryptorTest.java`
- `services/github-integration-service/src/test/java/com/livingdocs/github/controller/GitHubConnectionControllerTest.java`
- `services/github-integration-service/src/test/java/com/livingdocs/github/GitHubIntegrationFlowTest.java`

**Webhook**
- `services/github-integration-service/src/test/java/com/livingdocs/github/webhook/WebhookSignatureVerifierTest.java`
- `services/github-integration-service/src/test/java/com/livingdocs/github/controller/GitHubWebhookControllerTest.java`
- `services/github-integration-service/src/test/java/com/livingdocs/github/GitHubWebhookIngestionTest.java`

**GitHub Actions / CI**
- `.github/workflows/ci.yml`

**AI, generation và retrieval**
- `ai-service/tests/test_generator.py`
- `ai-service/tests/test_templates.py`
- `ai-service/tests/test_indexing.py`
- `ai-service/tests/test_rag.py`
- `ai-service/tests/test_retrieval_benchmark.py`
- `ai-service/tests/test_retrieval_improvements.py`
- `ai-service/tests/test_confidence_scoring.py`

**Frontend**
- `tests/test_frontend.py`
- `tests/test_frontend_templates.py`

**Ghi chú về phạm vi kiểm thử:** Các test trên kiểm tra những module GitHub, OAuth, webhook, generation, template, indexing, retrieval và confidence đang có. Chưa tìm thấy test chuyên biệt chứng minh có màn hình cấu hình tập trung cho retention, embedding model hoặc automatic update policies.
