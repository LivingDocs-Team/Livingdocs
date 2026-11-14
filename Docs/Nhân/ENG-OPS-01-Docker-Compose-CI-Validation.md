# ENG-OPS-01 — Kiểm tra Docker Compose và CI

> Đây là yêu cầu kỹ thuật/vận hành liên quan LD-382, không phải Functional Requirement của người dùng cuối.

| Mục | Nội dung |
|---|---|
| Story / Task Jira | LD-382 — Docker Deployment / Docker Compose validation |
| Người thực hiện | Nhân |
| Thành phần | `compose.yaml`, Dockerfiles của service, GitHub Actions workflow |
| Tác nhân | Developer/CI |
| Mục tiêu | Build/validate cấu hình triển khai lặp lại và phát hiện lỗi build/test thật |

## 1. Yêu cầu kỹ thuật

| ID | Yêu cầu |
|---|---|
| ENG-OPS-01.1 | CI kiểm tra cấu hình Docker Compose trước khi build/chạy stack. Lỗi cấu hình phải làm job thất bại. |
| ENG-OPS-01.2 | CI build các service trong phạm vi workflow: backend, AI service, GitHub Integration, frontend và analyzer nếu được khai báo trong Compose hiện tại. |
| ENG-OPS-01.3 | Không che giấu lỗi bằng `|| true`, `|| echo "passed"` hoặc lệnh tương đương ở bước kiểm tra/build/test bắt buộc. |
| ENG-OPS-01.4 | Health check dùng endpoint thực sự được service cung cấp. Không giả định mọi service đều có `/health`; Code Analyzer có thể dùng endpoint health đã cấu hình riêng. |
| ENG-OPS-01.5 | Không xóa database volume hoặc thay đổi dữ liệu local như một phần validation mặc định. Không đưa `.env`, token hoặc secret vào Git. |
| ENG-OPS-01.6 | CI thất bại khi service không khởi động trong thời hạn, integration test không kết nối được, hoặc lệnh build/test trả exit code khác 0. |
| ENG-OPS-01.7 | Báo cáo kiểm thử phân biệt rõ job CI xanh với test thực sự pass. Test skipped/xfail và test bị bỏ qua phải được báo riêng. |
| ENG-OPS-01.8 | Backend nhận `FRONTEND_URL` từ environment để OAuth success redirect không bị cố định vào localhost khi triển khai ở môi trường khác. |
| ENG-OPS-01.9 | Các cổng publish chỉ bind loopback khi chỉ phục vụ debug local; service-to-service communication sử dụng Docker network nội bộ và DNS service name. |
| ENG-OPS-01.10 | Logging production/default không bật DEBUG hoặc SQL statement logging; cấu hình verbose chỉ bật trong profile development. |

## 2. Tiêu chí chấp nhận

- **AC-OPS-01.1:** Compose validation thất bại khi file cấu hình sai.
- **AC-OPS-01.2:** Build failure của service bắt buộc làm workflow thất bại.
- **AC-OPS-01.3:** Integration test không kết nối được service làm workflow thất bại, không in thông báo pass thay thế.
- **AC-OPS-01.4:** Validation không xóa hoặc tái tạo database volume có sẵn.
- **AC-OPS-01.5:** Không có secret trong repository, log CI hoặc artifact.
- **AC-OPS-01.6:** Backend container nhận đúng `FRONTEND_URL` được cấu hình; giá trị default chỉ dùng cho local development.
- **AC-OPS-01.7:** Các service nội bộ giao tiếp qua network phù hợp; không publish port nội bộ ra mọi interface nếu không cần thiết.

## 3. Hướng dẫn cho AI coding agent

1. Đọc workflow, Compose và Dockerfiles hiện tại trước khi sửa.
2. Kiểm tra exit code và health endpoint thực tế của từng service.
3. Không dùng lệnh nuốt lỗi hoặc biến test fail thành success.
4. Không sửa `.env`, xóa volume, commit/push/merge nếu chưa được cho phép.
5. Báo cáo chính xác test nào pass, fail, skipped hoặc chưa chạy.



