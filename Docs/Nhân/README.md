# Tài liệu task — Nhân

Tài liệu này tổng hợp các task và phần việc Nhân đã tham gia trong LivingDocs. Mỗi tài liệu mô tả yêu cầu, luồng xử lý và tiêu chí chấp nhận theo implementation/contract đã xác định.

## Danh mục

| Tài liệu | Task / phạm vi | Loại |
|---|---|---|
| [FR-GH-03 — Repository Synchronization](FR-GH-03-Repository-Synchronization.md) | LD-24 / LD-63 — phối hợp luồng đồng bộ repository từ GitHub | Functional Requirement |
| [FR-GH-04 — Repository Analysis Input](FR-GH-04-Repository-Analysis-Input.md) | LD-63 và contract liên quan LD-395 — chuẩn hóa dữ liệu gửi Code Analyzer | Functional Requirement |
| [FR-INT-01 — Documentation Orchestration](FR-INT-01-Repository-Documentation-Orchestration.md) | LD-396 — điều phối phân tích và sinh tài liệu; OAuth/session recovery; cache-miss re-sync | Functional Requirement |
| [ENG-OPS-01 — Docker Compose và CI](ENG-OPS-01-Docker-Compose-CI-Validation.md) | LD-382 — Docker Compose, health checks, CI validation và cấu hình runtime | Engineering / Operational Requirement |
| [ENG-OPS-02 — Code Analyzer trong Docker Compose](ENG-OPS-02-Code-Analyzer-Docker-Compose.md) | LD-397 — tích hợp Code Analyzer vào Docker Compose và internal network | Engineering / Operational Requirement |

## Phạm vi và cách đọc

- Các tài liệu mô tả phần việc đã xác định được từ task, source code, contract và kiểm tra thực tế; không có nghĩa Nhân là người duy nhất thực hiện toàn bộ task phối hợp.
- LD-63 là phần việc phối hợp giữa các thành viên. Xem rõ vai trò ở từng task/Jira issue trước khi quy kết ownership.
- Các yêu cầu kỹ thuật được đặt tên `ENG-OPS`, không gọi nhầm là Functional Requirement của người dùng cuối.
- Snapshot repository và một số job/state hiện dùng in-memory store. Tự đồng bộ lại khi cache miss là cơ chế phục hồi bằng cách gọi GitHub, không phải persistent storage.
- Khi implementation hoặc API contract thay đổi, cần cập nhật tài liệu và test tương ứng. Tài liệu không thay thế việc kiểm tra source code thực tế.
