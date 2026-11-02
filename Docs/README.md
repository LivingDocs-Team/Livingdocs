# Functional Requirements — Tasks của Nhân

Mỗi task được tách thành một file riêng:

| File | Task | Loại |
|---|---|---|
| `FR-GH-03-Repository-Synchronization.md` | LD-24 / LD-63 — Repository Synchronization | Functional Requirement |
| `FR-GH-04-Repository-Analysis-Input.md` | LD-63 / contract liên quan LD-395 — Analysis Input | Functional Requirement |
| `FR-INT-01-Repository-Documentation-Orchestration.md` | LD-396 — Repository Documentation Orchestration | Functional Requirement |
| `ENG-OPS-01-Docker-Compose-CI-Validation.md` | LD-382 — Docker Compose / CI validation | Engineering requirement, không phải chức năng người dùng cuối |

## Cách sử dụng

Đọc FR phù hợp với task đang triển khai và đối chiếu code/contract hiện tại trước khi sửa. Không giả định tài liệu thay thế được việc kiểm tra implementation thực tế.

## Ghi chú phạm vi

Các file phản ánh những task đã xác định được từ context hiện tại; không khẳng định đây là toàn bộ task từng được giao cho Nhân. Nếu cần dùng trực tiếp trong `Docs/` của GitHub, hãy rà lại mã Jira, người assignee, API và default values với source code trước khi commit.
