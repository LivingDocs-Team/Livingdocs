# FR-AI-08 Duyệt bản cập nhật tài liệu (so sánh, accept / edit / dismiss / regenerate)

| Mục | Nội dung |
|---|---|
| Task Jira | LD-134 [Documentation Update Review & Rollback] Implement Update Review & Rollback |
| Story | LD-115 Documentation Update Review & Rollback |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service: `app/versions.py` (`compare`, `split_content`, `accept`, `dismiss`, `regenerate`, `edit`, `_rebase_pending`), `app/version_models.py` (`CompareResult`, `FileDiff`, `ReviewRequest`, `EditRequest`), `main.py` |
| Tác nhân | Người duyệt tài liệu |
| Liên quan | FR-AI-06 (phiên bản, LD-195), FR-AI-07 (đề xuất từ source change, LD-128), FR-AI-09 (khôi phục, LD-189) |

## 1. Mô tả

Đề xuất sinh ra từ thay đổi mã nguồn (FR-AI-07) không tự áp dụng. Người duyệt **xem khác biệt** giữa phiên bản hiện hành và đề xuất, rồi **chấp nhận**, **sửa** rồi chấp nhận, **bỏ qua** (huỷ bản cập nhật, tài liệu giữ như cũ) hoặc **sinh lại** đề xuất. Phiên bản hiện hành cũng có thể sửa tay. Mọi thao tác tạo phiên bản mới hoặc chỉ đổi trạng thái đề xuất, và được ghi vào nhật ký (FR-AI-06); không có gì bị xoá.

## 2. Yêu cầu chức năng

**So sánh phiên bản**

| ID | Yêu cầu |
|---|---|
| FR-AI-08.1 | Tham số `from`, `to` là số phiên bản (≥ 1). Thiếu `from` → phiên bản hiện hành; thiếu `to` → đề xuất đang chờ, không có thì phiên bản mới nhất. So sánh được mọi phiên bản, theo cả hai chiều. |
| FR-AI-08.2 | Với mỗi file có ở một trong hai phiên bản: `added`, `removed`, `modified` hoặc `unchanged`, kèm `added_lines`, `removed_lines`. Phiên bản sửa tay không tách được theo file thì cả tài liệu là một mục `(document)`. |
| FR-AI-08.3 | `unified_diff` của toàn văn (tiêu đề `--- version <from>` / `+++ version <to>`, rỗng khi giống hệt); tổng `added_lines`, `removed_lines`; `identical`. |

**Duyệt đề xuất**

| ID | Yêu cầu |
|---|---|
| FR-AI-08.4 | **Chấp nhận** đề xuất N: `status = accepted`, `decided_by`, `decided_at`; N thành `current_version`, `pending_version = null`; sự kiện `accepted`. Từ đây gửi lại source change của N → `409` (FR-AI-07.12). |
| FR-AI-08.5 | **Bỏ qua** đề xuất N: `status = dismissed`; phiên bản hiện hành giữ nguyên (bản cập nhật bị huỷ); sự kiện `dismissed`. Source change của N có thể gửi lại sau. |
| FR-AI-08.6 | **Sinh lại** đề xuất N: chạy lại toàn bộ source change của N (đầu vào đã lưu, FR-AI-07.13) trên phiên bản hiện hành với mẫu hiện tại, tạo đề xuất mới `origin = regenerate`; N chuyển `superseded`; sự kiện `superseded`, `regenerated`. |
| FR-AI-08.7 | **Sửa** phiên bản N (đề xuất, hoặc phiên bản hiện hành) với `content` mới: tạo phiên bản `origin = edit`, `manual = true`, `base_version = N`. Mặc định `accept = true` → thành hiện hành; `accept = false` → thành đề xuất mới (vẫn sinh lại được). Sửa một đề xuất thì đề xuất đó chuyển `superseded`. |
| FR-AI-08.8 | Nội dung sửa được tách lại theo file (mỗi phần giữa dòng `---` bắt đầu bằng `# <đường dẫn file>`, phần đầu có thể là tổng quan `# <target>`): file thay đổi `status = manual`, `changes` ghi `edited`; file bị bỏ khỏi nội dung ghi `removed`. Phần sửa được giữ ở các lần cập nhật sau nếu mã nguồn file đó không đổi. |
| FR-AI-08.9 | Không tách được theo file → vẫn lưu nguyên văn, `sections_match_content = false`, kèm cảnh báo rằng lần cập nhật sau sẽ dựng lại nội dung và mất phần sửa tay. |
| FR-AI-08.10 | Sửa phiên bản hiện hành khi đang có đề xuất chờ → đề xuất được dựng lại trên phiên bản vừa sửa (`origin = regenerate`, ghi chú `Rebased on version X`), đề xuất cũ `superseded`, để chấp nhận đề xuất không làm mất phần vừa sửa. |
| FR-AI-08.11 | Mọi thao tác nhận tuỳ chọn `actor`, `note`, lưu vào phiên bản và nhật ký. |

## 3. API

| Method | Endpoint | Body | Kết quả |
|---|---|---|---|
| GET | `/documents/{id}/compare?from=&to=` | – | `CompareResult` |
| POST | `/documents/{id}/versions/{n}/accept` | `{actor, note}` (tuỳ chọn) | `200` + `DocumentVersion` |
| POST | `/documents/{id}/versions/{n}/dismiss` | `{actor, note}` (tuỳ chọn) | `200` + `DocumentVersion` |
| POST | `/documents/{id}/versions/{n}/regenerate` | `{actor, note}` (tuỳ chọn) | `201` + đề xuất mới |
| POST | `/documents/{id}/versions/{n}/edit` | `{content, accept, actor, note}` | `201` + phiên bản mới |

`CompareResult`: `document_id`, `from_version`, `to_version`, `files` (`path`, `change`, `added_lines`, `removed_lines`), `added_lines`, `removed_lines`, `identical`, `unified_diff`.

## 4. Luồng chính

1. Có đề xuất mới (FR-AI-07) → frontend gọi `/compare` không tham số để hiện danh sách file thay đổi và diff.
2. Đúng → chấp nhận. Gần đúng → sửa rồi lưu. AI viết chưa tốt hoặc vừa đổi mẫu → sinh lại. Không cần cập nhật → bỏ qua.
3. Phiên bản mới (nếu có) và sự kiện được ghi vào lịch sử (FR-AI-06).

## 5. Luồng lỗi

| Trường hợp | Kết quả |
|---|---|
| Tài liệu / phiên bản không tồn tại | `404` |
| `from`/`to` < 1 | `422` |
| Chấp nhận, bỏ qua, sinh lại phiên bản không phải đề xuất | `409 Version N is <status>, not a proposal` |
| Sinh lại đề xuất không có source change (đề xuất do sửa tay phiên bản hiện hành) hoặc sinh lại không còn thay đổi | `409` |
| Sửa phiên bản không phải đề xuất và không phải hiện hành | `409` |
| Nội dung sửa giống hệt nội dung cũ | `409 The content is unchanged` |
| `content` rỗng | `422` |

## 6. Quy tắc nghiệp vụ

- Không thao tác nào sửa hoặc xoá phiên bản đã có; chỉ thêm phiên bản và đổi `status` của đề xuất.
- Mỗi tài liệu có tối đa một đề xuất chờ duyệt.
- So sánh chỉ đọc, không thay đổi dữ liệu.

## 7. Tiêu chí chấp nhận

- Đề xuất sửa 1 file: so sánh cho thấy file đó `modified`, file khác `unchanged`, diff có dòng `+` chứa entity mới.
- Chấp nhận → nội dung hiện hành có thay đổi mới; bỏ qua → không đổi.
- Sửa một mục file trong đề xuất rồi lưu → phiên bản mới hiện hành có đoạn sửa; cập nhật file khác sau đó vẫn giữ đoạn sửa.

## 8. Kiểm thử

`ai-service/tests/test_versions.py`: `test_compare_current_with_proposal`, `test_compare_added_and_removed_files`, `test_accept_proposal`, `test_dismiss_proposal_keeps_current`, `test_regenerate_proposal`, `test_edit_proposal_section_and_accept`, `test_edit_without_accept_creates_new_proposal`, `test_edit_free_text_and_errors`, `test_editing_current_version_rebases_pending_proposal`, `test_change_already_accepted_is_rejected`, `test_split_content`.
