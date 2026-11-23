# FR-BE—02 GitHub Actions Integration & Documentation Drift Guard

| Mục | Nội dung |
|---|---|
| Story Jira | LD-376 [GitHub Actions Integration] Implement GitHub Actions Integration (Epic LD-358) |
| Task đã làm | LD-377 – LD-381 (`LD-377` Configure GitHub Actions Workflow, `LD-378` Implement Pull Request Trigger, `LD-379` Integrate Documentation Drift Verification, `LD-380` Integrate Automated Testing, `LD-381` Implement Workflow Result Reporting) |
| Người thực hiện | Nguyễn Lê Minh |
| Nhánh / PR & Trạng thái | Đã hợp nhất vào `main` |
| Thành phần | `.github/workflows/ci.yml`, `scripts/check_documentation_drift.py`, `tests/test_documentation_drift.py`, `pytest.ini`, `compose.yaml` cùng các module được kiểm thử trong CI (`backend/`, `frontend/`, `services/github-integration-service/`, `ai-service/`, `app/`, `code-analyzer/`) |
| Tác nhân | GitHub Actions (`push`, `pull_request`, `workflow_dispatch`); Developers |

## 1. Mô tả

Chức năng tích hợp GitHub Actions (`LivingDocs CI`) tự động hóa quy trình kiểm tra chất lượng mã nguồn, chạy kiểm thử tự động đa dịch vụ, xác thực cấu hình Docker Compose và báo cáo kết quả mỗi khi mã nguồn được đẩy lên nhánh làm việc hoặc khi tạo/cập nhật Pull Request vào `main`. Song song đó, bộ công cụ **Documentation Drift Guard** (`scripts/check_documentation_drift.py`) quét toàn bộ tài liệu Markdown trong repository để phát hiện các liên kết nội bộ bị hỏng hoặc trỏ ra ngoài phạm vi repository. Các job trong workflow chạy độc lập trên runner `ubuntu-latest` và hiển thị trạng thái pass/fail riêng biệt trên GitHub Actions.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-BE—02.1 | Cấu hình workflow `LivingDocs CI` trong `.github/workflows/ci.yml` kích hoạt khi `push` lên nhánh `main` hoặc `LD-*`, khi `pull_request` nhắm vào `main` (mặc định `opened`, `synchronize`, `reopened`), và khi chạy thủ công qua `workflow_dispatch`. |
| FR-BE—02.2 | Thiết lập quyền tối thiểu `contents: read` ở cấp workflow và cấu hình `concurrency` theo nhóm `livingdocs-ci-${{ github.ref }}` với `cancel-in-progress: true` để hủy các lượt chạy cũ cùng nhánh/PR khi có commit mới. |
| FR-BE—02.3 | Job **Backend Build and Test** (`backend-build-test`, timeout 15 phút): khởi tạo service `postgres:18` (`POSTGRES_DB=cnpm`, `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`, cổng `5432`, healthcheck `pg_isready`), cài Java Temurin 21 kèm cache Maven theo `backend/pom.xml`, kiểm tra tồn tại `README.md`, `backend/pom.xml`, `.github/workflows/ci.yml`, cấp quyền thực thi `backend/mvnw` và chạy `./backend/mvnw --batch-mode --no-transfer-progress -f backend/pom.xml clean verify`. |
| FR-BE—02.4 | Job **Frontend Build and Test** (`frontend-build`, timeout 10 phút): cài Node.js 24 kèm cache npm theo `frontend/package-lock.json`, thực thi tuần tự `npm ci`, `npm run lint` và `npm run build` trong thư mục `frontend/`. |
| FR-BE—02.5 | Job **GitHub Integration Service Test** (`github-integration-test`, timeout 15 phút): cài Java Temurin 21 kèm cache Maven theo `services/github-integration-service/pom.xml`, chạy `mvn ... verify` với H2 database và mocked GitHub, sau đó chạy live test `GitHubRepositoryFetcherLiveTest` với `GITHUB_LIVE_TEST=true`, `GITHUB_LIVE_REPO=${{ github.repository }}` và `GITHUB_TOKEN=${{ secrets.GITHUB_TOKEN }}`. |
| FR-BE—02.6 | Upload báo cáo kiểm thử `services/github-integration-service/target/surefire-reports/` thành artifact `github-integration-test-reports` qua `actions/upload-artifact@v4` với điều kiện `if: always()` và `if-no-files-found: ignore` để lưu giữ log ngay cả khi test thất bại. |
| FR-BE—02.7 | Job **AI Service Build and Test** (`ai-service-test`, timeout 10 phút): cài Python 3.12 kèm cache pip theo `ai-service/requirements.txt`, cài đặt dependencies và chạy `python -m pytest -q` trong `ai-service/`. |
| FR-BE—02.8 | Job **AI Service Integration Test** (`ai-service-integration`, timeout 10 phút): cài dependencies của `ai-service` cùng `javalang`, khởi động nền Code Analyzer (`app.main:app`, port `8000`, working directory `ai-service/tests/integration/fixtures`) và AI Service (`main:app`, port `8001`), poll tối đa 30 giây tới `/health` và `/openapi.json`, chạy `python -m pytest -m live -v tests/integration` với `ANALYZER_URL` và `AI_SERVICE_URL`. |
| FR-BE—02.9 | Khi job `ai-service-integration` thất bại (`if: failure()`), tự động xuất log `$RUNNER_TEMP/analyzer.log` và `$RUNNER_TEMP/ai-service.log` ra console GitHub Actions để phục vụ chẩn đoán lỗi. |
| FR-BE—02.10 | Job **Docker Compose Validation** (`docker-compose-validation`, timeout 30 phút): truyền biến môi trường giả lập `TOKEN_ENCRYPTION_KEY` và `GITHUB_INTEGRATION_INTERNAL_SECRET`, kiểm tra cú pháp cấu hình bằng `docker compose -f compose.yaml config --quiet` và build thử nghiệm các image `backend`, `ai-service`, `code-analyzer`, `github-integration`, `frontend`. |
| FR-BE—02.11 | Script **Documentation Drift Guard** (`scripts/check_documentation_drift.py`): xác định `ROOT = Path(__file__).resolve().parents[1]`, quét đệ quy `ROOT.rglob("*.md")` và bỏ qua các thư mục `.git`, `node_modules`, `target`, `dist`, `.venv`, `venv`. |
| FR-BE—02.12 | Trích xuất liên kết Markdown dạng inline `[...](https://...)` (loại trừ ảnh `![...]`) và reference definition `[label]: <destination>`, hỗ trợ cả dạng `<...>` lẫn token không khoảng trắng có kèm title; đọc file UTF-8 với `errors="replace"`. |
| FR-BE—02.13 | Chuẩn hóa đích liên kết bằng `unquote` và `urlsplit`; bỏ qua external URL có scheme (`http:`, `https:`, `mailto:`, ...), protocol-relative URL (`//...`) và anchor-only link (`#...`). |
| FR-BE—02.14 | Resolve đường dẫn tương đối từ thư mục chứa file Markdown và đối chiếu ranh giới repository (`ROOT` hoặc thư mục cha khi test độc lập): báo `<path>: link escapes repository: <raw>` nếu vượt ra ngoài ranh giới; báo `<path>: missing local link: <raw>` nếu đích không tồn tại. |
| FR-BE—02.15 | Giao diện CLI `python scripts/check_documentation_drift.py`: nếu hợp lệ toàn bộ, in `Documentation drift check passed: checked <N> Markdown files.` và trả exit code `0`; nếu có lỗi, in `Documentation drift detected: broken local Markdown links found.` kèm danh sách lỗi và trả exit code `1`. |

## 3. API / Giao diện

| Loại | Thành phần / Lệnh / Job | Mô tả | Yêu cầu |
|---|---|---|---|
| Workflow | `.github/workflows/ci.yml` (`LivingDocs CI`) | Pipeline CI đa job chạy trên `ubuntu-latest` cho `push`, `pull_request`, `workflow_dispatch` | FR-BE—02.1 – FR-BE—02.10 |
| Trigger | `push` (`main`, `LD-*`) | Kích hoạt kiểm tra tự động khi đẩy mã nguồn lên nhánh chính hoặc nhánh task | FR-BE—02.1 |
| Trigger | `pull_request` vào `main` | Kích hoạt kiểm tra tự động cho PR tạo mới hoặc cập nhật | FR-BE—02.1 |
| Trigger | `workflow_dispatch` | Cho phép kích hoạt thủ công pipeline từ tab GitHub Actions | FR-BE—02.1 |
| CLI | `python scripts/check_documentation_drift.py` | Kiểm tra liên kết cục bộ trong toàn bộ file `*.md` của repository | FR-BE—02.11 – FR-BE—02.15 |
| Config | `pytest.ini` (`testpaths = tests`) | Cấu hình gốc pytest để thực thi bộ test drift guard | FR-BE—02.11 – FR-BE—02.15 |
| Artifact | `github-integration-test-reports` | Lưu trữ XML/TXT report từ `services/github-integration-service/target/surefire-reports/` | FR-BE—02.6 |

## 4. Luồng chính

1. Developer thực hiện `push` lên nhánh `main`/`LD-*`, tạo/cập nhật `pull_request` vào `main`, hoặc kích hoạt `workflow_dispatch`.
2. GitHub Actions kiểm tra nhóm `concurrency` `livingdocs-ci-${{ github.ref }}`; nếu có run cũ đang chạy trên cùng nhánh/PR thì hủy run cũ.
3. Các job kiểm thử được khởi tạo song song trên runner `ubuntu-latest`:
   - `backend-build-test` chờ container `postgres:18` healthy và chạy Maven `clean verify`.
   - `frontend-build` cài npm dependencies và chạy `npm run lint` + `npm run build`.
   - `github-integration-test` chạy Maven `verify` (unit/mock test) và live test tới GitHub API bằng `secrets.GITHUB_TOKEN`, sau đó upload surefire reports.
   - `ai-service-test` chạy unit/API test của AI Service qua `pytest`.
   - `ai-service-integration` khởi chạy song song Code Analyzer (`:8000`) và AI Service (`:8001`), chờ healthcheck sẵn sàng rồi chạy `pytest -m live`.
   - `docker-compose-validation` xác thực cấu hình `compose.yaml` và build toàn bộ Docker images.
4. Khi chạy kiểm tra tài liệu (`python scripts/check_documentation_drift.py`), script quét tất cả file `.md`, phân tích cú pháp liên kết nội bộ, xác minh đích tồn tại trong phạm vi repository và trả về mã thoát `0` (pass) hoặc `1` (fail kèm chi tiết file và đường dẫn lỗi).
5. Kết quả từng job được báo cáo trực tiếp trên giao diện Pull Request / Commit check của GitHub để làm điều kiện nghiệm thu trước khi merge.

## 5. Luồng lỗi

| Trường hợp | Điều kiện / Nguyên nhân | Kết quả |
|---|---|---|
| Liên kết Markdown cục bộ trỏ tới file/thư mục không tồn tại | Đường dẫn tương đối không tồn tại trên đĩa | In `<file>: missing local link: <raw>` và thoát với exit code `1` |
| Liên kết Markdown vượt ra ngoài thư mục gốc repository | Dùng nhiều `../` vượt khỏi `ROOT` | In `<file>: link escapes repository: <raw>` và thoát với exit code `1` |
| File Markdown có byte lỗi encoding UTF-8 | Ký tự không hợp lệ theo chuẩn UTF-8 | Đọc an toàn nhờ `errors="replace"` mà không crash script |
| Job kiểm thử hoặc build thất bại | Test fail, lỗi lint/build, sai cú pháp `compose.yaml` | Job tương ứng báo failed (exit code `≠ 0`), các job độc lập khác vẫn hoàn tất và báo cáo trạng thái riêng |
| `ai-service-integration` không khởi động kịp trong 30 giây hoặc fail test | Quá 30 lần poll `/health` và `/openapi.json` hoặc `pytest -m live` fail | Job fail và bước `Dump service logs on failure` in toàn bộ `analyzer.log` và `ai-service.log` |
| `github-integration-test` fail | Lỗi biên dịch hoặc test failure trong Maven `verify` | Bước `Upload GitHub integration test reports` vẫn chạy (`if: always()`) để lưu artifact phục vụ debug |

## 6. Quy tắc nghiệp vụ

- Mỗi job trong `.github/workflows/ci.yml` phải thiết lập `timeout-minutes` tường minh (`10` đến `30` phút) để tránh treo runner.
- Workflow chỉ yêu cầu quyền tối thiểu `contents: read`; các thông tin nhạy cảm (`TOKEN_ENCRYPTION_KEY`, `GITHUB_INTEGRATION_INTERNAL_SECRET`) trong job `docker-compose-validation` chỉ dùng chuỗi giả lập dành riêng cho CI.
- Documentation Drift Guard chỉ kiểm tra liên kết cục bộ trong repository; các liên kết web (`http://`, `https://`), email (`mailto:`), protocol-relative (`//`) và anchor nội trang (`#section`) được bỏ qua hợp lệ.
- Các thư mục build/dependency/môi trường ảo (`.git`, `node_modules`, `target`, `dist`, `.venv`, `venv`) luôn bị loại trừ khỏi quá trình quét Markdown để tránh dương tính giả.
- `scripts/check_documentation_drift.py` chỉ sử dụng thư viện chuẩn Python (`pathlib`, `re`, `sys`, `urllib.parse`) để có thể chạy trực tiếp ở mọi môi trường mà không cần cài đặt thêm package.

## 7. Tiêu chí chấp nhận

- **AC-BE-02.1:** Push lên `main` hoặc nhánh có tiền tố `LD-*` tự động kích hoạt workflow `LivingDocs CI`.
- **AC-BE-02.2:** Tạo mới hoặc cập nhật Pull Request vào `main` tự động kích hoạt workflow và hiển thị trạng thái kiểm tra trên PR.
- **AC-BE-02.3:** Kích hoạt thủ công qua `workflow_dispatch` hoạt động bình thường; các lượt chạy trùng nhánh tự động hủy run cũ (`cancel-in-progress: true`).
- **AC-BE-02.4:** Toàn bộ 6 job (`backend-build-test`, `frontend-build`, `github-integration-test`, `ai-service-test`, `ai-service-integration`, `docker-compose-validation`) thực thi đầy đủ bước kiểm tra và báo cáo trạng thái riêng biệt trên GitHub Actions.
- **AC-BE-02.5:** `scripts/check_documentation_drift.py` phát hiện chính xác liên kết cục bộ bị thiếu hoặc thoát khỏi repository (exit code `1`), đồng thời bỏ qua external URL và anchor hợp lệ (exit code `0`).
- **AC-BE-02.6:** Bộ kiểm thử đơn vị `tests/test_documentation_drift.py` chạy qua `pytest` đạt 100% pass.

## 8. Kiểm thử

- **Unit test Documentation Drift Guard (`tests/test_documentation_drift.py`):** Kiểm tra 4 nhóm kịch bản cốt lõi:
  1. `test_valid_links_pass`: liên kết file tương đối hợp lệ, anchor `#section`, external `https://` và liên kết có query/anchor (`docs/guide.md#usage`) trả về exit code `0`.
  2. `test_missing_local_link_fails`: liên kết tới `docs/does-not-exist.md` báo lỗi `missing local link` và trả về exit code `1`.
  3. `test_link_escaping_repository_fails`: liên kết `../outside.md` vượt ranh giới repository báo lỗi `link escapes repository` và trả về exit code `1`.
  4. `test_reference_style_link_checked`: liên kết dạng reference `[ref]: docs/missing-ref.md` cũng được kiểm tra và báo lỗi chính xác.
- **Kiểm thử tích hợp CI (`.github/workflows/ci.yml`):** Toàn bộ các job build, unit test, integration test đa dịch vụ (Code Analyzer + AI Service) và xác thực Docker Compose được vận hành tự động trên GitHub Actions runner `ubuntu-latest`.