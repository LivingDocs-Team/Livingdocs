# Documentation Drift Detection (LD-145)

Phát hiện **tài liệu bị lệch so với mã nguồn** do một Pull Request gây ra: PR đổi tên/xóa hàm, đổi tham số, đổi route API, xóa file... nhưng tài liệu vẫn mô tả bản cũ. Module chỉ dùng thư viện chuẩn của Python (3.10+), không cần cài thêm gói nào ngoài `git`.

## Các task Jira → module

| Task | Chức năng | Module |
|---|---|---|
| LD-146 Analyze Pull Request Changes | Đọc diff của PR, trích entity (class/hàm/method/route) trước và sau, so sánh | `diff_parser.py`, `entities.py`, `pr_analyzer.py` |
| LD-148 Identify Affected Documentation | Tìm tài liệu nhắc tới code đã đổi (theo tên, route, đường dẫn file, link) | `doc_scanner.py`, `affected.py` |
| LD-147 Detect Documentation Drift | Áp dụng rule để quyết định tài liệu nào thực sự lỗi thời, kèm độ tin cậy | `detector.py` |
| LD-149 Generate Drift Evidence | Bằng chứng cho từng finding + báo cáo JSON/Markdown | `evidence.py`, `report.py` |
| LD-150 Test Drift Detection | Test đơn vị, tích hợp, end-to-end trên git thật, job CI | `tests/test_drift_*.py`, job `documentation-drift` |

Luồng: `diff → EntityChange → AffectedReference → DriftFinding → DriftEvidence → báo cáo`.

## Cách dùng

```bash
# Trong CI hoặc trên máy: so sánh nhánh hiện tại với main (dùng merge-base)
python -m drift --base origin/main --head HEAD --output-dir drift-report

# Chỉ có file diff (working tree là bản sau PR; bản cũ được dựng lại từ diff)
python -m drift --diff-file pr.diff

# Làm CI thất bại khi có finding từ mức high trở lên (mặc định: chỉ báo cáo)
python -m drift --base origin/main --fail-on high
```

Tùy chọn: `--format markdown|json|both`, `--min-confidence 0.3`, `--ignore GLOB` (lặp lại được; `CHANGELOG*` luôn bị bỏ qua), `--repository`. Mã thoát: `0` bình thường, `1` vượt ngưỡng `--fail-on`, `2` lỗi cấu hình/git. Trong GitHub Actions, báo cáo Markdown tự được ghi vào Job Summary.

Dùng như thư viện:

```python
from drift import run_drift_detection
report = run_drift_detection(diff_text, read_old, read_new, docs)   # docs = {đường_dẫn: nội_dung}
print(report.to_json())
```

## Rule

| Rule | Loại | Phát hiện |
|---|---|---|
| DRIFT001 | removed_entity | Tài liệu nhắc code đã bị xóa |
| DRIFT002 | renamed_entity | Tài liệu dùng tên cũ của code đã đổi tên |
| DRIFT003 | signature_changed | Chữ ký cũ nguyên văn, ví dụ gọi hàm theo tham số/số đối số cũ, tham số đã xóa vẫn được liệt kê, tham số mới chưa được mô tả |
| DRIFT004 | return_type_changed | Kiểu trả về trong tài liệu đã cũ |
| DRIFT005 | route_changed | Route HTTP đổi path/method hoặc bị xóa (FastAPI, Flask, Spring) |
| DRIFT006 | members_changed | Thuộc tính class đã xóa vẫn được liệt kê / thuộc tính mới chưa mô tả |
| DRIFT007 / 008 | file_removed / file_renamed | Tài liệu trỏ tới file đã xóa / đổi tên (đường dẫn hoặc link Markdown) |
| DRIFT009 | undocumented_endpoint | Endpoint mới vắng mặt trong tài liệu đang liệt kê các endpoint cùng file |
| DRIFT010 | entity_moved | Tài liệu trỏ tới file cũ của code đã chuyển file |

Độ tin cậy `confidence` (0..1) = độ chắc của rule × độ chắc rằng đoạn văn bản thực sự nói về entity đó (tên đặc trưng trong code span/heading cao hơn tên chung chung trong văn xuôi). Mức độ: `high ≥ 0.8`, `medium ≥ 0.5`, còn lại `low`. Chỉ thay đổi phần thân hàm, docstring hoặc comment **không** bị coi là drift. Nếu PR đã cập nhật tài liệu đúng thì không có finding (tài liệu được đọc ở phiên bản sau PR).

## Bằng chứng (JSON `schema_version 1.0`)

Mỗi finding gồm: `id` ổn định, `rule_id`, `severity`, `confidence`, `reasons`, `suggestion`, `doc` (file, dòng, section, đoạn trích có đánh dấu dòng lỗi) và `code` (`file_path`, `start_line`, `end_line`, `code_snippet`, `commit_hash` — cùng tên trường với `GroundingEvidence` của FR-EVI-04 — cùng chữ ký trước/sau và đoạn diff liên quan). Báo cáo còn có `summary`, danh sách `affected_documents` và `warnings`.

## Giới hạn đã biết

- Hỗ trợ Python và Java (trích xuất bằng `ast` và bộ quét Java dựa trên cặp ngoặc, không dùng tree-sitter). Ngôn ngữ khác chỉ được xét ở mức đường dẫn file.
- Chỉ đọc tài liệu `.md`, `.markdown`, `.mdx`, `.rst`. Tên entity quá phổ thông (ví dụ `run`) chỉ được tính khi nằm trong code span, heading hoặc lời gọi `name(...)`.
- Phát hiện dựa trên rule nên có thể có false positive/negative; hãy xem `confidence` và `reasons`. Bộ kiểm tra link `scripts/check_documentation_drift.py` là công cụ riêng, không bị thay thế.

## Chạy test

```bash
python -m pytest -q -o addopts="" tests/test_drift_*.py
```
