# FR-AI-07 Cập nhật tài liệu tự động từ thay đổi mã nguồn

| Mục | Nội dung |
|---|---|
| Task Jira | LD-128 [Automatic Documentation Update] Implement Automatic Documentation Update |
| Story | LD-114 Automatic Documentation Update |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service (cổng 8001): `app/versions.py` (`DocumentStore.update`, `_apply`), `app/version_models.py`, `app/jobs.py` (`JobOutput`), `main.py` |
| Tác nhân | GitHub Integration Service (sau khi LD-116 phát hiện thay đổi), người duyệt tài liệu |
| Liên quan | LD-116 (phát hiện source change, `SourceChangeResponse`), FR-AI-06 (lưu tài liệu và phiên bản, LD-195), FR-AI-08 (duyệt đề xuất, LD-134) |

## 1. Mô tả

Khi mã nguồn thay đổi (commit trên nhánh mặc định hoặc Pull Request), LD-116 phát hiện các file và code entity bị thêm, sửa, xoá, đổi tên. Chức năng này nhận source change đó cùng kết quả phân tích mới của các file thay đổi, **chỉ sinh lại tài liệu của những file bị ảnh hưởng**, giữ nguyên tài liệu các file khác, và tạo một **phiên bản đề xuất** (`proposed`) để người dùng duyệt. Phiên bản hiện hành không đổi cho đến khi đề xuất được chấp nhận (FR-AI-08).

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AI-07.1 | Nhận `source_change` theo định dạng LD-116: `id`, `trigger` (`COMMIT`/`PULL_REQUEST`), `commit_sha`, `pull_request_number`, `files` (ít nhất 1). Mỗi file: `path`, `previous_path`, `change` (`ADDED`/`MODIFIED`/`REMOVED`/`RENAMED`, không phân biệt hoa thường), `language`, `skipped_reason`, `entities` (`kind`, `name`, `change`, `start_line`, `end_line`). Chấp nhận cả tên camelCase của Java (`commitSha`, `previousPath`, `skippedReason`, `startLine`…). |
| FR-AI-07.2 | Kèm `files`: kết quả Code Analyzer (định dạng `CONTRACT.md`) của các file sau thay đổi, không trùng `path`. File `REMOVED` không cần phân tích. Tuỳ chọn `context` (tài liệu có sẵn), `actor`, `note`. |
| FR-AI-07.3 | `MODIFIED`/`ADDED`: sinh lại tài liệu file đó bằng mẫu của tài liệu (FR-AI-05) và ngôn ngữ của tài liệu. Ghi nhận thay đổi `updated` (file đã có tài liệu) hoặc `added` (file mới). |
| FR-AI-07.4 | `REMOVED`: bỏ tài liệu của file khỏi phiên bản mới, ghi nhận `removed`. File chưa từng có tài liệu thì bỏ qua. |
| FR-AI-07.5 | `RENAMED`: tài liệu chuyển sang đường dẫn mới, giữ vị trí cũ trong tài liệu, ghi nhận `renamed` kèm `previous_path`. Có phân tích thì sinh lại; không có thì chuyển nguyên văn (đổi tiêu đề `# <path>`), `status = moved`, kèm cảnh báo. |
| FR-AI-07.6 | Không cập nhật nhưng ghi cảnh báo khi: file có `skipped_reason` (`<path>: not documented (<lý do>).`), thiếu phân tích (`<path>: no analysis provided; …`), phân tích lỗi (`<path>: skipped (<lỗi>); the previous documentation is kept.`), phân tích gửi kèm nhưng không thuộc source change (`<path>: analysis ignored, …`), lỗi bất ngờ khi sinh (`<path>: generation failed: …; the previous documentation is kept.`). |
| FR-AI-07.7 | Ngữ cảnh truy xuất (FR-AI-03) gồm các file thay đổi, `context` gửi kèm và tài liệu hiện có của các file không đổi, để tài liệu mới nhất quán với phần còn lại. |
| FR-AI-07.8 | Dựng lại toàn văn đúng bố cục FR-AI-01.11: tài liệu phạm vi `file` chỉ có 1 file thì giữ nguyên 1 file; còn lại là trang tổng quan (danh sách file, độ tin cậy chung) rồi tài liệu từng file. Thứ tự file giữ như phiên bản trước, file mới thêm vào cuối. |
| FR-AI-07.9 | Có ít nhất một thay đổi → tạo phiên bản `proposed`, `origin = source_change`, `base_version` = phiên bản hiện hành, `source_changes`, `changes` (đường dẫn, hành động, entity thay đổi lấy từ LD-116), `warnings`, `confidence`. Trả `201`. |
| FR-AI-07.10 | Không file nào có tài liệu bị ảnh hưởng → không tạo phiên bản, trả `200` với `proposal = null`, thông báo và cảnh báo. |
| FR-AI-07.11 | Đang có đề xuất chờ duyệt → đề xuất mới gồm thay đổi cũ **cộng** source change mới (dựng lại từ phiên bản hiện hành), đề xuất cũ chuyển `superseded` (`superseded_by` = số phiên bản mới). |
| FR-AI-07.12 | Gửi lại source change đang nằm trong đề xuất chờ duyệt → `200`, trả đề xuất đó, không tạo phiên bản mới (an toàn khi webhook gửi lặp). Source change đã nằm trong một phiên bản được chấp nhận → `409`. Source change thuộc đề xuất đã bị bỏ qua có thể gửi lại. |
| FR-AI-07.13 | Lưu đầu vào (source change, phân tích, ngữ cảnh) của mỗi đề xuất để có thể sinh lại (FR-AI-08) hoặc dựng lại khi phiên bản hiện hành đổi. |

## 3. API

| Method | Endpoint | Kết quả | Yêu cầu |
|---|---|---|---|
| POST | `/documents/{id}/updates` | `201` + `UpdateResult` có `proposal`; `200` khi không có thay đổi hoặc gửi lặp | FR-AI-07.1 – 07.13 |

Ví dụ body (rút gọn):

```json
{"actor": "github-integration",
 "source_change": {"id": "7b1c…", "trigger": "COMMIT", "commitSha": "abc123",
   "files": [{"path": "shop/cart.py", "change": "MODIFIED", "language": "python",
              "entities": [{"kind": "function", "name": "apply_discount", "change": "ADDED",
                            "startLine": 20, "endLine": 25}]},
             {"path": "shop/users.py", "change": "REMOVED"}]},
 "files": [{"path": "shop/cart.py", "language": "python", "status": "ok", "functions": [ … ]}]}
```

`UpdateResult`: `document_id`, `proposal` (`DocumentVersion` hoặc `null`), `message`, `warnings`.

## 4. Luồng chính

1. LD-116 lưu source change trạng thái `PENDING`; GitHub Integration gọi Code Analyzer cho các file thay đổi.
2. GitHub Integration gọi `POST /documents/{id}/updates` với source change và kết quả phân tích.
3. AI Service lấy phiên bản hiện hành (cùng các bước của đề xuất đang chờ, nếu có), áp lần lượt từng thay đổi file, sinh lại tài liệu các file `ADDED`/`MODIFIED`/`RENAMED`.
4. Dựng toàn văn, lưu phiên bản `proposed`, ghi sự kiện `proposed` vào lịch sử (FR-AI-06).
5. Người dùng xem khác biệt rồi chấp nhận, sửa, bỏ qua hoặc sinh lại (FR-AI-08).

## 5. Luồng lỗi

| Trường hợp | Kết quả |
|---|---|
| Tài liệu không tồn tại | `404 Document not found` |
| Thiếu `source_change`, `files` của source change rỗng, `change` không hợp lệ, trùng `path` trong `files` | `422` |
| Source change đã được chấp nhận ở phiên bản N | `409 Source change <id> was already applied in version N` |
| Từng file không cập nhật được | Không lỗi cả yêu cầu; file giữ tài liệu cũ, ghi vào `warnings` (FR-AI-07.6) |

## 6. Quy tắc nghiệp vụ

- Phiên bản là bất biến: cập nhật luôn tạo phiên bản mới, không sửa phiên bản cũ.
- Chỉ có tối đa một đề xuất chờ duyệt cho mỗi tài liệu (`pending_version`).
- Tài liệu file không đổi được giữ **nguyên văn**, kể cả phần người dùng đã sửa tay (FR-AI-08).
- Mẫu tài liệu đã bị xoá → dùng mẫu `default`, kèm cảnh báo.
- Cập nhật chạy đồng bộ trong yêu cầu (một tài liệu chỉ cập nhật một lần tại một thời điểm).

## 7. Tiêu chí chấp nhận

- Sửa 1 trong 2 file → đề xuất chỉ đổi tài liệu file đó, file còn lại giống hệt phiên bản trước; phiên bản hiện hành chưa đổi.
- Thêm, xoá, đổi tên file → tài liệu có, mất, chuyển tên tương ứng; `changes` ghi đúng hành động.
- Gửi 2 source change liên tiếp khi chưa duyệt → đề xuất cuối có cả hai; gửi lặp → không tạo phiên bản.
- Source change đã được chấp nhận (sau khi có FR-AI-08) gửi lại → `409`.

## 8. Kiểm thử

`ai-service/tests/test_versions.py`: `test_modified_file_creates_proposal`, `test_added_removed_and_renamed_files`, `test_renamed_file_with_analysis_is_regenerated`, `test_files_that_cannot_be_updated_keep_old_docs`, `test_validation_errors`, `test_same_change_twice_and_second_change_extends_proposal`, `test_file_scope_document_stays_single_file`, `test_generation_error_keeps_previous_docs`.
