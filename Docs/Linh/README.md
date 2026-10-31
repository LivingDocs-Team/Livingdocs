# Functional Requirements — Tasks của Linh (AI Service, sinh tài liệu)

Các chức năng do Nguyễn Thị Phương Linh thực hiện, mỗi chức năng một file:

| File | Chức năng | Story / task Jira |
|---|---|---|
| [FR-AI-01](FR1.md) | Tạo và theo dõi job sinh tài liệu | LD-90 (LD-91 – LD-95) |
| [FR-AI-02](FR2.md) | Sinh tài liệu từ kết quả phân tích code | LD-340 |
| [FR-AI-03](FR3.md) | Truy xuất mã liên quan và tài liệu có sẵn làm ngữ cảnh | LD-340 |
| [FR-AI-04](FR4.md) | Bằng chứng xác thực và điểm độ tin cậy | LD-340 |
| [FR-AI-05](FR5.md) | Mẫu tài liệu (documentation templates) | LD-96 (LD-97 – LD-100) |

Mỗi file gồm: mô tả, danh sách yêu cầu (FR-AI-xx.y), API, dữ liệu, luồng chính, luồng lỗi, quy tắc nghiệp vụ, tiêu chí chấp nhận và test liên quan. Các con số (trọng số, giới hạn, ngưỡng) trong file là giá trị đang dùng trong code, để có thể dựng lại đúng hành vi.

## Thứ tự sử dụng

    Đồng bộ repo (FR-GH-03) → dữ liệu cho phân tích (FR-GH-04) → Code Analyzer (LD-328)
      → FR-AI-01 tạo job → FR-AI-05 chọn mẫu → FR-AI-03 truy xuất ngữ cảnh
      → FR-AI-02 sinh tài liệu từng file → FR-AI-04 bằng chứng + độ tin cậy → kết quả Markdown + báo cáo

## Quy ước chung

- Service viết bằng Python 3.12, FastAPI, pydantic v2; chạy ở cổng 8001 (`uvicorn main:app --port 8001`). Mã nguồn ở `ai-service/`.
- Frontend không gọi trực tiếp: Backend (BFF) → GitHub Integration Service (`/api/repositories/{id}/documentation/generate`, `/api/documentation/...`) → AI Service. Xem `services/github-integration-service/docs/documentation-generation-contract.md`.
- Định dạng dữ liệu nhận từ Code Analyzer: `ai-service/CONTRACT.md`.
- Lỗi của AI Service theo FastAPI: `{"detail": "..."}` (404/403/409) hoặc `{"detail": [{"loc": [...], "msg": "..."}]}` (422).
- Không có `ANTHROPIC_API_KEY` thì service chạy chế độ **offline**: vẫn sinh tài liệu từ dữ liệu phân tích, không gọi AI. Không bao giờ commit API key.

## Không thuộc yêu cầu chức năng

Kiểm thử và CI không phải chức năng của sản phẩm nên không có file FR riêng:

- LD-390: kiểm thử tích hợp AI Service (`ai-service/tests/integration/`, job CI `ai-service-integration`), danh sách test case ở `ai-service/tests/integration/README.md`.
- Job CI `ai-service-test` chạy toàn bộ `pytest` của `ai-service/`.
