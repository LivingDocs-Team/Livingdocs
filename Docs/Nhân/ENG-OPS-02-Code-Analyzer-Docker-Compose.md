# ENG-OPS-02 — Code Analyzer trong Docker Compose

| Mục | Nội dung |
|---|---|
| Story / Task Jira | LD-397 — Code Analyzer integration / Docker Compose |
| Người thực hiện | Nhân |
| Thành phần | `code-analyzer/`, `compose.yaml`, GitHub Integration Service |
| Tác nhân | Developer/CI và GitHub Integration Service |
| Mục tiêu | Đóng gói Code Analyzer thành service độc lập và cho phép GitHub Integration gọi qua Docker internal network |

## 1. Mô tả

Code Analyzer là service FastAPI độc lập. Docker Compose phải build và chạy service này cùng stack LivingDocs, kiểm tra readiness trước khi GitHub Integration phụ thuộc vào nó, đồng thời giữ giao tiếp service-to-service trong network nội bộ.

## 2. Yêu cầu kỹ thuật

| ID | Yêu cầu |
|---|---|
| ENG-OPS-02.1 | Compose khai báo service `code-analyzer` với build context và Dockerfile trỏ đúng thư mục `code-analyzer/`. |
| ENG-OPS-02.2 | Service expose cổng container 8000; nếu publish ra host để debug local thì chỉ bind loopback, không mở mọi interface theo mặc định. |
| ENG-OPS-02.3 | Code Analyzer tham gia network nội bộ dùng cho phân tích; GitHub Integration và AI Service được kết nối theo topology Compose hiện hành. |
| ENG-OPS-02.4 | GitHub Integration gọi analyzer bằng service DNS `http://code-analyzer:8000`, không dùng `localhost` trong container. |
| ENG-OPS-02.5 | GitHub Integration chỉ phụ thuộc trạng thái `service_healthy` của analyzer khi Compose khai báo health dependency. |
| ENG-OPS-02.6 | Health check phải gọi đúng endpoint thực tế của analyzer. Kiểm tra runtime cần xác nhận endpoint được cấu hình và trả success. |
| ENG-OPS-02.7 | Analyzer nhận request theo contract `POST /api/v1/analyze-repo` với `scope`, `target`, `files[]`; mỗi file có `path`, `language`, `content`. |
| ENG-OPS-02.8 | Không đưa token GitHub, internal service secret hoặc thông tin xác thực vào request analyzer. |
| ENG-OPS-02.9 | Validation phải kiểm tra cả Compose syntax, image build và khả năng gọi analyzer từ container GitHub Integration; không chỉ kiểm tra service container đã tồn tại. |

## 3. Cấu hình runtime

Các giá trị cần đối chiếu với `compose.yaml` hiện tại trước khi thay đổi:

| Hạng mục | Giá trị/contract |
|---|---|
| Service | `code-analyzer` |
| Container port | `8000` |
| Internal base URL | `http://code-analyzer:8000` |
| API | `POST /api/v1/analyze-repo` |
| Request fields | `scope`, `target`, `files` |
| File fields | `path`, `language`, `content` |

## 4. Lệnh kiểm tra local

Chạy từ thư mục gốc repository:

```bash
# Validate Compose (không khởi động/dừng container)
docker compose -f compose.yaml config --quiet

# Build service analyzer
docker compose -f compose.yaml build code-analyzer

# Kiểm tra trạng thái stack hiện có
docker compose -f compose.yaml ps

# Kiểm tra endpoint từ host nếu port được publish
curl -fsS http://localhost:8000/openapi.json

# Kiểm tra giao tiếp nội bộ từ container GitHub Integration
docker compose -f compose.yaml exec github-integration curl -fsS http://code-analyzer:8000/openapi.json
```

Không dùng `docker compose down -v` trong quy trình kiểm tra thông thường vì lệnh đó xóa database volumes.

## 5. Tiêu chí chấp nhận

- **AC-OPS-02.1:** Compose config hợp lệ và image analyzer build thành công.
- **AC-OPS-02.2:** Analyzer chuyển sang healthy theo health check đã cấu hình.
- **AC-OPS-02.3:** GitHub Integration resolve được `code-analyzer` qua internal network và gọi được endpoint.
- **AC-OPS-02.4:** Request analyzer tuân thủ đúng schema `scope/target/files`; không đổi `target` thành `repo_name`.
- **AC-OPS-02.5:** Lỗi build, health check hoặc kết nối analyzer làm validation thất bại rõ ràng.
- **AC-OPS-02.6:** Kiểm tra không xóa database volumes hoặc dữ liệu local.
