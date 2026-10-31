# LivingDocs — Functional Requirements & Project Overview

Tài liệu tổng quan các chức năng được tổng hợp từ 4 đặc tả Markdown của dự án LivingDocs. Mỗi chức năng có một file đặc tả riêng, mô tả mục tiêu, vị trí mã nguồn, API/hợp đồng dữ liệu, luồng xử lý, quy tắc nghiệp vụ, kiểm thử và tiêu chí chấp nhận.

## Functional Requirements

Các chức năng được chia theo các đặc tả Jira/snapshot tương ứng:

| File | Chức năng | Story / task Jira |
|---|---|---|
| [LD-63-Repository-Synchronization.md](LD-63-Repository-Synchronization.md) | Đồng bộ repository GitHub, tạo snapshot và cung cấp dữ liệu đầu vào cho bước phân tích | LD-63 |
| [LD-376-GitHub-Actions-CI-and-Documentation-Drift.md](LD-376-GitHub-Actions-CI-and-Documentation-Drift.md) | GitHub Actions CI và kiểm tra Documentation Drift đối với liên kết Markdown nội bộ | LD-376 |
| [LD-382-Docker-Deployment.md](LD-382-Docker-Deployment.md) | Container hóa các service và điều phối môi trường chạy bằng Docker Compose | LD-382 |
| [LD-397-Code-Analyzer-Docker-Compose.md](LD-397-Code-Analyzer-Docker-Compose.md) | Phân tích mã nguồn Java/Python bằng AST và tích hợp Code Analyzer vào Docker Compose | LD-397 |

Mỗi file đặc tả chứa các thông tin cần thiết để triển khai hoặc tái tạo chức năng tương ứng. Các giá trị mặc định, giới hạn, mã lỗi, trạng thái và tiêu chí kiểm thử được quy định trong file chi tiết.

## Thứ tự sử dụng và quan hệ giữa các chức năng

Luồng dữ liệu chính phục vụ việc phân tích mã nguồn:

1. **Repository Synchronization (LD-63)**  
   Người dùng chọn repository và yêu cầu đồng bộ. GitHub Integration Service xác minh quyền truy cập, lấy snapshot theo commit của nhánh được chọn, lọc file Java/Python và tạo dữ liệu `AnalysisInput`.

2. **Code Analyzer (LD-397)**  
   GitHub Integration Service chuyển danh sách file có nội dung đến `POST /api/v1/analyze-repo`. Code Analyzer phân tích AST, trích xuất class, function/method và endpoint; kết quả được trả riêng cho từng file.

3. **AI Service**  
   Kết quả phân tích cấu trúc code là dữ liệu đầu vào cho bước sinh tài liệu của AI Service. Logic sinh tài liệu thuộc AI Service, không thuộc Code Analyzer.

Các chức năng hỗ trợ vận hành và chất lượng:

- **Docker & Deployment (LD-382):** đóng gói và khởi chạy các service hiện có bằng Docker Compose, quản lý phụ thuộc, healthcheck và dữ liệu PostgreSQL bằng named volumes.
- **GitHub Actions CI & Documentation Drift Guard (LD-376):** tự động kiểm tra khi push/PR hoặc chạy thủ công; kiểm tra liên kết Markdown nội bộ và chạy các job build/test của các module.

### Luồng dữ liệu phân tích

```text
Người dùng
    |
    v
Frontend
    |
    v
GitHub Integration Service
    |
    v
Repository Synchronization (LD-63)
    |
    | Snapshot / AnalysisInput
    v
Code Analyzer (LD-397)
    |
    | Kết quả phân tích AST
    v
AI Service
    |
    v
Sinh tài liệu
```

### Luồng CI và triển khai

```text
Push / Pull Request / Manual Dispatch
    |
    v
GitHub Actions (LD-376)
    |
    +--> Documentation Drift Verification
    +--> Backend Build and Test
    +--> Frontend Build
    +--> GitHub Integration Service Test
    +--> AI Service Test
    +--> AI Service Integration
    +--> Docker Compose Validation

Docker Compose (LD-382, được mở rộng tại LD-397)
    |
    +--> PostgreSQL databases
    +--> Backend
    +--> Frontend
    +--> GitHub Integration Service
    +--> AI Service
    +--> Code Analyzer
```

## Quy ước chung

### Công nghệ chính

| Thành phần | Công nghệ / runtime |
|---|---|
| Backend | Java 21, Spring Boot 3.5 |
| Frontend | React, Vite, Node.js 24, Nginx |
| GitHub Integration Service | Java 21, Spring Boot |
| AI Service | Python 3.12, FastAPI, Uvicorn |
| Code Analyzer | Python 3.12, FastAPI, AST, `javalang` |
| Database | PostgreSQL 16; H2 dùng trong một số test |
| Container orchestration | Docker, Docker Compose |
| CI | GitHub Actions |
| Documentation Drift Guard | Python, `pathlib`, `re`, `urllib.parse` |

### API và dữ liệu giữa các service

- Repository Sync sử dụng các endpoint:
  - `POST /api/repositories/{id}/sync`
  - `GET /api/repositories/{id}/sync/latest`
  - `GET /api/repositories/{id}/sync/latest/analysis-input`
- Các endpoint đồng bộ repository yêu cầu header `X-User-Id` theo snapshot LD-63.
- API Code Analyzer:
  - `GET /health`
  - `POST /api/v1/analyze-repo`
- Dữ liệu đầu vào analyzer có cấu trúc `scope`, `target`, `files`; mỗi file gồm `path`, `language` và `content`.
- Ngôn ngữ được hỗ trợ để phân tích AST là `python` và `java`.
- Repository Sync trả metadata snapshot cho frontend; nội dung source file được cung cấp riêng qua `analysis-input`.
- Kết quả Code Analyzer có trạng thái theo từng file: `ok`, `invalid`, `empty`, `unsupported`.

### Docker và cổng dịch vụ

Các cổng được mô tả trong các snapshot:

| Service | Cổng |
|---|---:|
| Frontend (Nginx) | 3000 |
| Backend | 8080 |
| GitHub Integration Service | 8082 |
| AI Service | 8001 |
| Code Analyzer | 8000 |
| Backend PostgreSQL (host) | 5434 |
| GitHub Integration PostgreSQL (host) | 5433 |

- Các service giao tiếp nội bộ bằng hostname của service trong Docker Compose, không dùng `localhost` giữa các container.
- Database sử dụng named volumes để giữ dữ liệu khi container được recreate.
- Code Analyzer và AI Service được kết nối với GitHub Integration Service qua network nội bộ theo snapshot LD-397.
- Port debug của Code Analyzer và AI Service được bind vào `127.0.0.1` theo cấu hình LD-397.

### Cấu hình và bảo mật

- Không commit secret hoặc file `.env` chứa credential thật.
- GitHub Integration Service cần `TOKEN_ENCRYPTION_KEY`, GitHub client credentials, app slug và redirect URI theo cấu hình triển khai.
- Token GitHub không được trả về frontend hoặc truyền trực tiếp cho Code Analyzer.
- Code Analyzer nhận source content qua API và chạy bằng user không đặc quyền `analyzer` (UID `10001`).
- Code Analyzer không cần LLM API key cho chức năng AST parsing.
- AI Service có thể cần `ANTHROPIC_API_KEY` để sử dụng LLM thật; snapshot có chế độ offline khi thiếu key.

## Kiểm thử và tiêu chí chấp nhận tổng quan

- **LD-63:** kiểm tra snapshot theo branch/commit, lọc file, giới hạn số lượng/kích thước, cảnh báo, xử lý lỗi GitHub, quyền sở hữu repository và payload `analysis-input`.
- **LD-376:** kiểm tra local Markdown links, path traversal, external links, anchor-only links, ignored directories; xác minh trigger và các job CI.
- **LD-382:** kiểm tra Compose config/build, trạng thái healthy của database và service, kết nối database, frontend port và khả năng giữ dữ liệu qua recreate.
- **LD-397:** kiểm tra API health/analyze, Python/Java parsing, trạng thái từng file, trường hợp lỗi/rỗng/không hỗ trợ, non-root container và kết nối service qua network nội bộ.

Chi tiết test case và kết quả mong đợi được ghi trong mục kiểm thử/tiêu chí chấp nhận của từng file đặc tả.

## Không thuộc yêu cầu chức năng / giới hạn cần lưu ý

Các nội dung sau không được tự xem là chức năng đã có nếu không có đặc tả hoặc triển khai bổ sung:

- LD-63 không bao gồm GitHub OAuth/đăng nhập, webhook, đồng bộ nền, Kafka, lưu lịch sử snapshot lâu dài hoặc phân tích AST.
- Snapshot LD-63 lưu snapshot mới nhất trong memory; restart service làm mất kết quả đồng bộ đã cache.
- LD-376 không tự deploy production, không tự sửa Markdown link và không commit thay đổi ngược về repository.
- LD-382 mô tả Docker Compose cho local/development/demo; không có Kubernetes, autoscaling, rolling deployment, ingress controller hoặc secret manager.
- LD-397 chỉ phân tích cấu trúc code; không thực hiện chức năng sinh tài liệu AI và không đọc trực tiếp filesystem host.
- Một file lỗi khi phân tích không làm dừng xử lý các file còn lại trong cùng request Code Analyzer.

## Lưu ý về các snapshot và phiên bản

Bốn file nguồn được trích xuất từ các snapshot/branch khác nhau. Chúng mô tả phạm vi của từng snapshot, không mặc nhiên là một bản triển khai duy nhất đã được hợp nhất hoàn chỉnh.

- LD-382 mô tả cấu hình Docker Compose nền với các service và network theo snapshot LD-382.
- LD-397 bổ sung Code Analyzer và cách kết nối các service qua các network nội bộ; không nên áp ngược cấu hình network của LD-397 khi mục tiêu là tái tạo chính xác snapshot LD-382.
- LD-376 ghi rõ metadata Git của snapshot ZIP đang ở `main`, không khẳng định đó là toàn bộ lịch sử thay đổi của branch LD-376.
- Khi triển khai tích hợp, cần đối chiếu `compose.yaml`, workflow và source code của branch/commit thực tế đang sử dụng để xử lý khác biệt giữa các snapshot.

## Tài liệu chi tiết

- [LD-63 — Repository Synchronization](LD-63-Repository-Synchronization.md)
- [LD-376 — GitHub Actions CI and Documentation Drift](LD-376-GitHub-Actions-CI-and-Documentation-Drift.md)
- [LD-382 — Docker & Deployment](LD-382-Docker-Deployment.md)
- [LD-397 — Code Analyzer in Docker Compose](LD-397-Code-Analyzer-Docker-Compose.md)
