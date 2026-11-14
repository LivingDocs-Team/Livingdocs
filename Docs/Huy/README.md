# Functional Requirements — Tasks của Huy (Auth, AST Analysis, AI Generation, Evidence & Submission)

Các chức năng do Huy thực hiện từ Sprint 1 đến Sprint 4, mỗi chức năng được lưu thành một file riêng:

| File | Chức năng | Story / Task Jira |
|---|---|---|
| [FR-AUTH-01](FR01.md) | Xác thực GitHub OAuth và kết nối Repository | LD-43, LD-53 (LD-20, LD-38, LD-63, LD-292) |
| [FR-AST-02](FR02.md) | Phân tích cây cú pháp trừu tượng (AST) và trích xuất Entity | LD-328 (LD-85, LD-395) |
| [FR-AI-03](FR03.md) | Sinh tài liệu kỹ thuật từ AST và xem trước thời gian thực | LD-340, LD-105 (LD-90, LD-96, LD-101) |
| [FR-EVI-04](FR04.md) | Trích xuất bằng chứng mã nguồn (`GroundingEvidence`) và gửi phê duyệt | LD-106 (LD-107, LD-109, LD-110, LD-111) |

Mỗi file gồm: mô tả, danh sách yêu cầu (FR-xx-yy.z), API, dữ liệu, luồng chính, luồng lỗi, quy tắc nghiệp vụ, tiêu chí chấp nhận và test liên quan. Các con số (trọng số, giới hạn, ngưỡng) trong file là giá trị đang dùng trong code, để có thể dựng lại đúng hành vi.

## Thứ tự sử dụng

    Đăng nhập GitHub OAuth (FR-AUTH-01) → Đồng bộ Repository & Webhook (FR-AUTH-01)
      → Phân tích mã nguồn AST Trích xuất Entities (FR-AST-02)
      → Chọn Template & Sinh tài liệu AI + Xem trước Markdown (FR-AI-03)
      → Trích xuất Bằng chứng Code (`GroundingEvidence`) & Kiểm tra Tiến độ (FR-EVI-04)
      → Xác minh CI/CD Pipeline → Khóa bản thảo & Gửi Phê duyệt (`submitted`) (FR-EVI-04)

## Quy ước chung

- Service viết bằng Python 3.10+, FastAPI, Pydantic v2; chạy ở cổng 8001 (`uvicorn app.main:app --reload --port 8001`). Mã nguồn nằm tại thư mục `ai-service/`.
- Frontend không gọi trực tiếp: Frontend (Web Client) → Backend (BFF / Gateway) → Dịch vụ AI Service / GitHub Integration Service.
- Định dạng bằng chứng mã nguồn (`GroundingEvidence`) tuân thủ khai báo Pydantic Schema: bao gồm `file_path`, `start_line`, `end_line`, `code_snippet` và `commit_hash`.
- Lỗi của AI Service theo chuẩn FastAPI: `{"detail": "..."}` (404/400/409) hoặc lỗi định dạng validation `{"detail": [{"loc": [...], "msg": "..."}]}` (422).
- CI/CD Workflow chạy tự động tại `.github/workflows/ci.yml`, thực thi các kịch bản unit test thực tế bằng `pytest` (tuyệt đối không hardcode gán `exit 0` hoặc gán cứng `TRUE`).

## Không thuộc yêu cầu chức năng

Kiểm thử và cấu hình hạ tầng CI/CD không phải chức năng giao diện người dùng nên không tạo file FR độc lập:

- **LD-364 / LD-376 / LD-391:** Thiết lập và kiểm thử đường ống tích hợp liên tục GitHub Actions CI/CD Pipeline (job `test-ai-service` chạy `pytest tests/ -v`).
- **LD-105-Tests / LD-390:** Kịch bản kiểm thử tích hợp giao diện Preview và Unit Test Backend cho các endpoints `GroundingEvidence` & `Submission` (tệp `ai-service/tests/test_evidence_submission.py`).



