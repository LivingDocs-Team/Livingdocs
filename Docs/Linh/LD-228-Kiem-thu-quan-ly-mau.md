# LD-228 — Kiểm thử quản lý mẫu tài liệu (Documentation Template Management)

Kiểm thử toàn bộ chức năng mẫu tài liệu của LD-223:

| Task | Nội dung | Yêu cầu (FR5) |
|---|---|---|
| LD-224 | Liệt kê mẫu có sẵn | FR-AI-05.4 |
| LD-225 | Tạo và sửa mẫu | FR-AI-05.11 – 05.13 |
| LD-226 | Cấu trúc mẫu (các mục và thứ tự) | FR-AI-05.1 – 05.2, 05.7 |
| LD-227 | Phiên bản mẫu | FR-AI-05.15 – 05.20 |

## Bộ test

| File | Phạm vi | Số test | Chạy ở đâu |
|---|---|---|---|
| `ai-service/tests/test_templates.py` | LD-97 – LD-100: xem, kiểm tra hợp lệ, trùng tên, sửa/xoá, mẫu có sẵn chỉ đọc, lưu file, tài liệu đúng mục | 24 | `cd ai-service && python -m pytest -q` (đã chạy: đạt) |
| `ai-service/tests/test_template_versions.py` | LD-227: phiên bản, khôi phục, sinh theo phiên bản cũ, lưu file | 11 | như trên (đã chạy: đạt) |
| `ai-service/tests/test_template_management.py` | LD-228: các test case TM-01 … TM-08 bên dưới | 21 | như trên (đã chạy: đạt) |
| `DocumentationTemplateServiceTest`, `DocumentationTemplateControllerTest` | GitHub Integration chuyển tiếp mẫu và phiên bản, ánh xạ lỗi | 9 + 3 | CI job "GitHub Integration Service Test" |
| `ApiRoutePermissionsTest` | Quyền của từng role với các route mẫu (gồm 3 route phiên bản) | theo bảng route | CI job "Backend Build and Test" |
| `tests/test_frontend_templates.py` | Giao diện chọn và quản lý mẫu (Playwright) | 3 | CI job "Frontend E2E Test" |

Kết quả chạy trên máy phát triển: 56 test mẫu của AI Service đạt; toàn bộ AI Service 494 đạt, 23 bỏ qua (test tích hợp cần API key). Test Java và Playwright chạy trên CI.

## Test case LD-228 (`test_template_management.py`)

| ID | Task | Nội dung kiểm tra | Kết quả mong đợi | Kết quả |
|---|---|---|---|---|
| TM-01 | LD-224 | Danh sách có đủ trường cho màn hình | Mỗi mẫu có `id`, `name`, `description`, `instructions`, `sections`, `built_in`, `version`, `created_at`, `updated_at`; 3 mẫu có sẵn đứng đầu | Đạt |
| TM-02 | LD-225 | Giới hạn độ dài chính xác | `name` 80 / `description` 300 / `instructions` 4000 ký tự → `201`; thêm 1 ký tự → `422` nêu tên trường | Đạt (3 bộ dữ liệu) |
| TM-02b | LD-225 | Sửa được kiểm tra như tạo | Mục lạ → `422`; khoảng trắng đầu/cuối bị bỏ; mẫu không có → `404` | Đạt |
| TM-03 | LD-226 | Mọi thứ tự, mọi tập mục | Tài liệu có đúng các tiêu đề `##` theo đúng thứ tự của mẫu (1, 2 và 4 mục, nhiều hoán vị) | Đạt (9 bộ dữ liệu) |
| TM-04 | LD-227 | Vòng đời: tạo → sinh → sửa → sinh → khôi phục → sinh | Job ghi phiên bản 1, 2, 3; tài liệu lần 1 và 3 giống nhau; lịch sử `(3, restored_from 1), (2), (1)`; vẫn sinh được theo phiên bản 2 | Đạt |
| TM-05 | LD-227 | 20 lần sửa cùng lúc (20 luồng) | 21 phiên bản liên tục, không trùng, không thiếu; đọc lại file vẫn là 21 | Đạt |
| TM-06 | LD-227 | Khôi phục sau khi khởi động lại; tên vẫn duy nhất | Khôi phục được sau restart; khôi phục tên đã bị mẫu khác dùng → lỗi trùng tên; lịch sử còn đủ | Đạt |
| TM-07 | LD-227 | Job đang chờ khi mẫu bị sửa | Job dùng phiên bản lúc tạo (1) và các mục cũ | Đạt |
| TM-08 | LD-224/225 | Mẫu có sẵn không đổi được bằng bất kỳ cách nào | `PUT`, `DELETE`, khôi phục → `403`; mẫu và lịch sử (1 phiên bản) không đổi | Đạt (3 mẫu) |

## Lỗi tìm thấy

Không tìm thấy lỗi mới trong các test case trên. Phần phiên bản (LD-227) được viết cùng lúc với test của nó.

## Giới hạn

- Chưa có giao diện xem và khôi phục phiên bản trên web. API đã có qua Backend (`/api/documentation/templates/{id}/versions…`). Màn hình Templates thuộc Technical Lead theo ma trận quyền của nhóm, nên thêm giao diện cần nhóm thống nhất.
- Sinh tài liệu theo phiên bản cũ (`template_version`) hiện chỉ có ở AI Service; GitHub Integration chưa chuyển tiếp trường này khi tạo job.
