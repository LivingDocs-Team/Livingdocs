# Functional Requirements — Tasks của Huy (Auth, AST Analysis, AI Generation, Evidence & Submission, Documentation Drift, Confidence Scoring)

Các chức năng do Huy thực hiện từ Sprint 1 đến Sprint 7, mỗi chức năng được lưu thành một file riêng:

| File | Chức năng | Story / Task Jira |
|---|---|---|
| [FR-AUTH-01](FR01.md) | Xác thực GitHub OAuth và kết nối Repository | LD-43, LD-53 (LD-20, LD-38, LD-63, LD-292) |
| [FR-AST-02](FR02.md) | Phân tích cây cú pháp trừu tượng (AST) và trích xuất Entity | LD-328 (LD-85, LD-395) |
| [FR-AI-03](FR03.md) | Sinh tài liệu kỹ thuật từ AST và xem trước thời gian thực | LD-340, LD-105 (LD-90, LD-96, LD-101) |
| [FR-EVI-04](FR04.md) | Trích xuất bằng chứng mã nguồn (`GroundingEvidence`) và gửi phê duyệt | LD-106 (LD-107, LD-109, LD-110, LD-111) |
| [FR-AI-05](FR05.md) | Phát hiện tài liệu lỗi thời (documentation drift) từ một Pull Request | LD-145 (LD-146, LD-147, LD-148, LD-149, LD-150) |
| [FR-AI-06](FR06.md) | Phân loại drift: Referential / Signature / Semantic, `kind`, `breaking` | LD-151 (LD-152, LD-153, LD-154, LD-155) |
| [FR-AI-07](FR07.md) | Đánh giá mức độ nghiêm trọng của drift, hiển thị lý do và bằng chứng | LD-156 (LD-157, LD-158, LD-159, LD-160) |
| [FR-AI-08](FR08.md) | Phân tích drift dựa trên AI: so sánh mã nguồn – tài liệu, AI review, xử lý finding | LD-346 (LD-347, LD-348, LD-349, LD-350, LD-351) |
| [FR-AI-09](FR09.md) | Chuẩn hoá điểm độ tin cậy (confidence) của tài liệu AI sinh và drift finding | LD-356 |
| [FR-AI-10](FR10.md) | Sửa lỗi lưu trữ evidence và submission (PR #108) | LD-402 |

Mỗi file gồm: mô tả, danh sách yêu cầu (FR-xx-yy.z), API, dữ liệu, luồng chính, luồng lỗi, quy tắc nghiệp vụ, tiêu chí chấp nhận và test liên quan. Các con số (trọng số, giới hạn, ngưỡng) trong file là giá trị đang dùng trong code, để có thể dựng lại đúng hành vi.

## Thứ tự sử dụng

    Đăng nhập GitHub OAuth (FR-AUTH-01) → Đồng bộ Repository & Webhook (FR-AUTH-01)
      → Phân tích mã nguồn AST Trích xuất Entities (FR-AST-02)
      → Chọn Template & Sinh tài liệu AI + Xem trước Markdown (FR-AI-03)
        (độ tin cậy của tài liệu sinh ra: FR-AI-09)
      → Trích xuất Bằng chứng Code (`GroundingEvidence`) & Kiểm tra Tiến độ (FR-EVI-04)
      → Xác minh CI/CD Pipeline → Khóa bản thảo & Gửi Phê duyệt (`submitted`) (FR-EVI-04)
        (evidence của bản sửa / rollback và lưu trữ submission: FR-AI-10)
      → Khi có Pull Request mới: phát hiện tài liệu lỗi thời (FR-AI-05)
      → Phân loại drift (FR-AI-06) → Đánh giá mức độ nghiêm trọng (FR-AI-07)
      → AI review, xem bằng chứng & xử lý finding: Acknowledge / Resolve / Dismiss (FR-AI-08)
        (độ tin cậy của drift finding: FR-AI-09)

## Quy ước chung

- Service viết bằng Python 3.10+, FastAPI, Pydantic v2; chạy ở cổng 8001 (`uvicorn main:app --reload --port 8001` trong thư mục `ai-service/`). Mã nguồn nằm tại thư mục `ai-service/`.
- Frontend không gọi trực tiếp: Frontend (Web Client) → Backend (BFF / Gateway) → Dịch vụ AI Service / GitHub Integration Service. Backend BFF chỉ chuyển tiếp `/api/repositories/**`, `/api/documentation/**` và `/api/document-workflows/**`.
- Định dạng bằng chứng mã nguồn (`GroundingEvidence`) tuân thủ khai báo Pydantic Schema: bao gồm `file_path`, `start_line`, `end_line`, `code_snippet` và `commit_hash`.
- Bằng chứng của drift finding dùng mã: `X1` code diff, `D1..` dòng tài liệu, `C1` commit / Pull Request, `T1..` mã Jira. AI chỉ được trích các mã có trong chính finding đó.
- Mức độ nghiêm trọng của drift: Low < Medium < High < Critical, chỉ do bảng luật `RULES` (`app/drift_severity.py`) quyết định; AI không thay đổi mức độ.
- Độ tin cậy luôn trong khoảng 0–1, làm tròn 2 chữ số; mức: high ≥ 0.75, medium ≥ 0.50, low < 0.50.
- Lỗi của AI Service theo chuẩn FastAPI: `{"detail": "..."}` (404/400/409) hoặc lỗi định dạng validation `{"detail": [{"loc": [...], "msg": "..."}]}` (422). Lỗi của GitHub Integration Service: `{"status", "code", "message", "timestamp"}`.
- CI/CD Workflow chạy tự động tại `.github/workflows/ci.yml`, thực thi các kịch bản unit test thực tế bằng `pytest` (tuyệt đối không hardcode gán `exit 0` hoặc gán cứng `TRUE`).

## Không thuộc yêu cầu chức năng

Kiểm thử và cấu hình hạ tầng CI/CD không phải chức năng giao diện người dùng nên không tạo file FR độc lập:

- **LD-364 / LD-376 / LD-391:** Thiết lập và kiểm thử đường ống tích hợp liên tục GitHub Actions CI/CD Pipeline (job `test-ai-service` chạy `pytest tests/ -v`).
- **LD-105-Tests / LD-390:** Kịch bản kiểm thử tích hợp giao diện Preview và Unit Test Backend cho các endpoints `GroundingEvidence` & `Submission` (tệp `tests/test_evidence_submission.py`).
- **LD-150 / LD-155 / LD-160:** Bộ test phát hiện, phân loại và đánh giá mức độ drift (`ai-service/tests/test_drift*.py`, `tests/test_frontend_drift.py`); nội dung kiểm thử đã ghi trong mục 8 của FR-AI-05, FR-AI-06, FR-AI-07.
