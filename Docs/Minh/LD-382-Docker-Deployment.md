# LivingDocs — Đặc tả tái tạo chức năng LD-382: Docker & Deployment

> Tài liệu được trích xuất từ `LivingDocs-LD-382.zip`, branch `LD-382-Implement-Docker-&-Deployment`. Mục tiêu là tái tạo cấu hình container hóa và chạy đồng bộ các service hiện có; đây không phải mô tả một hệ thống Kubernetes hay triển khai cloud.

## 1. Mục tiêu

Đóng gói các thành phần LivingDocs thành Docker images và điều phối bằng Docker Compose:
- PostgreSQL cho backend.
- PostgreSQL riêng cho GitHub Integration Service.
- Backend Spring Boot.
- AI Service FastAPI.
- GitHub Integration Service Spring Boot.
- Frontend React/Vite được build và phục vụ bằng Nginx.

Mục đích: khởi động môi trường local bằng một lệnh Compose, quản lý thứ tự phụ thuộc, healthcheck và volume dữ liệu.

## 2. File và vị trí mã nguồn

- `compose.yaml`: orchestration ở root.
- `backend/Dockerfile`: build backend Java và chạy JAR.
- `frontend/Dockerfile`: build React app và serve qua Nginx.
- `frontend/nginx.conf`: cấu hình Nginx SPA/reverse proxy theo source snapshot.
- `ai-service/Dockerfile`: image Python FastAPI.
- `services/github-integration-service/Dockerfile`: multi-stage Maven + JRE.
- `services/github-integration-service/docker-compose.yml`: Compose riêng để chạy PostgreSQL dev cho service GitHub integration.
- `backend/src/main/resources/application.properties`: cấu hình DB và server backend.
- `services/github-integration-service/src/main/resources/application.yml`: cấu hình DB, GitHub OAuth, token encryption, CORS và actuator.

## 3. Kiến trúc container

```text
Browser
  -> frontend (Nginx, host port 3000)
       -> backend (Spring Boot, host port 8080)
       -> GitHub Integration (host port 8082 cho OAuth callback/API theo cấu hình)

backend-db (PostgreSQL) <-> backend
github-db (PostgreSQL) <-> github-integration
ai-service (FastAPI, port 8001)
```

Compose snapshot định nghĩa named volumes:
- `backend-db-data`
- `github-db-data`

Các container được nối trong network Compose mặc định ở phiên bản LD-382. Không tự suy diễn thêm network segmentation của snapshot LD-397.

## 4. Dockerfile theo service

### 4.1 Backend

- Build stage dùng Maven + Eclipse Temurin.
- `WORKDIR /app`.
- Copy `pom.xml`, `src`.
- Chạy `mvn -B -DskipTests package`.
- Runtime stage dùng Eclipse Temurin JDK image trong snapshot.
- Cài `curl` để healthcheck có thể gọi actuator.
- Copy JAR thành `/app/app.jar`.
- Expose `8080`.
- Entrypoint: `java -jar app.jar`.

### 4.2 Frontend

- Build stage: `node:24-alpine`.
- Copy `package*.json`, chạy `npm ci`.
- Copy source và chạy `npm run build`.
- Runtime: `nginx:alpine`.
- Copy `dist` vào `/usr/share/nginx/html`.
- Copy `nginx.conf` vào Nginx config.
- Expose `80`, chạy Nginx foreground.

### 4.3 AI Service

- Base image `python:3.12-slim`.
- `WORKDIR /app`.
- Set `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`.
- Copy requirements và `pip install --no-cache-dir -r requirements.txt`.
- Copy source.
- Expose `8001`.
- Run `uvicorn main:app --host 0.0.0.0 --port 8001`.

### 4.4 GitHub Integration Service

- Build stage Maven + Eclipse Temurin 21.
- Copy `pom.xml`, tải dependencies offline, copy `src`, package bỏ qua tests trong image build.
- Runtime stage Eclipse Temurin 21 JRE.
- Cài `curl`, copy JAR `github-integration-service-*.jar` thành `app.jar`.
- Expose `8082`, chạy `java -jar app.jar`.

## 5. Docker Compose services

### 5.1 backend-db

- Image PostgreSQL 16.
- Database `cnpm`, user/password `livingdocs`.
- Host port `5434` map vào container `5432`.
- Named volume `backend-db-data`.
- Healthcheck `pg_isready -U livingdocs -d cnpm`.

### 5.2 github-db

- Image PostgreSQL 16.
- Database `github_integration`, user/password `livingdocs`.
- Host port `5433` map vào container `5432`.
- Named volume `github-db-data`.
- Healthcheck `pg_isready -U livingdocs -d github_integration`.

### 5.3 backend

- Build context `./backend`, Dockerfile `Dockerfile`.
- Image `livingdocs-backend:local`.
- Host `8080` -> container `8080`.
- DB URL nội bộ `jdbc:postgresql://backend-db:5432/cnpm`.
- Depends on `backend-db` healthy.
- OAuth client id/secret lấy từ environment, có placeholder mặc định local.
- Healthcheck gọi `http://localhost:8080/actuator/health`.
- `start_period` đủ dài cho Spring Boot startup.

### 5.4 ai-service

- Build context `./ai-service`.
- Image `livingdocs-ai:local`.
- Host `8001` -> container `8001`.
- Healthcheck gọi `http://localhost:8001/health` bằng Python urllib.
- Start period khoảng 15 giây.

### 5.5 github-integration

- Build context `./services/github-integration-service`.
- Image `livingdocs-github-integration:local`.
- Host `8082` -> container `8082`.
- DB URL nội bộ `jdbc:postgresql://github-db:5432/github_integration`.
- Nhận `TOKEN_ENCRYPTION_KEY`, GitHub client id/secret, app slug và redirect URI qua environment.
- Depends on `github-db` healthy.
- Healthcheck gọi actuator health endpoint.
- Start period khoảng 30 giây.

### 5.6 frontend

- Build context `./frontend`.
- Image `livingdocs-frontend:local`.
- Host port `3000` -> container Nginx port `80`.
- Depends on backend, AI service và GitHub integration theo compose snapshot.
- Frontend được build thành static assets, không chạy Vite dev server trong container production-like.

## 6. Biến môi trường và bảo mật

GitHub Integration Service yêu cầu:
- `TOKEN_ENCRYPTION_KEY`: khóa mã hóa token, bắt buộc trong Compose.
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `GITHUB_APP_SLUG`
- `GITHUB_REDIRECT_URI`

Backend có:
- `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`.
- OAuth GitHub client id/secret nếu backend dùng OAuth login.

Quy tắc:
- Secret phải cung cấp qua `.env` hoặc môi trường triển khai; không commit secret thật.
- `TOKEN_ENCRYPTION_KEY` phải là khóa phù hợp độ dài/format mà `TokenEncryptor` yêu cầu (trong service là khóa AES-256-GCM).
- Không thay placeholder local thành credential production.
- PostgreSQL data phải nằm trong named volume để container recreate không làm mất dữ liệu.
- Khi tái tạo từ snapshot LD-382, không tự áp dụng network hardening/loopback binding của LD-397 nếu mục tiêu là tái tạo chính xác LD-382.

## 7. Cách chạy

Từ thư mục root:

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

Theo dõi log:

```bash
docker compose logs -f backend
docker compose logs -f github-integration
docker compose logs -f ai-service
docker compose logs -f frontend
```

Dừng stack:

```bash
docker compose down
```

Giữ dữ liệu database bằng cách không thêm `-v`. Chỉ xóa volumes khi chủ động muốn reset dữ liệu.

Để chạy riêng database GitHub Integration Service trong development:

```bash
cd services/github-integration-service
docker compose up -d
```

Compose riêng sử dụng PostgreSQL 16 và named volume `github-db-data`.

## 8. Healthcheck và phụ thuộc

- Database phải healthy trước khi backend/GitHub Integration Service khởi động.
- Backend healthcheck dùng Spring Actuator.
- GitHub Integration healthcheck dùng Spring Actuator.
- AI Service healthcheck dùng `/health`.
- Healthcheck là cơ chế báo trạng thái container; không thay thế kiểm thử chức năng end-to-end.
- `depends_on` chỉ đảm bảo điều kiện phụ thuộc đã cấu hình, không đảm bảo mọi tích hợp bên ngoài (GitHub OAuth/LLM) có credential hợp lệ.

## 9. Giới hạn và lưu ý tái tạo

- Đây là Docker Compose cho môi trường local/development hoặc demo; không có Kubernetes manifests.
- Không có autoscaling, rolling deployment, ingress controller hay secret manager.
- Việc build image backend dùng `-DskipTests`; test cần chạy riêng bằng Maven/CI.
- AI Service có thể cần `ANTHROPIC_API_KEY` để dùng LLM thật; thiếu key thì code snapshot hỗ trợ offline generator.
- GitHub OAuth cần GitHub App/client credentials và redirect URI khớp cấu hình.
- Không đưa `.env` thật vào Git.
- Giữ chính xác port mapping, volume names, service names và internal DNS names vì các service dùng tên Compose để kết nối nhau.

## 10. Tiêu chí chấp nhận

1. `docker compose config` parse thành công khi đã cung cấp biến bắt buộc.
2. Tất cả images build thành công.
3. PostgreSQL containers healthy và giữ dữ liệu sau recreate.
4. Backend kết nối `backend-db`.
5. GitHub Integration Service kết nối `github-db`.
6. `/actuator/health` của các Spring services trả trạng thái healthy.
7. AI Service `/health` trả trạng thái OK.
8. Frontend được phục vụ ở host port 3000.
9. `docker compose down` không xóa named volumes; `down -v` mới xóa.
10. Secret không bị hard-code vào source hoặc commit vào repository.

## 11. Hướng dẫn cho AI tái tạo code

- Tạo một Dockerfile riêng cho mỗi service theo đúng build/runtime stage.
- Root `compose.yaml` là nguồn orchestration chính.
- Dùng tên service làm hostname trong các JDBC URLs, không dùng `localhost` giữa các container.
- Dùng healthchecks và `depends_on: condition: service_healthy` cho database dependencies.
- Dùng named volumes cho dữ liệu PostgreSQL.
- Không gộp hai PostgreSQL database thành một database nếu đang tái tạo snapshot LD-382.
- Không đưa các network riêng, loopback host bindings hay analyzer service từ LD-397 vào tài liệu/implementation LD-382.
