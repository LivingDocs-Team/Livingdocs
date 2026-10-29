# Code Analyzer trong Docker Compose (LD-397)

Code Analyzer (`code-analyzer/`, FastAPI, mã nguồn ở `app/`) chạy cùng các service MVP khác trong `compose.yaml`.

## Cấu hình

| Hạng mục | Giá trị |
|---|---|
| Service | `code-analyzer` |
| Build | context = thư mục gốc, `code-analyzer/Dockerfile` (Python 3.12, user không phải root) |
| Cổng | 8000 (publish `127.0.0.1:8000:8000` chỉ để debug) |
| Network | `analysis-internal` (chung với `github-integration` và `ai-service`) |
| Health check | `GET /health` → `{"status":"ok","service":"code-analyzer"}` |
| Biến môi trường | Analyzer không cần biến nào. Phía gọi dùng `CODE_ANALYZER_BASE_URL=http://code-analyzer:8000` (đã đặt cho `github-integration`) |

`github-integration` (service gọi analyzer trong luồng backend) `depends_on` `code-analyzer` với `condition: service_healthy`,
nên nó chỉ khởi động khi analyzer đã sẵn sàng.

## Chuẩn bị

Tạo `.env` ở thư mục gốc (xem `.env.example` của `services/github-integration-service`) với tối thiểu:

```
TOKEN_ENCRYPTION_KEY=<base64 32 byte>
GITHUB_INTEGRATION_INTERNAL_SECRET=<chuỗi bí mật>
```

## Lệnh kiểm tra local

```bash
# 1. Kiểm tra cú pháp compose
docker compose -f compose.yaml config --quiet

# 2. Build và chạy toàn bộ MVP (analyzer, ai-service, github-integration, backend, DB, frontend)
docker compose -f compose.yaml up --build -d

# 3. Trạng thái / health của các service
docker compose -f compose.yaml ps

# 4. Health check analyzer từ máy host
curl -fsS http://localhost:8000/health

# 5. Backend -> analyzer qua tên service (chạy từ container github-integration)
docker compose -f compose.yaml exec github-integration curl -fsS http://code-analyzer:8000/health
docker compose -f compose.yaml exec github-integration curl -fsS -X POST http://code-analyzer:8000/api/v1/analyze-repo \
  -H 'Content-Type: application/json' \
  -d '{"target":"demo/repo","scope":"repository","files":[{"path":"a.py","content":"def add(a, b):\n    return a + b\n","language":"python"}]}'

# 6. Các service còn lại
curl -fsS http://localhost:8001/health            # ai-service
curl -fsS http://localhost:8080/actuator/health   # backend
curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:3000/   # frontend

# 7. Log / dọn dẹp
docker compose -f compose.yaml logs -f code-analyzer
docker compose -f compose.yaml down        # thêm -v để xoá cả dữ liệu DB
```

Tất cả bước 1–6 được gói trong một script:

```bash
./scripts/verify-compose.sh            # build + up + kiểm tra
./scripts/verify-compose.sh --no-up    # chỉ kiểm tra stack đang chạy
```

## Xử lý sự cố

- `github-integration` không lên: kiểm tra `docker compose logs code-analyzer`; service này chờ analyzer healthy.
- `TOKEN_ENCRYPTION_KEY must be set in .env`: thiếu biến trong `.env`.
- Cổng 8000 bị chiếm: dừng tiến trình khác hoặc đổi mapping `127.0.0.1:8000:8000` trong `compose.yaml`.
