# BE2 — LD-376 CI và Documentation Drift Guard

| Mục | Nội dung |
|---|---|
| Story Jira | LD-376 CI and Documentation Drift Guard |
| Task đã làm | — |
| Người thực hiện | — |
| Thành phần | `.github/workflows/ci.yml`, `scripts/check_documentation_drift.py`, `tests/test_documentation_drift.py`, các module backend/frontend/analyzer/AI/service, `compose.yaml` |
| Tác nhân | GitHub Actions (push/PR/dispatch), developers |

## 1. Mô tả

Pipeline GitHub Actions tự động kiểm tra repository khi push/PR, đồng thời có chức năng **Documentation Drift Verification** kiểm tra các liên kết Markdown nội bộ bị hỏng. Pipeline kiểm tra nhiều thành phần độc lập: drift guard, backend, frontend, GitHub integration service, AI service, integration test AI + analyzer, Docker Compose validation. Mỗi job có trạng thái pass/fail độc lập.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| LD-376.1 | Drift guard phát hiện link local trong `.md` trỏ đến file/thư mục không tồn tại hoặc trỏ ra ngoài repo. External link, protocol-relative URL và anchor-only link không bị coi là file local. |
| LD-376.2 | Root = `Path(__file__).resolve().parents[1]`; quét `ROOT.rglob("*.md")`; bỏ qua `.git`, `node_modules`, `target`, `dist`, `.venv`, `venv`. |
| LD-376.3 | Nhận diện inline link `[...] (destination)` (không bắt image `![](...)`) và reference definition `[label]: destination`; hỗ trợ destination `<...>` hoặc token không khoảng trắng, có thể có title. |
| LD-376.4 | Đọc UTF-8 (lỗi decode thay bằng ký tự thay thế), thu thập destination, URL-decode bằng `unquote`, parse `urlsplit`; bỏ qua URL có scheme, protocol-relative (`//...`) và destination không có path (anchor-only). |
| LD-376.5 | Resolve path tương đối từ thư mục chứa Markdown; kiểm tra nằm trong root bằng `resolve()` + `relative_to(ROOT)`; báo `link escapes repository: <raw>` khi vượt root; báo `missing local link: <raw>` khi đích không tồn tại; hiển thị path tương đối với root khi có thể. |
| LD-376.6 | CLI chạy `python scripts/check_documentation_drift.py`: pass in `Documentation drift check passed: checked N Markdown files.` + exit 0; fail in `Documentation drift detected: broken local Markdown links found.` + liệt kê lỗi + exit 1. |
| LD-376.7 | Workflow `LivingDocs CI` trigger: `push` lên `main`/`LD-*`, `pull_request` vào `main` (types `opened`, `synchronize`, `reopened`, `ready_for_review`), `workflow_dispatch`. Permission tối thiểu `contents: read`. Concurrency group `livingdocs-ci-${{ github.ref }}`, `cancel-in-progress: true`. |
| LD-376.8 | Job Documentation Drift Verification: `ubuntu-latest`, timeout 5 phút, `actions/checkout@v4`, `actions/setup-python@v5` Python 3.12, chạy script, cài `pytest`/`pytest-html`, chạy `pytest -q tests/test_documentation_drift.py`, ghi `GITHUB_STEP_SUMMARY` PASS/FAIL. |
| LD-376.9 | Job Backend: `ubuntu-latest`, 15 phút, PostgreSQL service (`cnpm`/`postgres`/`postgres` port 5432, healthcheck `pg_isready`), Java Temurin 27, cache Maven theo `backend/pom.xml`, kiểm tra file README/pom/workflow tồn tại, cấp quyền thực thi `backend/mvnw`, chạy `./backend/mvnw --batch-mode --no-transfer-progress -f backend/pom.xml clean verify`, env DB `jdbc:postgresql://localhost:5432/cnpm`. |
| LD-376.10 | Job Frontend: `ubuntu-latest`, 10 phút, Node 24, cache npm theo `frontend/package-lock.json`, chạy `npm ci`, `npm run lint`, `npm run build` trong `frontend/`. |
| LD-376.11 | Job GitHub Integration Service: Java 21, Maven test với H2/mock; live test nếu `GITHUB_LIVE_TEST=true`, `GITHUB_LIVE_REPO`, `GITHUB_TOKEN`; upload `services/github-integration-service/target/surefire-reports/` bằng `actions/upload-artifact@v4`, `if: always()`. |
| LD-376.12 | Job AI Service: Python 3.12, cài `ai-service/requirements.txt`, chạy `python -m pytest -q` trong `ai-service`. |
| LD-376.13 | Job AI Service Integration: Python 3.12, cài AI deps + `javalang`, khởi động analyzer Uvicorn port 8000, AI service port 8001, poll health/openapi chờ sẵn sàng, chạy integration với `ANALYZER_URL=http://localhost:8000`, `AI_SERVICE_URL=http://localhost:8001`; in log hai service khi fail. |
| LD-376.14 | Job Docker Compose Validation kiểm tra cấu hình Compose và cấu hình service theo đúng workflow snapshot, không đổi sang deploy thật. |
| LD-376.15 | Unit test tối thiểu: `test_existing_local_markdown_link_passes`, `test_missing_local_markdown_link_is_reported` (chứa `missing local link`). |

## 3. API / Giao diện

| Loại | Command / Event | Kết quả | Yêu cầu |
|---|---|---|---|
| CLI | `python scripts/check_documentation_drift.py` | exit 0 khi pass, exit 1 khi có lỗi | LD-376.6 |
| Unit test | `python -m pytest -q tests/test_documentation_drift.py` | Test pass/fail độc lập | LD-376.15 |
| Trigger | `push` lên `main`/`LD-*` | Workflow chạy | LD-376.7 |
| Trigger | `pull_request` vào `main` (opened/synchronize/reopened/ready_for_review) | Workflow chạy | LD-376.7 |
| Trigger | `workflow_dispatch` | Workflow chạy thủ công | LD-376.7 |
| Job | Documentation Drift Verification | PASS/FAIL + summary | LD-376.8 |
| Job | Backend Build and Test | Maven `clean verify` | LD-376.9 |
| Job | Frontend Build | `npm ci` + `lint` + `build` | LD-376.10 |
| Job | GitHub Integration Service Test | Maven test + upload artifact | LD-376.11 |
| Job | AI Service Test | `pytest -q` | LD-376.12 |
| Job | AI Service Integration | Chạy integration test 2 service thật | LD-376.13 |
| Job | Docker Compose Validation | Parse compose + kiểm tra service | LD-376.14 |

## 4. Luồng chính

1. Push/PR/dispatch khớp trigger kích hoạt workflow `LivingDocs CI`.
2. Concurrency group hủy run cũ cùng ref khi có run mới.
3. Job Documentation Drift Verification: cài Python 3.12, chạy scanner; nếu pass → exit 0 + summary PASS; nếu fail → exit 1 + summary FAIL.
4. Job Backend Build and Test: khởi động PostgreSQL service, chờ healthy, chạy Maven `clean verify` với DB env.
5. Job Frontend Build: `npm ci` → `npm run lint` → `npm run build`.
6. Job GitHub Integration Service Test: Maven test H2/mock; live test nếu có `GITHUB_LIVE_TEST=true`; upload `surefire-reports/` kể cả khi fail.
7. Job AI Service Test: cài requirements, chạy pytest.
8. Job AI Service Integration: khởi động analyzer + AI service, poll health, chạy integration test.
9. Job Docker Compose Validation: kiểm tra compose.
10. Kết quả từng job được tổng hợp trạng thái workflow.

## 5. Luồng lỗi

| Trường hợp | Kết quả |
|---|---|
| Markdown link local trỏ đến file không tồn tại | In `missing local link: <raw>`, exit 1 |
| Link trỏ ra ngoài repository | In `link escapes repository: <raw>`, exit 1 |
| External URL, protocol-relative URL, anchor-only | Không bị coi là lỗi |
| File Markdown decode lỗi | Đọc bằng ký tự thay thế, không fail toàn bộ |
| Bất kỳ step bắt buộc nào fail | Job tương ứng fail |
| Test GitHub Integration Service fail | Artifact `surefire-reports/` vẫn được upload (`if: always()`) |
| AI Service Integration fail | In log analyzer + AI service để debug |
| Markdown link bị hỏng | Chỉ báo lỗi, không tự sửa link |

## 6. Quy tắc nghiệp vụ

- Drift guard chỉ kiểm tra local file reference, không crawl/kiểm tra URL internet.
- Không tự deploy production.
- Không tự sửa link Markdown bị hỏng.
- Không commit thay đổi ngược về repository.
- Không thay thế unit/integration tests của từng module.
- Không đặt secret thật trực tiếp trong YAML; dùng GitHub Actions secrets.
- Artifact upload phải `if: always()` để giữ báo cáo khi test fail.
- Mỗi job có trạng thái pass/fail độc lập.

## 7. Tiêu chí chấp nhận

- **AC-LD-376.1:** Push lên branch `LD-*` kích hoạt workflow.
- **AC-LD-376.2:** PR vào `main` kích hoạt workflow.
- **AC-LD-376.3:** Manual dispatch hoạt động.
- **AC-LD-376.4:** Markdown link local tồn tại được chấp nhận.
- **AC-LD-376.5:** Link local thiếu file bị báo lỗi và exit code khác 0.
- **AC-LD-376.6:** Link đi ra ngoài repository bị báo lỗi.
- **AC-LD-376.7:** External link và anchor-only link không bị coi là file thiếu.
- **AC-LD-376.8:** Thư mục cache/build được bỏ qua.
- **AC-LD-376.9:** Backend/Frontend/Service jobs chạy đúng runtime và lệnh đã mô tả.
- **AC-LD-376.10:** Test report được upload khi job có cấu hình upload, kể cả khi test fail.

## 8. Kiểm thử

`tests/test_documentation_drift.py` (unit) + các test module backend/frontend/AI/service được workflow gọi. Nên bổ sung test path traversal, URL external, anchor-only, reference-style links, URL-encoded path và ignored directories mà không đổi contract hiện tại.