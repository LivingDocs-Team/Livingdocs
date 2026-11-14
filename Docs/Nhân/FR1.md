# FR-INT-01 — Điều phối sinh tài liệu qua Backend BFF và GitHub Integration

| Mục | Nội dung |
|---|---|
| Story / Task Jira | LD-396 — Repository Documentation Orchestration |
| Người thực hiện | Nhân |
| Thành phần | Backend BFF (Spring Boot), GitHub Integration Service, Code Analyzer, AI Service, Frontend |
| Tác nhân | Người dùng đã đăng nhập |
| Phụ thuộc | Session authentication, CSRF, GitHub OAuth/connection, repository sync, Code Analyzer, AI Service |
| Mục tiêu | Cho người dùng khởi chạy sinh tài liệu từ repository mà không gọi trực tiếp service nội bộ từ trình duyệt; khôi phục phiên OAuth và phục hồi cache snapshot khi cần |

## 1. Mô tả

Frontend gửi yêu cầu sinh tài liệu qua Backend BFF. BFF xác thực session, áp dụng bảo vệ CSRF cho request thay đổi dữ liệu, xác định user từ principal đã xác thực, rồi gọi GitHub Integration bằng service credential nội bộ. GitHub Integration kiểm tra ownership của repository, bảo đảm có dữ liệu đồng bộ (tự sync lại nếu snapshot cache bị thiếu), tạo AnalysisInput, gọi Code Analyzer và chuyển kết quả phân tích sang AI Service để tạo job sinh tài liệu. Frontend theo dõi job và lấy kết quả qua các endpoint được BFF cho phép.

Luồng đăng nhập GitHub phải quay lại Frontend sau OAuth callback. Frontend kiểm tra session hiện có qua `GET /api/auth/me` để khôi phục trạng thái người dùng sau redirect/reload. Snapshot repository hiện được giữ trong in-memory cache; `latestOrSync` phục hồi trường hợp cache miss bằng cách gọi sync lại từ GitHub, không phải cơ chế lưu snapshot bền vững.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-INT-01.1 | Browser chỉ gọi endpoint `/api/...` trên Backend BFF; không gọi trực tiếp GitHub Integration, Code Analyzer hoặc AI Service. |
| FR-INT-01.2 | BFF lấy user ID từ principal/session đã xác thực. Không tin `X-User-Id`, `Authorization` hoặc user ID do browser gửi; BFF ghi đè header nội bộ bằng giá trị tin cậy. |
| FR-INT-01.3 | Request thay đổi dữ liệu phải qua CSRF đã cấu hình. Frontend gửi session cookie bằng `credentials: 'include'` và gửi CSRF token theo contract. Logout phải được bảo vệ CSRF nếu dùng session cookie. |
| FR-INT-01.4 | Khi gọi GitHub Integration, BFF gắn `Authorization: Bearer <GITHUB_INTEGRATION_INTERNAL_SECRET>` và `X-User-Id` lấy từ session. Không gửi secret xuống browser hoặc log secret. |
| FR-INT-01.5 | GitHub Integration từ chối request nội bộ thiếu/sai credential bằng `401 INTERNAL_SERVICE_AUTH_REQUIRED`, ngoại trừ endpoint được miễn rõ ràng trong contract như health, GitHub OAuth callback GET và các GET Swagger/OpenAPI được cấu hình cho API discovery. Việc mở Swagger phải được xem xét theo chính sách expose API documentation của môi trường triển khai. |
| FR-INT-01.6 | `POST /api/repositories/{repositoryId}/documentation/generate` chỉ chấp nhận repository thuộc user hiện tại. User không sở hữu repo nhận 403; repo không tồn tại nhận 404. |
| FR-INT-01.7 | Yêu cầu generate tạo AnalysisInput theo FR-GH-04, gửi tới Code Analyzer `POST /api/v1/analyze-repo`, rồi chuyển kết quả phân tích sang AI Service `POST /generate`. Không truyền payload giả thay cho kết quả phân tích. |
| FR-INT-01.8 | Hỗ trợ `templateId` và `outputLanguage` theo contract hiện tại. Template mặc định là `default` nếu không cung cấp; ngôn ngữ mặc định là `vi`. Chỉ cho phép template/ngôn ngữ downstream hỗ trợ. |
| FR-INT-01.9 | Khi AI Service trả job, GitHub Integration trả thông tin job cho BFF; không giữ request HTTP mở cho đến khi AI hoàn tất. Frontend theo dõi trạng thái job qua API. |
| FR-INT-01.10 | Endpoint job/result/report phải xác minh quyền truy cập. User chỉ được xem job gắn với repository/generation request của mình; UUID khó đoán không thay thế phân quyền. |
| FR-INT-01.11 | BFF chuyển tiếp status code và lỗi có cấu trúc nhất quán; xử lý riêng connect timeout và read timeout. Read timeout có thể dài hơn do phân tích/generate, nhưng không vô hạn. |
| FR-INT-01.12 | Frontend hiển thị lỗi có thể xử lý được, không hiển thị stack trace, credential, token hoặc nội dung bí mật. |
| FR-INT-01.13 | Không giả định job, owner mapping hoặc snapshot trong bộ nhớ tồn tại sau restart. Nếu store là in-memory, phải nêu giới hạn này và không mô tả là persistence. |
| FR-INT-01.14 | Không thay model/DTO Code Analyzer bằng model generation/evidence/submission. Mọi thay đổi model phải giữ tương thích hoặc cập nhật toàn bộ caller, contract và test liên quan trong cùng thay đổi. |
| FR-INT-01.15 | OAuth2 success callback chuyển hướng trình duyệt về Frontend theo `FRONTEND_URL` đã cấu hình. Reverse proxy phải chuyển tiếp các route `/oauth2/` và `/login/oauth2/` tới Backend để hoàn tất GitHub OAuth. |
| FR-INT-01.16 | Sau OAuth redirect hoặc khi tải lại ứng dụng, Frontend gọi `GET /api/auth/me` với session cookie. Nếu session hợp lệ, Backend trả thông tin user hiện tại để Frontend khôi phục trạng thái đăng nhập; nếu không hợp lệ/không tìm thấy user, trả `401`. |
| FR-INT-01.17 | Endpoint `GET /api/auth/me` chỉ trả thông tin tài khoản cần cho UI (id, email, username, firstName, lastName, role); không trả access token, client secret hoặc internal service secret. |
| FR-INT-01.18 | Khi documentation generation cần snapshot nhưng in-memory cache không có dữ liệu cho repository, service gọi `latestOrSync(userId, repositoryId)`: kiểm tra ownership, sau đó dùng snapshot trong cache nếu có; nếu không có thì tự đồng bộ lại repository bằng cấu hình mặc định trước khi tiếp tục phân tích. |
| FR-INT-01.19 | Cache-miss re-sync không được mô tả là durable persistence. Snapshot vẫn có thể mất khi service restart; lần generate tiếp theo có thể phải đồng bộ GitHub lại. |
| FR-INT-01.20 | Cấu hình Backend dùng `FRONTEND_URL` để xác định địa chỉ redirect; Docker Compose truyền biến này cho Backend. Nếu không cấu hình, dùng default local `http://localhost:3000`. |
| FR-INT-01.21 | Logging mặc định của Backend dùng mức INFO và không bật SQL statement logging. DEBUG cho Spring Security/Web và SQL logging chỉ bật trong profile development. |

## 3. API chính

| Method | Endpoint | Mục đích |
|---|---|---|
| GET | `/api/auth/me` | Lấy user hiện tại từ session đã xác thực |
| GET | `/api/auth/csrf` | Lấy CSRF token cho SPA |
| GET | `/api/github/connection` | Đọc trạng thái kết nối GitHub |
| POST | `/api/repositories/{repositoryId}/documentation/generate` | Khởi chạy phân tích và sinh tài liệu |
| GET | `/api/documentation/jobs/{jobId}` | Lấy trạng thái/tiến độ job |
| GET | `/api/documentation/jobs/{jobId}/result` | Lấy tài liệu khi job hoàn thành |
| GET | `/api/documentation/jobs/{jobId}/report` | Lấy báo cáo evidence/confidence nếu có trong contract |
| DELETE | `/api/github/connection` | Ngắt kết nối GitHub |

Các route OAuth2 browser flow gồm `/oauth2/authorization/github` và `/login/oauth2/code/github`; reverse proxy phải chuyển chúng về Backend. Trước khi code, kiểm tra path và response DTO thực tế trong controller. Không tạo endpoint mới nếu endpoint tương đương đã tồn tại.

Ví dụ request generate:

```json
{
  "templateId": "default",
  "outputLanguage": "vi"
}
```

Tên field HTTP phải khớp DTO/controller hiện có. Nếu API downstream dùng `template_id` hoặc `output_language`, thực hiện mapping có chủ đích, không trộn lẫn hai kiểu đặt tên.

## 4. Luồng chính

1. Người dùng chọn Continue with GitHub; browser điều hướng tới `/oauth2/authorization/github` qua Frontend reverse proxy.
2. Backend hoàn tất OAuth2 callback, tạo/cập nhật authentication session và chuyển hướng về Frontend qua `FRONTEND_URL`.
3. Frontend gọi `GET /api/auth/me` với session cookie để khôi phục user và trạng thái đăng nhập.
4. Người dùng chọn repository đã thêm vào workspace và yêu cầu sinh tài liệu.
5. Frontend gửi request qua BFF kèm session cookie và CSRF token.
6. BFF xác thực user, kiểm tra CSRF, lấy user ID từ principal và gắn service credential.
7. GitHub Integration xác minh credential và ownership; lấy snapshot cache hoặc tự sync lại khi cache miss.
8. Service tạo AnalysisInput, gọi Code Analyzer, rồi gửi kết quả phân tích sang AI Service.
9. AI Service trả job ID; service chuyển job metadata về frontend.
10. Frontend poll trạng thái, rồi lấy Markdown và report khi hoàn thành.

## 5. Luồng lỗi

| Trường hợp | Hành vi |
|---|---|
| Chưa đăng nhập/session hết hạn | `/api/auth/me` hoặc BFF trả 401; Frontend trở về Sign in; không gọi service nội bộ |
| OAuth callback lỗi | Không khôi phục phiên giả; hiển thị trạng thái lỗi phù hợp |
| CSRF thiếu/sai | Từ chối request thay đổi dữ liệu |
| Internal credential thiếu/sai | GitHub Integration trả 401 |
| User không sở hữu repo/job | Trả 403; không lộ dữ liệu |
| Repo không tồn tại | Trả 404 |
| Cache miss | Thử sync lại từ GitHub; nếu sync thất bại thì trả lỗi tương ứng, không giả lập thành công |
| GitHub rate limit hoặc unavailable | Trả lỗi đồng bộ có cấu trúc; không tạo tài liệu giả |
| Code Analyzer/AI Service không khả dụng | Trả lỗi service có cấu trúc; không giả lập thành công |
| AI job failed | Frontend hiển thị trạng thái thất bại |
| Timeout downstream | Ghi nhận lỗi/timeout; không trả tài liệu giả |

## 6. Cấu hình và vận hành

- `FRONTEND_URL` phải được truyền vào Backend container và dùng làm OAuth success redirect.
- Nginx Frontend proxy cả `/api/`, `/oauth2/` và `/login/oauth2/` về Backend.
- Backend mặc định log INFO, không bật SQL logging; profile development mới bật DEBUG và SQL.
- GET Swagger/OpenAPI hiện được miễn internal-service filter để phục vụ API discovery. Chỉ giữ ngoại lệ này nếu chính sách triển khai cho phép truy cập tài liệu API; nếu không, cần giới hạn bằng network/auth hoặc loại bỏ ngoại lệ.
- Snapshot cache, owner mapping hoặc job store dạng in-memory không phải persistent storage.

## 7. Tiêu chí chấp nhận

- **AC-INT-01.1:** Request generate từ browser chỉ đi qua BFF; internal secret không có ở frontend.
- **AC-INT-01.2:** Giả mạo `X-User-Id` từ browser không thay đổi user đã xác thực.
- **AC-INT-01.3:** POST thiếu CSRF token bị từ chối.
- **AC-INT-01.4:** User A không thể generate hoặc đọc job/result/report của user B.
- **AC-INT-01.5:** Request hợp lệ đi qua Integration → Analyzer → AI Service và trả job ID thật.
- **AC-INT-01.6:** Analyzer/AI Service ngừng hoạt động phải thể hiện lỗi thật; test không được biến lỗi thành success bằng `|| true`, `|| echo` hoặc mock giả lập success trong integration test.
- **AC-INT-01.7:** Test contract xác nhận request/response field giữa các service.
- **AC-INT-01.8:** Model/DTO Code Analyzer vẫn import được và test hiện hữu tiếp tục chạy.
- **AC-INT-01.9:** OAuth thành công redirect về Frontend; Frontend gọi `/api/auth/me` và hiển thị đúng user khi session còn hiệu lực.
- **AC-INT-01.10:** Session hết hạn hoặc không có user mapping trả 401; Frontend không giữ trạng thái đăng nhập giả.
- **AC-INT-01.11:** Sau khi GitHub Integration restart làm mất cache snapshot, generate tự gọi sync lại và có thể hoàn tất nếu GitHub còn truy cập được.
- **AC-INT-01.12:** Cache miss không được coi là bằng chứng snapshot được lưu bền vững; tài liệu phải nêu rõ giới hạn in-memory.
- **AC-INT-01.13:** Compose truyền `FRONTEND_URL` cho Backend; OAuth redirect hoạt động với URL frontend được cấu hình.
- **AC-INT-01.14:** Backend production/default log không bật DEBUG hoặc SQL statement logging; profile development có thể bật các log này.



