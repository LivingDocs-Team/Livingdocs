# FR-AI-09 Khôi phục phiên bản tài liệu (rollback)

| Mục | Nội dung |
|---|---|
| Task Jira | LD-189 [Documentation Rollback] Implement Documentation Rollback |
| Story | LD-176 Documentation Rollback |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service: `app/versions.py` (`DocumentStore.rollback`, `_rebase_pending`), `app/version_models.py` (`RollbackRequest`), `main.py` |
| Tác nhân | Người dùng / người duyệt tài liệu |
| Liên quan | FR-AI-06 (phiên bản và lịch sử, LD-195), FR-AI-08 (duyệt đề xuất, LD-134) |

## 1. Mô tả

Khi phiên bản hiện hành của tài liệu sai (chấp nhận nhầm một bản cập nhật, sửa tay hỏng…), người dùng khôi phục một phiên bản cũ. Khôi phục **không xoá** gì: nội dung phiên bản cũ được chép thành một phiên bản mới và phiên bản mới đó thành hiện hành; toàn bộ lịch sử, kể cả chính thao tác khôi phục, vẫn được lưu và xem lại được (FR-AI-06).

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AI-09.1 | Khôi phục phiên bản M (`version` ≥ 1): M phải từng được chấp nhận (`status = accepted`) và khác phiên bản hiện hành. |
| FR-AI-09.2 | Tạo phiên bản mới `origin = rollback`, `status = accepted`, `restored_from = M`, `base_version` = phiên bản hiện hành trước đó; `content`, `sections`, `skipped`, `confidence` giống hệt M. Phiên bản mới thành `current_version`. |
| FR-AI-09.3 | Ghi sự kiện `rolled_back` (`version` = phiên bản mới, `related_version` = M, `actor`, `note`; ghi chú mặc định `Restored version M`). |
| FR-AI-09.4 | Các phiên bản giữa M và hiện hành giữ nguyên trạng thái và vẫn khôi phục lại được sau đó. |
| FR-AI-09.5 | Đang có đề xuất chờ duyệt → đề xuất được dựng lại trên phiên bản vừa khôi phục (`origin = regenerate`, ghi chú `Rebased on version X (rollback to version M)`), đề xuất cũ `superseded`. Nếu đề xuất không còn thay đổi gì so với phiên bản khôi phục thì chỉ đánh dấu `superseded`. Nhờ vậy chấp nhận đề xuất sau đó không đưa lại nội dung đã bị khôi phục bỏ đi. |

## 3. API

| Method | Endpoint | Body | Kết quả |
|---|---|---|---|
| POST | `/documents/{id}/rollback` | `{version, actor, note}` | `201` + `DocumentVersion` (phiên bản mới) |

## 4. Luồng chính

1. Người dùng xem danh sách phiên bản và nhật ký (FR-AI-06), so sánh phiên bản cần quay về với hiện hành (FR-AI-08).
2. Gọi `POST /documents/{id}/rollback {"version": M}`.
3. AI Service tạo phiên bản mới từ M, đặt làm hiện hành, ghi `rolled_back`, dựng lại đề xuất đang chờ (nếu có), lưu file.

## 5. Luồng lỗi

| Trường hợp | Kết quả |
|---|---|
| Tài liệu / phiên bản không tồn tại | `404` |
| `version` < 1 | `422` |
| M chưa từng được chấp nhận (`proposed`, `dismissed`, `superseded`) | `409 Version M was never accepted (...)` |
| M đang là phiên bản hiện hành | `409 Version M is already the current version` |

## 6. Quy tắc nghiệp vụ

- Rollback là "tiến lên bằng nội dung cũ": số phiên bản luôn tăng, không phiên bản nào bị xoá hay sửa.
- Chỉ khôi phục về phiên bản đã từng được chấp nhận, để không đưa vào nội dung chưa qua duyệt.

## 7. Tiêu chí chấp nhận

- Khôi phục phiên bản 1 khi hiện hành là 2 → phiên bản 3 có nội dung giống phiên bản 1; phiên bản 2 vẫn còn và khôi phục lại được (phiên bản 4).
- Nhật ký có `rolled_back` cho từng lần khôi phục.

## 8. Kiểm thử

`ai-service/tests/test_versions.py`: `test_rollback_restores_and_keeps_history`, `test_rollback_errors`, `test_pending_proposal_is_rebased_after_rollback`.
