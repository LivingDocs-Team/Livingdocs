# FR-BE-8 Release Smoke Testing & Deployment Verification

| Mục | Nội dung |
|---|---|
| Story Jira | LD-404 Release Smoke Testing & Deployment Verification |
| Task đã làm | — (Sprint 7 — Code-aligned scope; phụ thuộc: LD-401, LD-405, LD-403) |
| Người thực hiện | Nguyễn Lê Minh |
| Nhánh / PR & Trạng thái | Nhánh tính năng `LD-404` (Sprint 7 — Release Smoke Testing trước khi hợp nhất phát hành) |
| Thành phần | `compose.yaml`, `scripts/verify-compose.sh`, `scripts/verify-compose.ps1`, `scripts/release_smoke_test.py`, `.github/workflows/ci.yml`, `artifacts/ld-404-smoke-report.log`, `artifacts/smoke-e2e-results.json`, `artifacts/smoke-state.json` |
| Tác nhân | Release Engineer / Developer chạy kiểm thử triển khai local; GitHub Actions CI job `release-smoke-test` |

## 1. Mô tả

Chức năng kiểm thử khói phát hành và xác minh triển khai (`LD-404`) tự động hóa toàn bộ quy trình kiểm chứng stack LivingDocs trên Docker Compose từ trạng thái sạch đến khi phục hồi sau khởi động lại. Quy trình xác thực cấu hình `compose.yaml`, khởi chạy độc lập 7 container dịch vụ (`backend-db`, `github-db`, `code-analyzer`, `ai-service`, `github-integration`, `backend`, `frontend`), kiểm tra migration cơ sở dữ liệu Flyway, chạy kịch bản E2E hai pha (`pre-restart` và `post-restart`) gồm đăng ký/đăng nhập người dùng, sinh tài liệu AI, chỉnh sửa phiên bản và kế thừa evidence, sau đó thực hiện `docker compose restart` để kiểm chứng khả năng phục hồi dịch vụ và tính bền vững dữ liệu qua named volumes, ghi nhận toàn bộ kết quả vào `artifacts/` và tích hợp vào CI.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-BE—08.1 | Chạy stack kiểm thử trên Docker Compose project name riêng (`SMOKE_PROJECT`, mặc định `livingdocs-smoke`, qua `docker compose -p livingdocs-smoke -f compose.yaml`) với bộ cổng host tách biệt (`BACKEND_DB_PORT=5444`, `GITHUB_DB_PORT=5443`, `BACKEND_PORT=8081`, `FRONTEND_PORT=3001`, `AI_SERVICE_PORT=8002`, `ANALYZER_PORT=8003`, `GITHUB_INTEGRATION_PORT=8083` trên Bash hoặc ánh xạ động qua `docker compose port` trên PowerShell) để không xóa volume hay xung đột cổng với stack dev chính. |
| FR-BE—08.2 | Kiểm tra tính hợp lệ của `compose.yaml` bằng `docker compose -p <project> -f compose.yaml config --quiet` trước khi triển khai; cấu hình sai dừng quy trình ngay với exit code `1`. |
| FR-BE—08.3 | Hỗ trợ 3 chế độ khởi chạy: `--clean` / `-Clean` (chạy `docker compose down -v --remove-orphans` trong phạm vi `SMOKE_PROJECT` rồi `docker compose up --build -d`), mặc định (`docker compose up --build -d` giữ volume hiện có), và `--no-up` / `-NoUp` (kiểm thử trên stack đang chạy); PowerShell từ chối `-Clean` nếu `SMOKE_PROJECT` trùng `livingdocs` hoặc `default`. |
| FR-BE—08.4 | Chờ toàn bộ 7 dịch vụ trong `compose.yaml` (`backend-db`, `github-db`, `code-analyzer`, `ai-service`, `github-integration`, `backend`, `frontend`) đạt trạng thái `healthy` (hoặc `running` nếu không khai báo healthcheck) bằng `docker inspect` theo chu kỳ 3 giây trong ngưỡng `VERIFY_TIMEOUT` mặc định `300s`. |
| FR-BE—08.5 | Xác minh migration cơ sở dữ liệu bằng truy vấn `psql` trực tiếp vào container `github-db` (`database github_integration`): số bản ghi trong `flyway_schema_history` có `success = true` phải $> 0$ và số bản ghi có `success = false` phải $= 0$. |
| FR-BE—08.6 | Lưu trạng thái trung gian giữa hai pha (`run_id`, `username`, `email`, `password`, `firstName`, `lastName`, `user_id`, `job_id`, `doc_id`, `expected_version`, `pre_restart_at`) vào file JSON trong thư mục tạm quyền `0o700` (file quyền `0o600`, ghi nguyên tử qua `.tmp` + `os.replace`); cấm lưu state chứa mật khẩu trong `artifacts/` và tự động xóa file tạm sau khi hoàn tất. |
| FR-BE—08.7 | Pha `pre-restart` (`release_smoke_test.py --phase pre-restart`) xác thực qua Backend: lấy `XSRF-TOKEN` từ `GET /api/auth/csrf`, đăng ký tài khoản mới (`POST /api/auth/register` kèm `firstName`, `lastName`) và đăng nhập (`POST /api/auth/login` kèm session cookie và `X-XSRF-TOKEN`). |
| FR-BE—08.8 | Pha `pre-restart` gửi payload phân tích file tới AI Service (`POST /generate` kèm `Authorization: Bearer <secret>` và `X-User-Id`), chờ job hoàn tất (`GET /jobs/{job_id}`, timeout 60s), tạo tài liệu v1 (`POST /internal/documents/from-job`), sau đó cập nhật nội dung (`PUT /internal/documents/{doc_id}/content` với `expected_version: 1`) để tạo v2 và xác nhận `evidence_from_version == 1`. |
| FR-BE—08.9 | Khởi động lại toàn bộ stack bằng `docker compose -p <project> -f compose.yaml restart` (mô phỏng redeploy) và lặp lại kiểm tra `wait_all_healthy` cho cả 7 dịch vụ. |
| FR-BE—08.10 | Pha `post-restart` (`release_smoke_test.py --phase post-restart`) đăng nhập lại trên Backend bằng tài khoản đã tạo ở pha `pre-restart` (`GET /api/auth/csrf` + `POST /api/auth/login`) và gọi `GET /api/auth/me` để xác nhận danh tính người dùng (`email`) bền vững qua restart trên volume `backend-db-data`. |
| FR-BE—08.11 | Pha `post-restart` kiểm tra tính bền vững tài liệu và grounding evidence trên AI Service (`ai-templates` volume): gọi `GET /internal/documents/{doc_id}`, `GET /internal/documents/{doc_id}/evidence?version=1`, `GET /internal/documents/{doc_id}/evidence?version=2` và `GET /internal/documents/{doc_id}/review-evidence?version=2`; xác nhận HTTP `200`, payload JSON có nội dung thực (`len > 50`) và `evidence.job_id == job_id` gốc. |
| FR-BE—08.12 | Duy trì dữ liệu qua restart thông qua 4 named volumes (`backend-db-data`, `github-db-data`, `ai-templates`, `analyzer-data`) và cô lập giao tiếp nội bộ qua 3 Docker networks (`backend-network`, `github-internal`, `analysis-internal`) trong `compose.yaml`. |
| FR-BE—08.13 | Xuất nhật ký và báo cáo kiểm thử vào `artifacts/`: `artifacts/ld-404-smoke-report.log` (log từng bước `[PASS]`/`[FAIL]`), `artifacts/smoke-pre-restart-result.json` và `artifacts/smoke-post-restart-result.json`. |
| FR-BE—08.14 | Tích hợp vào `.github/workflows/ci.yml` qua job `release-smoke-test` (`Release Smoke Test (LD-404)`), phụ thuộc `needs: [docker-compose-validation]`, chạy `./scripts/verify-compose.sh --clean`, dọn dẹp container/volume (`if: always()`) và tải lên artifact `ld-404-smoke-artifacts` (`retention-days: 7`). |
| FR-BE—08.15 | `scripts/release_smoke_test.py` chỉ sử dụng thư viện chuẩn Python (`urllib.request`, `http.cookiejar`, `json`, `argparse`, `tempfile`, `os`), không yêu cầu cài đặt package ngoài. |

## 3. Script điều phối và Endpoints kiểm thử

### Script thực thi

| Lệnh / Script | Tham số & Biến môi trường | Kết quả | Yêu cầu |
|---|---|---|---|
| `./scripts/verify-compose.sh` | `[--clean \| --no-up]`, `SMOKE_PROJECT`, `VERIFY_TIMEOUT` (mặc định `300`), `SMOKE_*_PORT` | Chạy toàn bộ quy trình kiểm thử khói trên Linux/macOS/CI, ghi `artifacts/ld-404-smoke-report.log` | FR-BE—08.1 – FR-BE—08.14 |
| `.\scripts\verify-compose.ps1` | `[-Clean] [-NoUp] [-TimeoutSeconds 300]`, `SMOKE_PROJECT` | Chạy toàn bộ quy trình kiểm thử khói trên Windows PowerShell, tự resolve cổng host thực tế từ Docker | FR-BE—08.1 – FR-BE—08.14 |
| `python3 scripts/release_smoke_test.py` | `--phase {pre-restart\|post-restart}` `--state-file <path>` `--report-file <path>` | Thực thi kịch bản E2E xác thực, sinh/sửa tài liệu và xác minh persistence sau restart | FR-BE—08.6 – FR-BE—08.15 |

### Endpoints Healthcheck & E2E Smoke

| Dịch vụ / Giao thức | Method & Endpoint | Kết quả mong đợi | Yêu cầu |
|---|---|---|---|
| `backend-db` (PostgreSQL 16) | `pg_isready -U livingdocs -d cnpm` | Exit code `0` (healthy) | FR-BE—08.4, FR-BE—08.12 |
| `github-db` (PostgreSQL 16) | `pg_isready -U livingdocs -d github_integration` | Exit code `0`, `flyway_schema_history` có `success = true > 0` và `success = false == 0` | FR-BE—08.4, FR-BE—08.5 |
| `code-analyzer` (FastAPI `:8000`) | `GET /health` | HTTP `200` (healthy) | FR-BE—08.4 |
| `ai-service` (FastAPI `:8001`) | `GET /health` | HTTP `200` (healthy) | FR-BE—08.4 |
| `github-integration` (Spring Boot `:8082`) | `GET /actuator/health` | HTTP `200` (healthy) | FR-BE—08.4 |
| `backend` (Spring Boot `:8080`) | `GET /actuator/health` | HTTP `200` (healthy) | FR-BE—08.4 |
| `frontend` (Nginx `:80`) | `GET /` | HTTP `200`, HTML chứa `id="root"` | FR-BE—08.4 |
| Backend Auth & Session | `GET /api/auth/csrf`, `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` | HTTP `200`/`201`, trả `userId`, duy trì session cookie & `email` qua restart | FR-BE—08.7, FR-BE—08.10 |
| AI Service Generation & Versioning | `POST /generate`, `GET /jobs/{job_id}`, `POST /internal/documents/from-job`, `PUT /internal/documents/{doc_id}/content` | Tạo `job_id`, sinh `doc_id` v1, cập nhật v2 với `evidence_from_version == 1` | FR-BE—08.8 |
| AI Service Persistence & Evidence | `GET /internal/documents/{doc_id}`, `GET .../evidence?version=1\|2`, `GET .../review-evidence?version=2` | HTTP `200`, JSON `len > 50`, `evidence.job_id == job_id` sau restart | FR-BE—08.11 |

Ví dụ payload `POST /generate` và `PUT /internal/documents/{doc_id}/content` trong `release_smoke_test.py` (kèm header `Authorization: Bearer <secret>` và `X-User-Id`):
- `POST /generate`: `{"scope": "file", "target": "smoke.py", "files": [{"path": "smoke.py", "language": "python", "status": "ok", "functions": [{"name": "smoke_fn", "parameters": [], "source": "def smoke_fn():\n    return 42"}]}]}`
- `PUT /internal/documents/{doc_id}/content`: `{"expected_version": 1, "content": "# Smoke v2\n\nUpdated during LD-404 smoke review flow"}`

## 4. Luồng chính

1. Runner hoặc developer khởi chạy `./scripts/verify-compose.sh --clean` (hoặc `.\scripts\verify-compose.ps1 -Clean`).
2. Script nạp biến từ `.env` (nếu có), thiết lập `SMOKE_PROJECT=livingdocs-smoke`, ánh xạ cổng riêng và tạo thư mục tạm quyền `0o700` cho `SMOKE_STATE_FILE`.
3. Kiểm tra cấu hình bằng `docker compose -p livingdocs-smoke -f compose.yaml config --quiet`.
4. Nếu truyền cờ `--clean` / `-Clean`, xóa toàn bộ container và volume của `livingdocs-smoke` bằng `docker compose down -v --remove-orphans`, sau đó build và khởi chạy stack bằng `docker compose up --build -d`.
5. Chờ lần lượt 7 dịch vụ (`backend-db`, `github-db`, `code-analyzer`, `ai-service`, `github-integration`, `backend`, `frontend`) đạt `healthy`/`running` trong giới hạn `300s`.
6. Truy vấn `flyway_schema_history` trên `github-db` để xác nhận toàn bộ phiên bản migration đã chạy thành công và không có bản ghi lỗi.
7. Chạy `python3 scripts/release_smoke_test.py --phase pre-restart`: đăng ký user mới trên Backend, đăng nhập, gọi AI Service `POST /generate`, tạo document v1 từ job, cập nhật nội dung lên v2 (`evidence_from_version == 1`) và lưu state vào file tạm bảo mật.
8. Khởi động lại toàn bộ dịch vụ bằng `docker compose -p livingdocs-smoke -f compose.yaml restart` và chờ cả 7 dịch vụ phục hồi trạng thái `healthy`/`running`.
9. Chạy `python3 scripts/release_smoke_test.py --phase post-restart`: đăng nhập lại user đã tạo, kiểm tra `GET /api/auth/me`, kiểm tra `GET /internal/documents/{doc_id}`, `evidence` của v1 & v2 (`job_id` khớp gốc, `len > 50`) và `review-evidence` của v2.
10. Xóa file state tạm bảo mật, hoàn tất ghi log vào `artifacts/ld-404-smoke-report.log` và trả exit code `0`.

## 5. Luồng lỗi

| Trường hợp | Điều kiện / Mã lỗi | Kết quả |
|---|---|---|
| Cấu hình `compose.yaml` sai hoặc thiếu biến bắt buộc | `docker compose config --quiet` trả exit code $\neq 0$ | Ghi `[FAIL] compose.yaml is invalid` vào report và dừng với exit code `1` |
| Chạy `-Clean` trên PowerShell với project chính | `SMOKE_PROJECT` là `livingdocs` hoặc `default` | Từ chối thực thi (`Refusing to --Clean`), thoát với exit code `1` để bảo vệ volume dev |
| Container không đạt `healthy` đúng hạn | Quá `VERIFY_TIMEOUT` (mặc định `300s`) trước hoặc sau restart | Ghi `[FAIL] <service> did not become healthy within 300s` và dừng với exit code `1` |
| Flyway migration trên `github-db` thiếu hoặc lỗi | `success = true` bằng $0$ hoặc `success = false` $> 0$ | Ghi `[FAIL] github-db Flyway migrations...` và dừng với exit code `1` |
| Thiếu hoặc sai `INTERNAL_API_SECRET` / `AI_SERVICE_INTERNAL_SECRET` | AI Service trả HTTP `401`/`403` cho `/generate` hoặc `/internal/documents/*` | `assert_true` ném `AssertionError`, in `[FAIL]` ra `stderr` và thoát exit code `1` |
| Đăng ký / đăng nhập Backend thất bại | `POST /api/auth/register` ($\notin \{200, 201\}$) hoặc `POST /api/auth/login` ($\neq 200$) | Dừng pha kiểm thử với exit code `1` |
| Kế thừa evidence khi tạo v2 không khớp | `PUT /internal/documents/{id}/content` trả `evidence_from_version != 1` | Dừng pha `pre-restart` với exit code `1` |
| Truyền đường dẫn `--state-file` nằm trong `artifacts/` | Đường dẫn chứa thư mục `artifacts` | Thoát ngay với thông báo cấm lưu state chứa mật khẩu trong `artifacts/` |
| Dữ liệu mất hoặc sai lệch sau `docker compose restart` | Re-login lỗi, `GET /internal/documents/{doc_id}` trả `404`, `evidence.job_id != job_id` hoặc `len(evidence) <= 50` | Pha `post-restart` thất bại với exit code `1` |

## 6. Quy tắc nghiệp vụ

- Toàn bộ smoke test chạy trên project name riêng (`livingdocs-smoke`) và dải cổng riêng để cô lập hoàn toàn với môi trường phát triển đang vận hành (`livingdocs`).
- File state trung gian chứa thông tin đăng nhập kiểm thử (`password`) chỉ tồn tại trong thư mục tạm quyền `0o700` (file `0o600`), tuyệt đối không ghi vào `artifacts/` để tránh lộ credential khi commit hoặc upload CI artifact, và bị xóa ngay sau khi pha `post-restart` kết thúc.
- `release_smoke_test.py` không dùng thư viện bên thứ ba; chỉ dùng thư viện chuẩn Python để chạy đồng nhất trên Ubuntu CI runner và máy local Windows/macOS/Linux.
- Gọi AI Service hỗ trợ chế độ offline (khi không cấu hình `ANTHROPIC_API_KEY`, `/generate` xử lý đồng bộ/nhanh) và vẫn giữ vòng polling tối đa 60 giây cho trường hợp chạy bất đồng bộ.
- Mọi request tới endpoint `/internal/documents/*` của AI Service bắt buộc đính kèm cả `Authorization: Bearer <secret>` và `X-User-Id`.
- Kiểm tra persistence của evidence không chỉ dừng ở HTTP `200` mà bắt buộc đối chiếu `evidence.job_id` trùng với `job_id` ban đầu và kích thước payload JSON $> 50$ byte.
- Không che giấu lỗi bằng `|| true` ở các bước kiểm tra/build/test chính; lệnh dọn dẹp `docker compose -p livingdocs-smoke down -v --remove-orphans || true` trong CI chỉ chạy ở bước cleanup cuối job (`if: always()`).

## 7. Tiêu chí chấp nhận

- **AC-BE-08.1:** `docker compose -p livingdocs-smoke -f compose.yaml config --quiet` hợp lệ và khởi tạo thành công toàn bộ 7 dịch vụ (`backend-db`, `github-db`, `code-analyzer`, `ai-service`, `github-integration`, `backend`, `frontend`) ở trạng thái `healthy`/`running`.
- **AC-BE-08.2:** Migration cơ sở dữ liệu Flyway trên `github-db` áp dụng đầy đủ (`success = true > 0`) và không có bản ghi lỗi (`success = false == 0`).
- **AC-BE-08.3:** Pha `pre-restart` hoàn tất 100% luồng E2E: đăng ký/đăng nhập Backend, sinh tài liệu qua AI Service (`POST /generate`), tạo document v1 (`from-job`) và cập nhật v2 kế thừa evidence (`evidence_from_version == 1`).
- **AC-BE-08.4:** Sau `docker compose restart`, cả 7 dịch vụ phục hồi trạng thái `healthy`/`running` trong `VERIFY_TIMEOUT`.
- **AC-BE-08.5:** Pha `post-restart` xác nhận dữ liệu bền vững qua restart: tài khoản người dùng đăng nhập lại thành công (`/api/auth/me` trả đúng `email`), document v1/v2 cùng `evidence` (`job_id` khớp gốc, `len > 50`) và `review-evidence` v2 truy vấn thành công.
- **AC-BE-08.6:** File state tạm chứa mật khẩu nằm ngoài `artifacts/` với quyền hạn chế và được dọn dẹp sạch sau khi chạy.
- **AC-BE-08.7:** Kết quả kiểm thử được ghi nhận đầy đủ trong `artifacts/ld-404-smoke-report.log` và các file JSON báo cáo pha chạy.
- **AC-BE-08.8:** Job CI `release-smoke-test` trong `.github/workflows/ci.yml` chạy sau `docker-compose-validation`, thực thi `./scripts/verify-compose.sh --clean`, dọn dẹp stack và upload `ld-404-smoke-artifacts`.

## 8. Kiểm thử

Thực thi kiểm thử khói triển khai trực tiếp bằng `./scripts/verify-compose.sh --clean` (Linux/macOS/CI) hoặc `.\scripts\verify-compose.ps1 -Clean` (Windows PowerShell). Kết quả chạy đã được ghi nhận trong `artifacts/ld-404-smoke-report.log` xác nhận toàn bộ 7 container đạt `healthy/running` cả trước và sau `docker compose restart`, `github-db` áp dụng thành công 9 phiên bản Flyway migration với 0 lỗi, và cả hai pha `pre-restart` lẫn `post-restart` đều đạt `PASSED` (đối chiếu với bản ghi E2E `artifacts/smoke-e2e-results.json`: `status: "PASSED"`, `expected_version: 2`). Trên GitHub Actions, workflow `.github/workflows/ci.yml` tự động chạy job `Release Smoke Test (LD-404)` phụ thuộc `docker-compose-validation`, dọn dẹp stack `livingdocs-smoke` với `if: always()` và xuất artifact `ld-404-smoke-artifacts`.