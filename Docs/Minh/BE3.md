# BE3 — LD-382 Docker & Deployment

| Mục | Nội dung |
|---|---|
| Story Jira | LD-382 Docker & Deployment |
| Task đã làm | — |
| Người thực hiện | — |
| Thành phần | `compose.yaml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `ai-service/Dockerfile`, `services/github-integration-service/Dockerfile`, `services/github-integration-service/docker-compose.yml`, `backend/src/main/resources/application.properties`, `services/github-integration-service/src/main/resources/application.yml` |
| Tác nhân | Developers / DevOps khởi động stack local bằng Compose |

## 1. Mô tả

Đóng gói các thành phần LivingDocs thành Docker images và điều phối bằng Docker Compose: PostgreSQL cho backend, PostgreSQL riêng cho GitHub Integration Service, backend Spring Boot, AI Service FastAPI, GitHub Integration Service Spring Boot, frontend React/Vite build tĩnh phục vụ bởi Nginx. Mục đích: khởi động môi trường local bằng một lệnh Compose, quản lý thứ tự phụ thuộc, healthcheck và volume dữ liệu.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| LD-382.1 | `backend/Dockerfile`: build stage Maven + Eclipse Temurin, `WORKDIR /app`, copy `pom.xml`/`src`, chạy `mvn -B -DskipTests package`; runtime stage Eclipse Temurin JDK, cài `curl`, copy JAR thành `/app/app.jar`, expose `8080`, entrypoint `java -jar app.jar`. |
| LD-382.2 | `frontend/Dockerfile`: build stage `node:24-alpine`, `npm ci`, copy source, `npm run build`; runtime `nginx:alpine`, copy `dist` vào `/usr/share/nginx/html`, copy `nginx.conf`, expose `80`, chạy Nginx foreground. |
| LD-382.3 | `ai-service/Dockerfile`: base `python:3.12-slim`, `WORKDIR /app`, `PYTHONDONTWRITEBYTECODE=1`/`PYTHONUNBUFFERED=1`, cài `requirements.txt`, copy source, expose `8001`, CMD `uvicorn main:app --host 0.0.0.0 --port 8001`. |
| LD-382.4 | `services/github-integration-service/Dockerfile`: build stage Maven + Eclipse Temurin 21, tải dependencies offline, copy `src`, package bỏ qua tests; runtime Eclipse Temurin 21 JRE, cài `curl`, copy JAR `github-integration-service-*.jar` thành `app.jar`, expose `8082`, CMD `java -jar app.jar`. |
| LD-382.5 | Compose service `backend-db`: PostgreSQL 16, DB `cnpm`, user/password `livingdocs`, host `5434` → container `5432`, volume `backend-db-data`, healthcheck `pg_isready -U livingdocs -d cnpm`. |
| LD-382.6 | Compose service `github-db`: PostgreSQL 16, DB `github_integration`, user/password `livingdocs`, host `5433` → container `5432`, volume `github-db-data`, healthcheck `pg_isready -U livingdocs -d github_integration`. |
| LD-382.7 | Compose service `backend`: build `./backend`, image `livingdocs-backend:local`, host `8080` → container `8080`, DB URL `jdbc:postgresql://backend-db:5432/cnpm`, depends on `backend-db` healthy, OAuth client id/secret qua env với placeholder local, healthcheck `http://localhost:8080/actuator/health`, start_period đủ dài cho Spring Boot. |
| LD-382.8 | Compose service `ai-service`: build `./ai-service`, image `livingdocs-ai:local`, host `8001` → container `8001`, healthcheck `/health` bằng Python urllib, start period ~15s. |
| LD-382.9 | Compose service `github-integration`: build `./services/github-integration-service`, image `livingdocs-github-integration:local`, host `8082` → container `8082`, DB URL `jdbc:postgresql://github-db:5432/github_integration`, nhận `TOKEN_ENCRYPTION_KEY`, GitHub client id/secret, app slug, redirect URI qua env, depends on `github-db` healthy, healthcheck actuator, start period ~30s. |
| LD-382.10 | Compose service `frontend`: build `./frontend`, image `livingdocs-frontend:local`, host `3000` → container `80`, depends on backend, ai-service, github-integration theo compose snapshot; frontend build static, không chạy Vite dev server. |
| LD-382.11 | Named volumes: `backend-db-data`, `github-db-data`; container nối trong network Compose mặc định ở phiên bản LD-382. Không tự suy diễn network segmentation LD-397. |
| LD-382.12 | Secret lấy qua `.env`/môi trường; không commit secret. `TOKEN_ENCRYPTION_KEY` đúng format AES-256-GCM mà `TokenEncryptor` yêu cầu. Không thay placeholder local thành credential production. |
| LD-382.13 | `services/github-integration-service/docker-compose.yml` chạy riêng PostgreSQL 16 dev cho GitHub integration, named volume `github-db-data`. |
| LD-382.14 | Healthcheck + `depends_on: condition: service_healthy` đảm bảo DB healthy trước backend/GitHub Integration. Healthcheck không thay thế kiểm thử end-to-end; `depends_on` không đảm bảo credential bên ngoài (GitHub OAuth/LLM) hợp lệ. |

## 3. API / Cổng và giao diện

| Loại | Địa chỉ / Endpoint | Kết quả | Yêu cầu |
|---|---|---|---|
| HTTP | Frontend host `3000` → container `80` | SPA static qua Nginx | LD-382.2, LD-382.10 |
| HTTP | Backend host `8080` → container `8080` | Spring Boot API | LD-382.7 |
| HTTP | GitHub Integration host `8082` → container `8082` | Spring Boot OAuth/API | LD-382.9 |
| HTTP | AI Service host `8001` → container `8001` | FastAPI | LD-382.8 |
| Health | Backend `GET /actuator/health` | `UP` | LD-382.7 |
| Health | GitHub Integration `GET /actuator/health` | `UP` | LD-382.9 |
| Health | AI Service `GET /health` | `OK` | LD-382.8 |
| TCP | Backend DB `backend-db:5432` (host `5434`) | PostgreSQL healthy | LD-382.5 |
| TCP | GitHub DB `github-db:5432` (host `5433`) | PostgreSQL healthy | LD-382.6 |

## 4. Luồng chính

1. Từ root repo chạy `docker compose config` (đã có biến bắt buộc) để parse.
2. `docker compose build` build các images: backend, frontend, ai-service, github-integration.
3. `docker compose up -d` khởi động services.
4. PostgreSQL `backend-db` và `github-db` chạy, healthcheck `pg_isready` → healthy.
5. Backend khởi động sau khi `backend-db` healthy; GitHub Integration khởi động sau khi `github-db` healthy.
6. AI Service và Frontend khởi động; frontend phục vụ ở host port 3000; browser gọi backend/GitHub Integration qua reverse proxy Nginx.
7. Kiểm tra trạng thái bằng `docker compose ps`, xem log bằng `docker compose logs -f <service>`.
8. Dừng stack bằng `docker compose down` (giữ volumes) hoặc `docker compose down -v` (xóa volumes — reset dữ liệu).

## 5. Luồng lỗi

| Trường hợp | Kết quả |
|---|---|
| Thiếu biến bắt buộc (`TOKEN_ENCRYPTION_KEY`, GitHub client/secret…) | `docker compose config` fail |
| DB chưa healthy | Backend/GitHub Integration không khởi động (depends_on healthy) |
| Build backend/frontend/AI/GitHub Integration lỗi | `docker compose build` fail, image tương ứng không có |
| Backend healthcheck fail | Container bị đánh dấu unhealthy; service phụ thuộc không vượt qua |
| GitHub OAuth/LLM sai credential | Healthcheck vẫn có thể `UP`, nhưng tích hợp bên ngoài fail — cần kiểm tra cấu hình |
| Secret bị hard-code hoặc commit | Vi phạm nguyên tắc bảo mật |
| Chạy `down` (không `-v`) | Named volumes giữ nguyên, dữ liệu DB còn |
| Chạy `down -v` | Xóa volumes, dữ liệu DB mất |

## 6. Quy tắc nghiệp vụ

- Root `compose.yaml` là nguồn orchestration chính.
- Dùng tên service Compose làm hostname trong JDBC URL, không dùng `localhost` giữa các container.
- Dùng healthcheck + `depends_on: condition: service_healthy` cho DB dependency.
- Dùng named volume cho dữ liệu PostgreSQL; `docker compose down` không xóa, `down -v` mới xóa.
- Không gộp hai PostgreSQL database thành một khi tái tạo LD-382.
- Khi tái tạo LD-382, không tự áp dụng network hardening/loopback binding của LD-397, không thêm analyzer service LD-397.
- Build backend dùng `-DskipTests`; test chạy riêng qua Maven/CI.
- Đây là Compose local/development/demo; không có Kubernetes manifests, autoscaling, rolling deploy, ingress, secret manager.
- AI Service có thể cần `ANTHROPIC_API_KEY` để dùng LLM thật; thiếu key thì hỗ trợ offline generator.
- Không đưa `.env` thật vào Git; giữ chính xác port, volume name, service name, internal DNS.

## 7. Tiêu chí chấp nhận

- **AC-LD-382.1:** `docker compose config` parse thành công khi đã cung cấp biến bắt buộc.
- **AC-LD-382.2:** Tất cả images build thành công.
- **AC-LD-382.3:** PostgreSQL containers healthy và giữ dữ liệu sau recreate.
- **AC-LD-382.4:** Backend kết nối `backend-db`.
- **AC-LD-382.5:** GitHub Integration Service kết nối `github-db`.
- **AC-LD-382.6:** `/actuator/health` của các Spring services trả `healthy`.
- **AC-LD-382.7:** AI Service `/health` trả `OK`.
- **AC-LD-382.8:** Frontend phục vụ ở host port 3000.
- **AC-LD-382.9:** `docker compose down` không xóa named volumes; `down -v` mới xóa.
- **AC-LD-382.10:** Secret không bị hard-code vào source hoặc commit vào repository.

## 8. Kiểm thử

Kiểm thử thủ công theo mục 4 + mục 7 trong môi trường local. Tự động hóa một phần qua job `Docker Compose Validation` trong workflow CI LD-376.