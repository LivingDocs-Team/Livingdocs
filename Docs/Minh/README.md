# Functional Requirements — Tasks của Minh & Nhóm Backend (BE1 – BE9)

Các chức năng do Nguyễn Lê Minh (và các task Backend/System tích hợp liên quan) thực hiện, mỗi chức năng một file:

| File | Chức năng | Story / task Jira |
|---|---|---|
| [FR-BE-01](BE1.md) | Repository Synchronization (Đồng bộ snapshot repository từ GitHub) | LD-63 (LD-64 – LD-67) |
| [FR-BE-02](BE2.md) | GitHub Actions Integration & Documentation Drift Guard | LD-376 (LD-377 – LD-381) |
| [FR-BE-03](BE3.md) | Docker & Deployment (Đóng gói & triển khai Docker Compose MVP) | LD-382 (LD-383 – LD-387) |
| [FR-BE-04](BE4.md) | Add Code Analyzer to Docker Compose | LD-397 |
| [FR-BE-05](BE5.md) | Ghi nhận và hiển thị lịch sử thay đổi tài liệu (Documentation Change Log) | LD-177 (LD-178 – LD-182) |
| [FR-BE-06](BE6.md) | Cấu hình hệ thống LivingDocs (System Configuration) | LD-273 (LD-274, LD-275, LD-277 – LD-279) |
| [FR-FE-04](BE7.md) | Giao diện quản trị hệ thống và bảng điều khiển (Administration & Dashboard) | LD-316 (LD-317 – LD-321) |
| [FR-BE-08](BE8.md) | Release Smoke Testing & Deployment Verification | LD-404 |
| [FR-BE-09](BE9.md) | Liên kết Tài liệu – Mã nguồn và Xác minh Migration | LD-405, LD-211 (LD-212 – LD-216) |

Mỗi file gồm: mô tả, danh sách yêu cầu (FR-BE-xx.y / FR-FE-xx.y), API, dữ liệu, luồng chính, luồng lỗi, quy tắc nghiệp vụ, tiêu chí chấp nhận và test liên quan. Các con số (cổng kết nối, timeout, số phần tử, cờ lệnh) trong file là giá trị đang dùng trong code, để có thể dựng lại đúng hành vi.

## Thứ tự sử dụng

    Đồng bộ repo (FR-BE-01) → Phân tích Code Analyzer (FR-BE-04) → Sinh tài liệu & trích xuất Code Entities (FR-BE-09)
      → Gắn liên kết Tài liệu ↔ Mã nguồn & điều hướng (FR-BE-09) → Ghi nhận lịch sử thay đổi (FR-BE-05)
      → Quản trị & Cấu hình hệ thống (FR-BE-06, FR-FE-04) → Đóng gói Docker (FR-BE-03)
      → CI Build & Drift Guard (FR-BE-02) → Release Smoke Test (FR-BE-08)

## Quy ước chung

- **Hạ tầng & Cổng dịch vụ (Docker Compose):**
  - Frontend (`frontend/`): React / Vite / Nginx, cổng host `3000` (container cổng `80`).
  - Backend BFF (`backend/`): Spring Boot (Java 21/27), cổng `8080`, cơ sở dữ liệu `backend-db` (`postgres:16`, cổng host `5434`).
  - GitHub Integration Service (`services/github-integration-service/`): Spring Boot (Java 21), cổng `8082`, cơ sở dữ liệu `github-db` (`postgres:16`, cổng host `5433`).
  - AI Service (`ai-service/`): Python 3.12 / FastAPI, cổng `8001`.
  - Code Analyzer (`app/` / `code-analyzer/`): Python 3.12 / FastAPI, cổng `8000`.
- **Xác thực & Chuyển tiếp (BFF Pattern):** Frontend không gọi trực tiếp các microservice nội bộ. Mọi request đi qua Backend BFF (`:8080`) để xác thực phiên (Cookie/CSRF) và chuyển tiếp header `X-User-Id` cùng secret nội bộ (`GITHUB_INTEGRATION_INTERNAL_SECRET`, `AI_SERVICE_INTERNAL_SECRET`).
- **Biến môi trường & Bí mật:** File mẫu `.env.example` phải luôn chứa đầy đủ các khóa mẫu bao gồm `GITHUB_WEBHOOK_SECRET=` (để trống). Không bao giờ commit `.env` thật hay secrets chứa thông tin mật lên repository.
- **Tính nhất quán tài liệu (Drift Guard):** Mọi file Markdown (`*.md`) phải vượt qua `scripts/check_documentation_drift.py` để đảm bảo không có liên kết nội bộ hỏng hoặc thoát ranh giới repository.

## Không thuộc yêu cầu chức năng

Một số task hạ tầng, kiểm thử và CI/CD tự động hóa đóng vai trò đảm bảo chất lượng triển khai nên được quản lý tập trung trong luồng vận hành:

- **LD-376 (FR-BE-02):** Workflow `LivingDocs CI` (`.github/workflows/ci.yml`) tích hợp tự động hóa build/test đa dịch vụ và kiểm tra liên kết Markdown qua `scripts/check_documentation_drift.py`.
- **LD-382 (FR-BE-03) & LD-397 (FR-BE-04):** Đóng gói Dockerfile đa tầng và điều phối container qua `compose.yaml`.
- **LD-404 (FR-BE-08):** Kịch bản kiểm thử khói phát hành 2 pha pre-restart / post-restart (`scripts/verify-compose.sh` & `scripts/release_smoke_test.py`).
- **LD-405 (FR-BE-09):** Tự động nhận diện và chọn lineage Flyway migration (`FlywayMigrationLineageSelector`) nhằm đảm bảo tương thích dữ liệu cũ và mới trên CI PostgreSQL 16.