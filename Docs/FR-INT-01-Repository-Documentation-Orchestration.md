# FR-INT-01 — Điều phối sinh tài liệu qua Backend BFF và GitHub Integration

| Mục | Nội dung |
|---|---|
| Story / Task Jira | LD-396 — Repository Documentation Orchestration |
| Người thực hiện | Nhân |
| Thành phần | Backend BFF (Spring Boot), GitHub Integration Service, Code Analyzer, AI Service, Frontend |
| Tác nhân | Người dùng đã đăng nhập |
| Phụ thuộc | Session authentication, CSRF, GitHub connection, repository sync, Code Analyzer, AI Service |
| Mục tiêu | Cho người dùng khởi chạy sinh tài liệu từ repository đã đồng bộ mà không gọi trực tiếp service nội bộ từ trình duyệt |

## 1. Mô tả

Frontend gửi yêu cầu sinh tài liệu qua Backend BFF. BFF xác thực session, áp dụng bảo vệ CSRF cho request thay đổi dữ liệu, xác định user từ principal đã xác thực, rồi gọi GitHub Integration bằng service credential nội bộ. GitHub Integration kiểm tra ownership của repository, lấy dữ liệu đầu vào theo contract, gọi Code Analyzer và chuyển kết quả phân tích sang AI Service để tạo job sinh tài liệu. Frontend theo dõi job và lấy kết quả qua các endpoint được BFF cho phép.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-INT-01.1 | Browser chỉ gọi endpoint `/api/...` trên Backend BFF; không gọi trực tiếp GitHub Integration, Code Analyzer hoặc AI Service. |
| FR-INT-01.2 | BFF lấy user ID từ principal/session đã xác thực. Không tin `X-User-Id`, `Authorization` hoặc user ID do browser gửi; BFF ghi đè header nội bộ bằng giá trị tin cậy. |
| FR-INT-01.3 | Request thay đổi dữ liệu phải qua CSRF đã cấu hình. Frontend gửi session cookie bằng `credentials: 'include'` và gửi CSRF token theo contract. Logout phải được bảo vệ CSRF nếu dùng session cookie. |
| FR-INT-01.4 | Khi gọi GitHub Integration, BFF gắn `Authorization: Bearer <GITHUB_INTEGRATION_INTERNAL_SECRET>` và `X-User-Id` lấy từ session. Không gửi secret xuống browser hoặc log secret. |
| FR-INT-01.5 | GitHub Integration từ chối request nội bộ thiếu/sai credential bằng `401 INTERNAL_SERVICE_AUTH_REQUIRED`, ngoại trừ endpoint được miễn rõ ràng trong contract như health và GitHub OAuth callback GET. |
| FR-INT-01.6 | `POST /api/repositories/{repositoryId}/documentation/generate` chỉ chấp nhận repository thuộc user hiện tại. User không sở hữu repo nhận 403; repo không tồn tại nhận 404. |
| FR-INT-01.7 | Yêu cầu generate dùng dữ liệu repository đã sync; tạo `AnalysisInput` theo FR-GH-04, gửi tới Code Analyzer `POST /api/v1/analyze-repo`, rồi chuyển kết quả phân tích sang AI Service `POST /generate`. Không truyền payload giả thay cho kết quả phân tích. |
| FR-INT-01.8 | Hỗ trợ `templateId` và `outputLanguage` theo contract hiện tại. Template mặc định là `default` nếu không cung cấp; ngôn ngữ mặc định là `vi`. Chỉ cho phép template/ngôn ngữ downstream hỗ trợ. |
| FR-INT-01.9 | Khi AI Service trả job, GitHub Integration trả thông tin job cho BFF; không giữ request HTTP mở cho đến khi AI hoàn tất. Frontend theo dõi trạng thái job qua API. |
| FR-INT-01.10 | Endpoint job/result/report phải xác minh quyền truy cập. User chỉ được xem job gắn với repository/generation request của mình; UUID khó đoán không thay thế phân quyền. |
| FR-INT-01.11 | BFF chuyển tiếp status code và lỗi có cấu trúc nhất quán; xử lý riêng connect timeout và read timeout. Read timeout có thể dài hơn do phân tích/generate, nhưng không vô hạn. |
| FR-INT-01.12 | Frontend hiển thị lỗi có thể xử lý được, không hiển thị stack trace, credential, token hoặc nội dung bí mật. |
| FR-INT-01.13 | Không giả định job, owner mapping hoặc snapshot trong bộ nhớ tồn tại sau restart. Nếu store là in-memory, phải nêu giới hạn này và không mô tả là persistence. |
| FR-INT-01.14 | Không thay model/DTO Code Analyzer bằng model generation/evidence/submission. Mọi thay đổi model phải giữ tương thích hoặc cập nhật toàn bộ caller, contract và test liên quan trong cùng thay đổi. |

## 3. API chính

| Method | Endpoint | Mục đích |
|---|---|---|
| POST | `/api/repositories/{repositoryId}/documentation/generate` | Khởi chạy phân tích và sinh tài liệu |
| GET | `/api/documentation/jobs/{jobId}` | Lấy trạng thái/tiến độ job |
| GET | `/api/documentation/jobs/{jobId}/result` | Lấy tài liệu khi job hoàn thành |
| GET | `/api/documentation/jobs/{jobId}/report` | Lấy báo cáo evidence/confidence nếu có trong contract |
| GET | `/api/github/connection` | Đọc trạng thái kết nối GitHub |
| GET | `/api/github/authorize-url` | Lấy URL bắt đầu OAuth/installation |
| DELETE | `/api/github/connection` | Ngắt kết nối GitHub |

Trước khi code, kiểm tra path và response DTO thực tế trong controller. Không tạo endpoint mới nếu endpoint tương đương đã tồn tại.

Ví dụ request:

```json
{
  "templateId": "default",
  "outputLanguage": "vi"
}
```

Tên field HTTP phải khớp DTO/controller hiện có. Nếu API downstream dùng `template_id` hoặc `output_language`, thực hiện mapping có chủ đích, không trộn lẫn hai kiểu đặt tên.

## 4. Luồng chính

1. Người dùng đăng nhập và kết nối GitHub.
2. Chọn repository đã thêm vào workspace và yêu cầu sinh tài liệu.
3. Frontend gửi request qua BFF kèm session cookie và CSRF token.
4. BFF xác thực user, kiểm tra CSRF, lấy user ID từ principal và gắn service credential.
5. GitHub Integration xác minh credential và ownership.
6. Service đọc snapshot/analysis input, gọi Code Analyzer, rồi gửi kết quả phân tích sang AI Service.
7. AI Service trả job ID; service chuyển job metadata về frontend.
8. Frontend poll trạng thái, rồi lấy Markdown và report khi hoàn thành.

## 5. Luồng lỗi

| Trường hợp | Hành vi |
|---|---|
| Chưa đăng nhập/session hết hạn | BFF trả lỗi xác thực; không gọi service nội bộ |
| CSRF thiếu/sai | Từ chối request thay đổi dữ liệu |
| Internal credential thiếu/sai | GitHub Integration trả 401 |
| User không sở hữu repo/job | Trả 403; không lộ dữ liệu |
| Chưa sync hoặc thiếu analysis input | Trả lỗi yêu cầu sync trước theo contract |
| Code Analyzer/AI Service không khả dụng | Trả lỗi service có cấu trúc; không giả lập thành công |
| AI job failed | Frontend hiển thị trạng thái thất bại |
| Timeout downstream | Ghi nhận lỗi/timeout; không trả tài liệu giả |

## 6. Tiêu chí chấp nhận

- **AC-INT-01.1:** Request generate từ browser chỉ đi qua BFF; internal secret không có ở frontend.
- **AC-INT-01.2:** Giả mạo `X-User-Id` từ browser không thay đổi user đã xác thực.
- **AC-INT-01.3:** POST thiếu CSRF token bị từ chối.
- **AC-INT-01.4:** User A không thể generate hoặc đọc job/result/report của user B.
- **AC-INT-01.5:** Request hợp lệ đi qua Integration → Analyzer → AI Service và trả job ID thật.
- **AC-INT-01.6:** Analyzer/AI Service ngừng hoạt động phải thể hiện lỗi thật; test không được biến lỗi thành success bằng `|| true`, `|| echo` hoặc mock giả lập success trong integration test.
- **AC-INT-01.7:** Test contract xác nhận request/response field giữa các service.
- **AC-INT-01.8:** Model/DTO Code Analyzer vẫn import được và test hiện hữu tiếp tục chạy.
