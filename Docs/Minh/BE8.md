# LivingDocs — Đặc tả chức năng LD-404: Release Smoke Testing & Deployment Verification

## 1. Mục tiêu

LD-404 triển khai bộ kiểm tra smoke test và xác minh triển khai cho LivingDocs, nhằm kiểm tra khả năng khởi động stack từ Docker Compose, trạng thái hoạt động của các service, quá trình khởi tạo database/migration, luồng tạo và review tài liệu, khả năng phục hồi sau khi restart và tính bền vững của dữ liệu.

Chức năng cung cấp hai lớp kiểm tra:

1. **Deployment verification:** xác minh cấu hình Compose, khởi động các container, chờ service sẵn sàng, kiểm tra database schema/migration và health endpoint.
2. **End-to-end smoke & persistence verification:** thực hiện một luồng nghiệp vụ mẫu trước khi restart, restart các application service, sau đó xác minh dữ liệu cần được lưu vẫn tồn tại và dữ liệu tạm thời được reset đúng thiết kế.

Kết quả được ghi thành log và JSON report để có thể kiểm tra lại sau khi chạy.

## 2. Thành phần và vị trí mã nguồn

### 2.1. Script kiểm tra chính

- `scripts/release_smoke_test.py`: thực hiện E2E smoke test theo hai phase `pre-restart` và `post-restart`. Script chỉ sử dụng Python Standard Library, không yêu cầu cài thêm package kiểm thử.
- `scripts/verify-compose.sh`: kịch bản chạy trên Linux/macOS/Git Bash, điều phối toàn bộ quá trình xác minh Docker Compose.
- `scripts/verify-compose.ps1`: phiên bản PowerShell dành cho Windows, có các tham số `-Clean`, `-NoUp` và `-TimeoutSeconds`.

### 2.2. Hạ tầng và cấu hình liên quan

- `compose.yaml`: định nghĩa các service, healthcheck, network và named volume được kiểm tra.
- `.github/workflows/ci.yml`: pipeline CI hiện có, gồm các job build/test và job kiểm tra cấu hình, build Docker image.
- `artifacts/`: nơi lưu kết quả smoke test mẫu và trạng thái trung gian.

### 2.3. Artifact kết quả

- `artifacts/ld-404-smoke-report.log`: log tổng hợp các bước xác minh do script điều phối tạo ra.
- `artifacts/smoke-state.json`: trạng thái trung gian được tạo ở phase trước restart, dùng làm đầu vào cho phase sau restart.
- `artifacts/smoke-e2e-results.json`: kết quả E2E cuối cùng, gồm thông tin lần chạy, document/version được kiểm tra, thời điểm trước/sau restart và trạng thái.

Các file state/report có thể chứa định danh tài khoản kiểm thử và thông tin phục vụ xác thực. Không đưa mật khẩu, token hoặc secret vào tài liệu, log chia sẻ hay commit; cần kiểm soát việc lưu trữ và chia sẻ artifact thực tế.

## 3. Tổng quan kiến trúc và phạm vi kiểm tra

LD-404 kiểm tra stack LivingDocs được khai báo trong `compose.yaml` gồm bảy service:

| Service | Vai trò trong quá trình kiểm tra |
|---|---|
| `backend-db` | PostgreSQL database cho Backend; kiểm tra schema đã được khởi tạo và dữ liệu user còn tồn tại sau restart |
| `github-db` | PostgreSQL database cho GitHub Integration; kiểm tra Flyway migration |
| `code-analyzer` | Phân tích source code mẫu qua API `/health` và `/api/v1/analyze-repo` |
| `ai-service` | Sinh tài liệu, lưu document/version và thực hiện kiểm tra review |
| `github-integration` | Kiểm tra trạng thái service qua `/actuator/health` |
| `backend` | Kiểm tra Backend health và các API xác thực/session |
| `frontend` | Kiểm tra trang ứng dụng được phục vụ tại cổng 3000 và BFF route qua Nginx |

Các URL mặc định được `release_smoke_test.py` sử dụng:

| Biến môi trường | Giá trị mặc định |
|---|---|
| `FRONTEND_URL` | `http://localhost:3000` |
| `BACKEND_URL` | `http://localhost:8080` |
| `ANALYZER_URL` | `http://localhost:8000` |
| `AI_SERVICE_URL` | `http://localhost:8001` |
| `GITHUB_INTEGRATION_INTERNAL_SECRET` | Không có giá trị mặc định; được dùng để tạo header xác thực nội bộ khi được cấu hình |

Luồng kiểm tra nghiệp vụ gọi trực tiếp các API của Backend, Code Analyzer và AI Service theo mục đích smoke test. Đây là script xác minh triển khai, không phải giao diện người dùng mới.

## 4. Deployment Verification

### 4.1. Kiểm tra cấu hình Docker Compose

Trước khi khởi động, script chạy:

```bash
docker compose -f compose.yaml config --quiet
```

Nếu cấu hình không hợp lệ, quá trình kiểm tra dừng và ghi nhận lỗi. Nếu hợp lệ, log ghi nhận trạng thái `PASS`.

### 4.2. Chế độ clean deployment

Khi chạy với tùy chọn clean, script thực hiện:

```bash
docker compose -f compose.yaml down -v --remove-orphans
```

Sau đó khởi động lại stack bằng:

```bash
docker compose -f compose.yaml up --build -d
```

**Lưu ý:** `down -v` xóa named volume của Compose, bao gồm dữ liệu database và dữ liệu lưu trữ của ứng dụng. Đây là thao tác destructive, chỉ sử dụng khi chủ động muốn kiểm tra triển khai sạch và đã chấp nhận việc xóa dữ liệu hiện có.

Nếu không chọn clean, script không chủ động xóa volume trước khi khởi động.

### 4.3. Chờ service sẵn sàng

Script lần lượt chờ các service:

1. `backend-db`
2. `github-db`
3. `code-analyzer`
4. `ai-service`
5. `github-integration`
6. `backend`
7. `frontend`

Mỗi service có thời gian chờ tối đa mặc định 300 giây. Cứ mỗi 3 giây, script kiểm tra container bằng `docker compose ps` và `docker inspect`.

Service được xem là sẵn sàng khi trạng thái health là `healthy`; nếu container không khai báo health status thì trạng thái `running` được chấp nhận. Nếu quá thời gian chờ, script ghi `FAIL` và dừng.

Shell script cho phép thay timeout qua biến `VERIFY_TIMEOUT`; PowerShell script nhận tham số `-TimeoutSeconds`.

### 4.4. Kiểm tra database migration và schema

Script kiểm tra hai database theo cơ chế tương ứng:

**GitHub Integration database (`github-db`):**

- Đếm số bản ghi thành công trong `flyway_schema_history`.
- Yêu cầu có ít nhất một migration thành công.
- Đếm migration thất bại và yêu cầu số lượng bằng 0.

**Backend database (`backend-db`):**

- Truy vấn `information_schema.tables` trong schema `public`.
- Yêu cầu có ít nhất một table, xác nhận schema đã được khởi tạo.

Backend hiện sử dụng Hibernate `ddl-auto=update`, do đó bước này kiểm tra schema đã có bảng, không phải kiểm tra Flyway migration cho Backend.

### 4.5. Kiểm tra health endpoint và khả năng phục vụ

Các endpoint/địa chỉ được kiểm tra:

| Thành phần | Địa chỉ kiểm tra |
|---|---|
| Code Analyzer | `GET http://localhost:8000/health` |
| AI Service | `GET http://localhost:8001/health` |
| GitHub Integration | `GET http://localhost:8082/actuator/health` |
| Backend | `GET http://localhost:8080/actuator/health` |
| Frontend | `GET http://localhost:3000/` |

Shell script còn kiểm tra nội dung JSON `status: ok` của health endpoint Code Analyzer và AI Service. Với GitHub Integration và Backend, script yêu cầu request thành công; với Frontend, script xác nhận trang chủ có thể được phục vụ.

## 5. End-to-End Smoke Test trước restart

`release_smoke_test.py --phase pre-restart` thực hiện luồng kiểm tra nghiệp vụ mẫu theo thứ tự dưới đây.

### 5.1. Kiểm tra CSRF qua Frontend/BFF

- Gửi `GET /api/auth/csrf` thông qua `FRONTEND_URL`.
- Xác nhận HTTP 200.
- Lấy `XSRF-TOKEN` từ cookie jar hoặc token trong response.
- Dùng token này cho các request thay đổi dữ liệu tiếp theo.

Bước này xác minh route API qua frontend reverse proxy và cơ chế lấy CSRF token.

### 5.2. Đăng ký và đăng nhập smoke user

Script tạo tài khoản kiểm thử với username/email có gắn `run_id`, sau đó:

1. Gửi `POST /api/auth/register` với username, email, password, first name và last name.
2. Yêu cầu HTTP 201.
3. Làm mới CSRF token.
4. Gửi `POST /api/auth/login` bằng email/password và CSRF header.
5. Yêu cầu HTTP 200.
6. Gọi `GET /api/auth/me` và xác nhận email của session đúng với tài khoản vừa tạo.

Cookie jar được dùng để duy trì session trong các request thuộc phase này.

### 5.3. Kiểm tra Code Analyzer

Script gửi source code Python mẫu có class `PaymentService` và method `charge` đến:

```text
POST /api/v1/analyze-repo
```

Payload kiểm tra scope repository và file `services/payment.py`. Script yêu cầu HTTP 200 và response dạng object. Kết quả phân tích được sử dụng làm đầu vào cho bước sinh tài liệu.

### 5.4. Kiểm tra AI Documentation Generation

Script gọi:

```text
POST /generate
GET  /jobs/{job_id}
```

- Gửi dữ liệu phân tích code, target repository mẫu, template `default` và output language `en`.
- Yêu cầu API khởi tạo job trả HTTP 202 và có `id`.
- Poll trạng thái job tối đa 60 giây, mỗi giây một lần.
- Chỉ xem bước sinh tài liệu thành công khi job đạt trạng thái `completed`.

Request đến AI Service có thể kèm Bearer token lấy từ `GITHUB_INTEGRATION_INTERNAL_SECRET`.

### 5.5. Lưu document và tạo version

Sau khi job hoàn thành, script gọi:

```text
POST /internal/documents/from-job
```

để lưu document từ generation job. Script yêu cầu HTTP 201 và document ID hợp lệ.

Tiếp đó, script cập nhật nội dung document qua:

```text
PUT /internal/documents/{doc_id}/content
```

Request sử dụng `expected_version: 1`; kết quả phải tạo version số 2. Nội dung Markdown được thay bằng nội dung kiểm thử có đánh dấu `Updated during LD-404 smoke review flow.`.

### 5.6. Kiểm tra review decision và evidence

Script gửi quyết định review:

```text
POST /internal/documents/{doc_id}/review-decision
```

với version 2 và decision `APPROVED`. HTTP 200 hoặc 204 được chấp nhận.

Sau đó script gọi:

```text
GET /internal/documents/{doc_id}/evidence?version=2
```

và yêu cầu HTTP 200 để xác nhận grounding evidence của version 2 còn truy xuất được.

### 5.7. Lưu trạng thái cho phase sau restart

Khi toàn bộ bước trước restart thành công, script ghi state JSON gồm các thông tin phục vụ đối chiếu:

- `run_id`, username/email và user ID của smoke user.
- Generation job ID.
- Document ID.
- Version kỳ vọng (`expected_version = 2`).
- Thời điểm hoàn tất phase trước restart (`pre_restart_at`).

File state này là dữ liệu đầu vào bắt buộc cho phase `post-restart`.

## 6. Restart và kiểm tra phục hồi

Sau khi phase trước restart thành công, script điều phối restart năm application service:

```bash
docker compose restart code-analyzer ai-service github-integration backend frontend
```

Hai database `backend-db` và `github-db` không nằm trong danh sách restart ở bước này.

Sau lệnh restart, script tiếp tục chờ các service trong danh sách bảy service đạt trạng thái `healthy` hoặc `running`. Nếu service không phục hồi trong timeout, quá trình xác minh thất bại.

## 7. Kiểm tra persistence sau restart

`release_smoke_test.py --phase post-restart` đọc state JSON đã tạo trước restart và kiểm tra các dữ liệu sau.

### 7.1. Backend user/session data

- Lấy CSRF token từ `GET /api/auth/csrf`.
- Đăng nhập lại smoke user đã đăng ký trước restart bằng `POST /api/auth/login`.
- Yêu cầu HTTP 200.

Bước này xác minh tài khoản được lưu trong `backend-db` vẫn tồn tại sau khi Backend được restart. Script tạo session mới để kiểm tra đăng nhập, không yêu cầu session cookie cũ phải được giữ nguyên.

### 7.2. AI document và version persistence

Script gọi:

```text
GET /internal/documents/{doc_id}
GET /internal/documents/{doc_id}/content?version=2
```

Các điều kiện thành công:

- Document được tìm thấy với HTTP 200.
- `current_version` vẫn bằng version kỳ vọng (2).
- Nội dung version 2 vẫn chứa chuỗi đánh dấu được ghi trước restart.

Bước này xác minh document và versioned Markdown content được lưu bền vững qua volume `ai-templates` của AI Service.

### 7.3. Generation job có tính tạm thời

Script gọi lại:

```text
GET /jobs/{job_id}
```

và yêu cầu HTTP 404 sau restart.

Đây là hành vi được mong đợi: generation job lưu trong bộ nhớ của AI Service là dữ liệu tạm thời, không cần tồn tại sau khi service restart. Vì vậy, HTTP 404 ở bước này được xem là kiểm tra thành công, không phải lỗi.

### 7.4. Hoàn tất report

Nếu tất cả kiểm tra sau restart thành công, script cập nhật state với:

- `post_restart_at`: thời điểm hoàn tất kiểm tra sau restart.
- `status`: `PASSED`.

Kết quả được ghi vào JSON report để lưu lại bằng chứng của lần chạy.

## 8. Cách sử dụng

### 8.1. Linux/macOS/Git Bash

Từ thư mục gốc repository:

```bash
# Khởi động/build stack, chạy smoke test, restart và kiểm tra persistence
./scripts/verify-compose.sh

# Clean deployment: xóa container và named volume trước khi build/start
./scripts/verify-compose.sh --clean

# Không chạy lệnh up; xác minh stack đang chạy, sau đó smoke/restart/persistence
./scripts/verify-compose.sh --no-up
```

Có thể cấu hình thêm:

- `VERIFY_TIMEOUT`: timeout chờ service, mặc định 300 giây.
- `SMOKE_REPORT_DIR`: thư mục lưu report, mặc định `artifacts`.

### 8.2. Windows PowerShell

Từ thư mục gốc repository:

```powershell
# Build/start stack và chạy toàn bộ quy trình
.\scripts\verify-compose.ps1

# Clean deployment (lưu ý thao tác xóa volume)
.\scripts\verify-compose.ps1 -Clean

# Xác minh stack đang chạy, không chạy compose up
.\scripts\verify-compose.ps1 -NoUp

# Thay đổi thời gian chờ service
.\scripts\verify-compose.ps1 -TimeoutSeconds 600
```

PowerShell script đọc `.env` vào process environment để cung cấp các biến cần thiết cho Python smoke test. Không ghi giá trị secret ra log.

## 9. Xử lý lỗi và báo cáo

- Các bước xác minh được ghi log theo nhãn `[PASS]` hoặc `[FAIL]`.
- Khi một bước bắt buộc thất bại, script điều phối dừng với exit code khác 0.
- `release_smoke_test.py` in thông tin lỗi ra stderr và thoát với exit code 1 khi có exception/điều kiện assertion không đạt.
- Các bước thành công được ghi nhận bằng các assertion riêng, giúp xác định giai đoạn thất bại.
- Report được lưu trong thư mục artifact để phục vụ rà soát kết quả triển khai.

## 10. Kiểm thử và bằng chứng trong snapshot LD-404

Trong snapshot code được cung cấp có các file triển khai:

- `scripts/release_smoke_test.py`
- `scripts/verify-compose.sh`
- `scripts/verify-compose.ps1`
- `artifacts/smoke-e2e-results.json`
- `artifacts/smoke-state.json`

Artifact `smoke-e2e-results.json` trong snapshot ghi nhận:

| Trường | Giá trị ghi nhận |
|---|---|
| `pre_restart_at` | `2026-11-17T05:10:41.034330+00:00` |
| `post_restart_at` | `2026-11-17T05:11:59.192694+00:00` |
| `expected_version` | `2` |
| `status` | `PASSED` |

Như vậy, artifact được cung cấp thể hiện một lần chạy E2E trước/sau restart đã ghi nhận trạng thái `PASSED`. Đây là bằng chứng từ report có trong snapshot; không đồng nghĩa với việc toàn bộ CI pipeline đã được chạy lại trong quá trình lập tài liệu này.

`ci.yml` hiện có job `docker-compose-validation` thực hiện `docker compose config --quiet` và build các image. Trong nội dung workflow được cung cấp, job này chưa gọi `scripts/verify-compose.sh` hoặc `scripts/verify-compose.ps1`; do đó không mô tả LD-404 như một bước smoke/restart tự động đã được tích hợp vào CI.

## 11. Tiêu chí chấp nhận

Đối chiếu với đề bài LD-404, các tiêu chí chức năng cần xác minh gồm:

1. Docker Compose configuration hợp lệ.
2. Có thể triển khai stack theo quy trình clean deployment hoặc khởi động thông thường.
3. Tất cả service được kiểm tra đạt trạng thái sẵn sàng trong timeout.
4. GitHub Integration Flyway migrations có migration thành công và không có migration thất bại.
5. Backend database schema đã được khởi tạo.
6. Các health endpoint và frontend entry point phản hồi thành công.
7. Smoke user có thể đăng ký, đăng nhập và xác thực session.
8. Code Analyzer phân tích được source code mẫu.
9. AI Service tạo generation job và job hoàn tất.
10. Document được lưu, cập nhật lên version 2 và review decision được chấp nhận.
11. Grounding evidence của version được kiểm tra có thể truy xuất.
12. Các application service được restart và phục hồi.
13. Smoke user vẫn có thể đăng nhập sau restart.
14. Document, version và Markdown content vẫn tồn tại sau restart.
15. Generation job trong bộ nhớ trả HTTP 404 sau restart theo thiết kế.
16. Kết quả trước/sau restart được ghi thành report có trạng thái cuối cùng.

## 12. Giới hạn và lưu ý

- Smoke test dùng tài khoản và source code mẫu được tạo tự động; đây không phải kiểm thử trên repository GitHub thực của người dùng.
- Luồng review trong script kiểm tra API versioned document của AI Service với quyết định `APPROVED`. Script không mô phỏng đầy đủ quy trình Staff review và Manager approval nhiều vai trò của Document Workflow.
- Bước persistence xác minh user trong Backend database và document/version trong AI Service volume; không phải phép kiểm tra toàn bộ dữ liệu của mọi service.
- Generation job là dữ liệu in-memory và được kỳ vọng mất sau restart; không xem việc job trả 404 là lỗi.
- Health check ở bước điều phối chấp nhận trạng thái `running` nếu container không có health status. Vì vậy, điều kiện này không phải lúc nào cũng chứng minh endpoint nghiệp vụ của service hoạt động; các endpoint riêng được kiểm tra ở bước health verification.
- `--clean`/`-Clean` sử dụng `docker compose down -v`, có thể xóa dữ liệu đang lưu trong các named volume.
- Script cần Docker Compose, Python 3 và các biến môi trường/secret phù hợp với cấu hình Compose. Không ghi secret thực tế vào tài liệu hoặc report.
- Artifact smoke test có thể chứa thông tin đăng nhập của tài khoản kiểm thử. Cần hạn chế quyền truy cập, không chia sẻ công khai và không lưu mật khẩu dạng rõ trong artifact được commit.
- Snapshot CI hiện chỉ xác minh Compose config và build image ở job Docker Compose; chưa thể kết luận smoke/restart test được tự động chạy trong CI.

## 13. Hướng dẫn khi mở rộng hoặc tái tạo chức năng

- Giữ `release_smoke_test.py` độc lập với package bên ngoài để có thể chạy trong môi trường triển khai tối giản.
- Duy trì tách biệt rõ hai phase `pre-restart` và `post-restart`; phase sau phải dùng đúng state file do phase trước tạo.
- Không coi job in-memory phải tồn tại sau restart; giữ nguyên kiểm tra HTTP 404 như hành vi dự kiến.
- Khi bổ sung kiểm tra persistence, cần xác định rõ dữ liệu nào phải tồn tại và dữ liệu nào được phép mất sau restart.
- Giữ việc xác minh Flyway của GitHub Integration tách biệt với kiểm tra schema Hibernate của Backend.
- Cẩn trọng với chế độ clean vì thao tác xóa volume có thể làm mất dữ liệu môi trường phát triển.
- Không ghi password, access token, internal secret hoặc thông tin xác thực nhạy cảm vào log/report được chia sẻ.
- Nếu tích hợp smoke test vào CI, cần bổ sung bước gọi script, chuẩn bị secrets và Docker runtime phù hợp; cập nhật tài liệu và bằng chứng CI tương ứng.
