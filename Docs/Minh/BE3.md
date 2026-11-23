# FR-BE—03 Docker & Deployment

| Mục | Nội dung |
|---|---|
| Story Jira | LD-382 [Docker & Deployment] Implement Docker & Deployment (Epic LD-358) |
| Task đã làm | LD-383 – LD-387 (`LD-383` Create Backend Docker Configuration, `LD-384` Create Frontend Docker Configuration, `LD-385` Create AI Service Docker Configuration, `LD-386` Configure Service Deployment, `LD-387` Test Docker Deployment) |
| Người thực hiện | Nguyễn Lê Minh |
| Nhánh / PR & Trạng thái | Đã hợp nhất vào `main` |
| Thành phần | `compose.yaml`, `.dockerignore`, `backend/Dockerfile`, `frontend/Dockerfile`, `ai-service/Dockerfile`, `services/github-integration-service/Dockerfile`, `services/github-integration-service/docker-compose.yml`, `services/github-integration-service/.env.example`, `.github/workflows/ci.yml`, `backend/src/main/resources/application.properties`, `services/github-integration-service/src/main/resources/application.yml` |
| Tác nhân | Developers / DevOps khởi động stack local bằng Docker Compose; GitHub Actions (`docker-compose-validation`) |

## 1. Mô tả

Chức năng đóng gói các dịch vụ của hệ thống LivingDocs thành Docker images và điều phối triển khai bằng Docker Compose (`compose.yaml`). Kiến trúc triển khai gồm 6 container services: 2 cơ sở dữ liệu PostgreSQL 16 độc lập (`backend-db` và `github-db`), `backend` (Spring Boot / Java 27), `github-integration` (Spring Boot / Java 21), `ai-service` (FastAPI / Python 3.12), và `frontend` (React/Vite build tĩnh phục vụ qua Nginx). Hệ thống hỗ trợ khởi động môi trường local đồng bộ qua một lệnh Docker Compose, quản lý thứ tự khởi chạy bằng healthcheck, lưu trữ bền vững qua named volumes và tích hợp bước kiểm tra cấu hình/build image trong pipeline CI/CD.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-BE—03.1 | Cấu hình `.dockerignore` ở thư mục gốc để loại trừ `.git`, `.github`, `**/node_modules`, `**/target`, `**/dist`, `**/__pycache__`, `**/.pytest_cache`, `**/.venv`, `**/venv`, `**/.env`, `**/.env.*` (giữ lại `!**/.env.example`) khỏi build context. |
| FR-BE—03.2 | `backend/Dockerfile` (`LD-383`): multi-stage build sử dụng `maven:3.10-eclipse-temurin-27` (`WORKDIR /app`, copy `pom.xml` và `src`, chạy `mvn -B -DskipTests package`); runtime stage dùng `eclipse-temurin:27-jdk`, cài `curl`, copy `/app/target/*.jar` thành `app.jar`, mở cổng `8080` và chạy `ENTRYPOINT ["java", "-jar", "app.jar"]`. |
| FR-BE—03.3 | `frontend/Dockerfile` (`LD-384`): multi-stage build sử dụng `node:24-alpine` (`WORKDIR /app`, copy `package*.json`, chạy `npm ci`, copy mã nguồn và chạy `npm run build`); runtime stage dùng `nginx:alpine`, copy `/app/dist` vào `/usr/share/nginx/html`, mở cổng `80` và chạy `CMD ["nginx", "-g", "daemon off;"]`. |
| FR-BE—03.4 | `ai-service/Dockerfile` (`LD-385`): sử dụng base image `python:3.12-slim`, `WORKDIR /app`, thiết lập `PYTHONDONTWRITEBYTECODE=1` và `PYTHONUNBUFFERED=1`, cài đặt `requirements.txt` với `--no-cache-dir`, copy mã nguồn, mở cổng `8001` và chạy `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]`. |
| FR-BE—03.5 | `services/github-integration-service/Dockerfile` (`LD-383`): multi-stage build sử dụng `maven:3.9-eclipse-temurin-21` (`WORKDIR /app`, copy `pom.xml`, chạy `mvn -q -B dependency:go-offline`, copy `src`, chạy `mvn -q -B package -DskipTests`); runtime stage dùng `eclipse-temurin:21-jre`, copy `/app/target/github-integration-service-*.jar` thành `app.jar`, mở cổng `8082` và chạy `ENTRYPOINT ["java", "-jar", "app.jar"]`. |
| FR-BE—03.6 | Compose service `backend-db` (`LD-386`): dùng image `postgres:16`, khởi tạo `POSTGRES_DB=cnpm`, `POSTGRES_USER=livingdocs`, `POSTGRES_PASSWORD=livingdocs`, ánh xạ cổng `5434:5432`, gắn volume `backend-db-data:/var/lib/postgresql/data` và healthcheck `pg_isready -U livingdocs -d cnpm` (interval `5s`, timeout `3s`, retries `20`). |
| FR-BE—03.7 | Compose service `github-db` (`LD-386`): dùng image `postgres:16`, khởi tạo `POSTGRES_DB=github_integration`, `POSTGRES_USER=livingdocs`, `POSTGRES_PASSWORD=livingdocs`, ánh xạ cổng `5433:5432`, gắn volume `github-db-data:/var/lib/postgresql/data` và healthcheck `pg_isready -U livingdocs -d github_integration` (interval `5s`, timeout `3s`, retries `20`). |
| FR-BE—03.8 | Compose service `backend` (`LD-386`): build từ `./backend` thành image `livingdocs-backend:local`, ánh xạ cổng `8080:8080`, cấu hình `DB_URL=jdbc:postgresql://backend-db:5432/cnpm`, truyền biến OAuth GitHub qua env với giá trị mặc định `local-placeholder`, phụ thuộc `backend-db` (`condition: service_healthy`), và healthcheck `curl -fsS http://localhost:8080/actuator/health` (`start_period: 60s`). |
| FR-BE—03.9 | Compose service `ai-service` (`LD-386`): build từ `./ai-service` thành image `livingdocs-ai:local`, ánh xạ cổng `8001:8001`, và healthcheck gọi `http://localhost:8001/health` bằng `python3` (`urllib.request`, `start_period: 15s`). |
| FR-BE—03.10 | Compose service `github-integration` (`LD-386`): build từ `./services/github-integration-service` thành image `livingdocs-github-integration:local`, ánh xạ cổng `8082:8082`, cấu hình `DB_URL=jdbc:postgresql://github-db:5432/github_integration`, bắt buộc truyền `TOKEN_ENCRYPTION_KEY` qua `.env`/environment, truyền đầy đủ các biến cấu hình runtime theo `services/github-integration-service/.env.example` (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_APP_SLUG`, `GITHUB_REDIRECT_URI`, `GITHUB_INTEGRATION_INTERNAL_SECRET`, `GITHUB_WEBHOOK_SECRET`), phụ thuộc `github-db` (`condition: service_healthy`) và healthcheck endpoint `/actuator/health` (`start_period: 30s`). |
| FR-BE—03.11 | Compose service `frontend` (`LD-386`): build từ `./frontend` thành image `livingdocs-frontend:local`, ánh xạ cổng `3000:80`, khai báo `depends_on` tới `backend`, `ai-service` và `github-integration`. |
| FR-BE—03.12 | Khai báo 2 named volumes `backend-db-data` và `github-db-data` ở cấp root `compose.yaml`; các container giao tiếp nội bộ qua DNS tên service trên mạng bridge mặc định của Compose. |
| FR-BE—03.13 | Cung cấp `services/github-integration-service/docker-compose.yml` để khởi chạy độc lập container PostgreSQL 16 (`livingdocs-github-db`, cổng `5433:5432`, volume `github-db-data`) phục vụ phát triển riêng lẻ service này, kèm file mẫu `.env.example` (giữ nguyên biến trống `GITHUB_WEBHOOK_SECRET=` để xác minh chữ ký webhook GitHub App). |
| FR-BE—03.14 | Tích hợp CI/CD (`LD-387`): job `Docker Compose Validation` trong `.github/workflows/ci.yml` chạy `docker compose -f compose.yaml config --quiet` và `docker compose -f compose.yaml build backend ai-service github-integration frontend` với `TOKEN_ENCRYPTION_KEY` giả lập (`ci-validation-placeholder-only`). |

## 3. API / Giao diện

| Loại | Địa chỉ / Lệnh / Endpoint | Kết quả | Yêu cầu |
|---|---|---|---|
| HTTP | Frontend `http://localhost:3000` (host `3000` → container `80`) | Phục vụ giao diện SPA tĩnh qua Nginx | FR-BE—03.3, FR-BE—03.11 |
| HTTP | Backend `http://localhost:8080` (host `8080` → container `8080`) | Spring Boot REST API & OAuth2 | FR-BE—03.2, FR-BE—03.8 |
| HTTP | GitHub Integration `http://localhost:8082` (host `8082` → container `8082`) | Spring Boot GitHub Integration API & Swagger UI | FR-BE—03.5, FR-BE—03.10 |
| HTTP | AI Service `http://localhost:8001` (host `8001` → container `8001`) | FastAPI Documentation Generation Service | FR-BE—03.4, FR-BE—03.9 |
| Health | `GET http://localhost:8080/actuator/health` | Trả về `{"status":"UP"}` khi Backend sẵn sàng | FR-BE—03.8 |
| Health | `GET http://localhost:8082/actuator/health` | Trả về `{"status":"UP"}` khi GitHub Integration sẵn sàng | FR-BE—03.10 |
| Health | `GET http://localhost:8001/health` | Trả về `{"status":"ok","generator":...}` khi AI Service sẵn sàng | FR-BE—03.9 |
| TCP | `backend-db:5432` (host `5434:5432`) | PostgreSQL 16 database `cnpm` sẵn sàng nhận kết nối | FR-BE—03.6 |
| TCP | `github-db:5432` (host `5433:5432`) | PostgreSQL 16 database `github_integration` sẵn sàng nhận kết nối | FR-BE—03.7 |
| CLI | `docker compose -f compose.yaml config --quiet` | Kiểm tra cú pháp và biến môi trường bắt buộc trong `compose.yaml` | FR-BE—03.14 |
| CLI | `docker compose -f compose.yaml up -d --build` | Build images và khởi chạy toàn bộ 6 containers ở chế độ nền | FR-BE—03.6 – FR-BE—03.12 |

## 4. Luồng chính

1. Developer chuẩn bị biến môi trường (tối thiểu `TOKEN_ENCRYPTION_KEY` chuỗi Base64 32 byte cùng `GITHUB_INTEGRATION_INTERNAL_SECRET` và `GITHUB_WEBHOOK_SECRET` theo mẫu `services/github-integration-service/.env.example`) ở file `.env` tại root hoặc biến môi trường shell.
2. Chạy `docker compose -f compose.yaml config --quiet` để kiểm tra tính hợp lệ của cấu hình Compose và đảm bảo các biến bắt buộc đã được nạp.
3. Chạy `docker compose -f compose.yaml build` để đóng gói 4 application images: `livingdocs-backend:local`, `livingdocs-ai:local`, `livingdocs-github-integration:local` và `livingdocs-frontend:local`.
4. Chạy `docker compose -f compose.yaml up -d` để khởi động toàn bộ stack.
5. Hai container cơ sở dữ liệu `backend-db` và `github-db` khởi chạy trước, gắn volume bền vững và thực thi healthcheck `pg_isready` cho đến khi đạt trạng thái `healthy`.
6. Sau khi DB tương ứng đạt `healthy`, `backend` kết nối tới `jdbc:postgresql://backend-db:5432/cnpm` và `github-integration` kết nối tới `jdbc:postgresql://github-db:5432/github_integration` (chạy Flyway migration tự động).
7. `ai-service` (port `8001`) và `frontend` (port `3000`) khởi động hoàn tất; Developer kiểm tra trạng thái qua `docker compose ps` và kiểm tra các endpoint healthcheck.
8. Khi dừng hệ thống, chạy `docker compose down` để tắt container mà vẫn giữ dữ liệu trong `backend-db-data` và `github-db-data`, hoặc `docker compose down -v` khi cần xóa sạch dữ liệu database.

## 5. Luồng lỗi

| Trường hợp | Cơ chế xử lý & Kết quả |
|---|---|
| Thiếu biến bắt buộc `TOKEN_ENCRYPTION_KEY` hoặc biến rỗng | Lệnh `docker compose config` / `up` dừng ngay lập tức với thông báo lỗi `TOKEN_ENCRYPTION_KEY must be set in .env`. |
| `TOKEN_ENCRYPTION_KEY` sai định dạng Base64 hoặc khác 32 byte | `TokenEncryptor` ném `IllegalStateException` khi khởi tạo bean, container `github-integration` dừng khởi động. |
| `backend-db` hoặc `github-db` chưa đạt trạng thái `healthy` | `backend` và `github-integration` không khởi động nhờ ràng buộc `depends_on: condition: service_healthy`. |
| Lỗi biên dịch Maven hoặc `npm run build` trong quá trình build image | `docker compose build` và job CI `Docker Compose Validation` fail với exit code khác 0. |
| Runtime image `eclipse-temurin:21-jre` của `github-integration` thiếu lệnh `curl` | Lệnh healthcheck `curl -fsS http://localhost:8082/actuator/health` trong `compose.yaml` sẽ báo lỗi thực thi trên container nếu chưa cài `curl` trong `Dockerfile`. |
| Sai thông tin GitHub OAuth hoặc thiếu `ANTHROPIC_API_KEY` | Container vẫn khởi động (`health` endpoint vẫn `UP`), nhưng thao tác OAuth thật sẽ lỗi hoặc `ai-service` chuyển sang chế độ offline generator. |
| Chạy `docker compose down` (không có `-v`) vs `docker compose down -v` | Không có `-v` giữ nguyên dữ liệu PostgreSQL; có `-v` xóa toàn bộ named volumes `backend-db-data` và `github-db-data`. |

## 6. Quy tắc nghiệp vụ

- `compose.yaml` tại thư mục gốc là cấu hình điều phối chính cho toàn bộ stack local/development; `services/github-integration-service/docker-compose.yml` chỉ dùng khi phát triển độc lập service GitHub Integration.
- Giao tiếp giữa các container sử dụng tên service Compose làm hostname nội bộ (`backend-db`, `github-db`), không dùng `localhost`.
- Hai cơ sở dữ liệu `cnpm` (`backend-db`) và `github_integration` (`github-db`) được tách biệt hoàn toàn cả về container, cổng host (`5434` và `5433`) lẫn named volume (`backend-db-data` và `github-db-data`).
- Mọi secret (`TOKEN_ENCRYPTION_KEY`, `GITHUB_INTEGRATION_INTERNAL_SECRET`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, OAuth credentials) phải nạp qua `.env` hoặc biến môi trường; tuyệt đối không commit `.env` thật vào Git (`.dockerignore` và `.gitignore` đã chặn file `.env`).
- Các Dockerfile Java sử dụng `-DskipTests` để tối ưu tốc độ đóng gói image; việc chạy unit/integration test được đảm nhiệm bởi các job kiểm thử chuyên biệt trong `.github/workflows/ci.yml`.
- Phạm vi `LD-382` tập trung vào đóng gói container và triển khai local/CI validation; chưa bao gồm reverse proxy `nginx.conf` tùy chỉnh cho SPA, tách network segmentation, ràng buộc loopback `127.0.0.1` hay triển khai Kubernetes/production.

## 7. Tiêu chí chấp nhận

- **AC-BE-03.1:** `docker compose -f compose.yaml config --quiet` thực thi thành công khi cung cấp đủ biến môi trường bắt buộc và báo lỗi rõ ràng khi thiếu `TOKEN_ENCRYPTION_KEY`.
- **AC-BE-03.2:** Cả 4 application images (`livingdocs-backend:local`, `livingdocs-frontend:local`, `livingdocs-ai:local`, `livingdocs-github-integration:local`) build thành công qua `docker compose build`.
- **AC-BE-03.3:** Hai container PostgreSQL 16 (`backend-db` trên cổng `5434`, `github-db` trên cổng `5433`) đạt trạng thái `healthy` và bảo toàn dữ liệu qua các lần khởi động lại container.
- **AC-BE-03.4:** `backend` kết nối thành công tới `backend-db` và endpoint `http://localhost:8080/actuator/health` trả về `UP`.
- **AC-BE-03.5:** `github-integration` kết nối thành công tới `github-db`, chạy Flyway migration và endpoint `http://localhost:8082/actuator/health` trả về `UP`.
- **AC-BE-03.6:** `ai-service` khởi động trên cổng `8001` và endpoint `http://localhost:8001/health` trả về trạng thái `ok`.
- **AC-BE-03.7:** `frontend` phục vụ thành công bản build tĩnh qua Nginx tại `http://localhost:3000`.
- **AC-BE-03.8:** `docker compose down` giữ nguyên named volumes `backend-db-data`, `github-db-data`; `docker compose down -v` xóa sạch volumes.
- **AC-BE-03.9:** Không có secret thật bị hard-code trong Dockerfile, `compose.yaml` hoặc commit vào repository.
- **AC-BE-03.10:** Job `Docker Compose Validation` trong `.github/workflows/ci.yml` chạy thành công bước kiểm tra cấu hình và build toàn bộ service images.

## 8. Kiểm thử

Kiểm thử triển khai Docker (`LD-387`) được thực hiện theo hai lớp:
1. **Tự động hóa trong CI:** Job `Docker Compose Validation` trong `.github/workflows/ci.yml` tự động chạy `docker compose -f compose.yaml config --quiet` và `docker compose -f compose.yaml build backend ai-service github-integration frontend` trên mỗi lần push/PR.
2. **Kiểm thử vận hành local:** Khởi chạy `docker compose up -d`, xác minh trạng thái `healthy` của `backend-db`, `github-db`, `backend`, `ai-service`, kiểm tra giao diện web tại `http://localhost:3000` và kiểm tra độ bền dữ liệu volume qua chu trình `docker compose down` / `up -d` (lưu ý bổ sung cài đặt `curl` vào runtime stage của `services/github-integration-service/Dockerfile` để healthcheck container `github-integration` hoạt động ổn định).