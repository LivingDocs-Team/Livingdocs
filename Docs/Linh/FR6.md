# FR-AI-06 Quản lý phiên bản tài liệu

| Mục | Nội dung |
|---|---|
| Task Jira | LD-195 [Documentation Version Management] Implement Documentation Version Management |
| Epic | Documentation Versioning |
| Người thực hiện | Nguyễn Thị Phương Linh |
| Thành phần | AI Service: `app/versions.py` (`DocumentStore`: tạo, liệt kê, lưu file), `app/version_models.py`, `app/jobs.py` (`JobOutput`), `main.py` |
| Tác nhân | Người dùng LivingDocs, GitHub Integration Service |

## 1. Mô tả

Kết quả của một job sinh tài liệu (FR-AI-01) được lưu thành **tài liệu** với phiên bản 1. Mỗi thay đổi sau đó (cập nhật từ source change — FR-AI-07, duyệt — FR-AI-08, khôi phục — FR-AI-09) tạo thêm một phiên bản mới; không phiên bản nào bị sửa hay xoá. Người dùng xem được danh sách phiên bản, nội dung từng phiên bản và nhật ký ai đã làm gì, khi nào.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-AI-06.1 | Tạo tài liệu từ job `completed` (`job_id`, tuỳ chọn `title`, `actor`, `note`): giữ phạm vi, đích, mẫu, ngôn ngữ của job; phiên bản 1 `accepted`, `origin = generated`, nội dung giống hệt `/jobs/{id}/result`, kèm tài liệu từng file (`sections`) và file bị bỏ qua (`skipped`). |
| FR-AI-06.2 | Tài liệu (`Document`): `id`, `title`, `target`, `scope`, `template_id`, `output_language`, `source_job_id`, `current_version` (phiên bản được chấp nhận mới nhất), `pending_version` (đề xuất chờ duyệt hoặc `null`), `versions_total`, `created_at`, `updated_at`. |
| FR-AI-06.3 | Phiên bản (`DocumentVersion`): `number` (1, 2, 3…), `status` (`proposed`, `accepted`, `dismissed`, `superseded`), `origin` (`generated`, `source_change`, `edit`, `regenerate`, `rollback`), `base_version`, `restored_from`, `superseded_by`, `source_changes`, `changes`, `warnings`, `confidence`, `manual`, `note`, `created_by`, `created_at`, `decided_by`, `decided_at`, `content`, `sections`, `skipped`, `sections_match_content`. |
| FR-AI-06.4 | Liệt kê tài liệu (mới cập nhật trước); xem một tài liệu; lấy Markdown của phiên bản hiện hành hoặc `?version=N`. |
| FR-AI-06.5 | Liệt kê phiên bản (mới nhất trước) ở dạng tóm tắt, không kèm nội dung; xem đầy đủ một phiên bản. |
| FR-AI-06.6 | Nhật ký (`HistoryEvent`, cũ trước): `at`, `action` (`created`, `proposed`, `accepted`, `edited`, `dismissed`, `regenerated`, `superseded`, `rolled_back`), `version`, `related_version`, `actor`, `note`. |
| FR-AI-06.7 | Lưu toàn bộ tài liệu, phiên bản, nhật ký và đầu vào của đề xuất vào `DOCUMENTS_FILE` (mặc định `data/documents.json`, ghi nguyên tử) để còn sau khi khởi động lại. `DOCUMENTS_FILE=` (rỗng) → chỉ giữ trong bộ nhớ. File hỏng → đổi tên `documents.corrupt-<thời gian>.json`, khởi động với danh sách rỗng. |

## 3. API

| Method | Endpoint | Kết quả |
|---|---|---|
| POST | `/documents` | `201` + `Document` |
| GET | `/documents` | Danh sách `Document` |
| GET | `/documents/{id}` | `Document` |
| GET | `/documents/{id}/content?version=N` | Markdown, `text/markdown` |
| GET | `/documents/{id}/versions` | Danh sách `VersionSummary`, mới nhất trước |
| GET | `/documents/{id}/versions/{n}` | `DocumentVersion` |
| GET | `/documents/{id}/history` | Danh sách `HistoryEvent` |

## 4. Luồng chính

1. Job sinh tài liệu hoàn tất → `POST /documents {"job_id": …}`.
2. AI Service tạo tài liệu, phiên bản 1, sự kiện `created`, lưu file.
3. Các thay đổi sau (FR-AI-07, FR-AI-08, FR-AI-09) thêm phiên bản và sự kiện; người dùng xem danh sách phiên bản, nhật ký, nội dung từng phiên bản.

## 5. Luồng lỗi

| Trường hợp | Kết quả |
|---|---|
| Job không tồn tại | `404 Job not found` |
| Job chưa xong hoặc `failed` | `409 Job is <status>` |
| Job đã xong nhưng không có kết quả theo file (trường hợp hiếm, ví dụ job dựng thủ công) | `409 Job result is no longer available` |
| Tài liệu / phiên bản không tồn tại | `404` |

## 6. Quy tắc nghiệp vụ

- Phiên bản bất biến; số phiên bản tăng dần, không dùng lại.
- Phiên bản hiện hành chỉ đổi khi một phiên bản được chấp nhận (FR-AI-08) hoặc khôi phục (FR-AI-09).

## 7. Tiêu chí chấp nhận

- Lưu job thành tài liệu: phiên bản 1 trùng với kết quả job, nhật ký có `created`.
- Khởi động lại service: tài liệu, phiên bản, nhật ký vẫn còn.

## 8. Kiểm thử

`ai-service/tests/test_versions.py`: `test_save_job_as_version_1`, `test_create_document_errors`, `test_documents_survive_restart`.



