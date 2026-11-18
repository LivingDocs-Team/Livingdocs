# Tài liệu task — Nhân

## Mục lục

| Tài liệu | Task / phạm vi | Loại |
|---|---|---|
| [FR1 — Documentation Orchestration](FR1.md) | LD-396 — điều phối phân tích và sinh tài liệu; OAuth/session recovery; cache-miss re-sync | Functional Requirement |
| [FR2 — Repository Synchronization](FR2.md) | LD-24 / LD-63 — phối hợp luồng đồng bộ repository từ GitHub | Functional Requirement |
| [FR3 — Repository Analysis Input](FR3.md) | LD-63 và contract liên quan LD-395 — chuẩn hóa dữ liệu gửi Code Analyzer | Functional Requirement |
| [FR4 — Tích hợp đăng ký và đăng nhập trên frontend](FR4.md) | LD-389 | Functional Requirement |
| [FR5 — Quản lý người dùng, vai trò và quyền](FR5.md) | LD-261–LD-266 | Functional Requirement |
| [FR6 — Lịch sử phê duyệt tài liệu](FR6.md) | LD-251–LD-256 | Functional Requirement |
| [FR7 — Quản trị workspace và repository](FR7.md) | LD-267–LD-272 | Functional Requirement |
| [FR8 — Hồi quy phân quyền và GitHub OAuth](FR8.md) | LD-399, LD-400 | Functional Requirement |
| [FR9 — Audit, giám sát và chính sách thông báo](FR9.md) | LD-280–LD-285 | Functional Requirement |
| [FR10 — Bình luận review, yêu cầu sửa và nộp lại](FR10.md) | LD-245–LD-250 | Functional Requirement |
| [FR11 — Documentation Collections và phân công tài liệu](FR11.md) | LD-219–LD-221 | Functional Requirement |
| [ENG-OPS-01 — Docker Compose và CI](ENG-OPS-01-Docker-Compose-CI-Validation.md) | LD-382 — Docker Compose, health checks, CI validation và cấu hình runtime | Engineering / Operational Requirement |
| [ENG-OPS-02 — Code Analyzer trong Docker Compose](ENG-OPS-02-Code-Analyzer-Docker-Compose.md) | LD-397 — tích hợp Code Analyzer vào Docker Compose và internal network | Engineering / Operational Requirement |
| [ENG-OPS-03 — Tổ chức mã xác thực và kiểm thử Backend](ENG-OPS-03-Backend-Auth-Test-Layout.md) | Refactor Backend, PR #120–121 | Engineering / Operational Requirement |

Trạng thái Jira trong các tài liệu mới được ghi theo lần đối chiếu ngày 18/11/2026. Các PR và commit dẫn tới phần triển khai đã xác minh của Nhân, kể cả những hạng mục thực hiện cùng các thành viên khác.

Xem [yêu cầu xác thực chung](../Huy/FR01.md) cho đăng ký, đăng nhập, đăng xuất và GitHub OAuth, và [hướng dẫn CI dự án](../Huy/README.md) cho build/test.
