# FR-KB-04 Tìm kiếm tài liệu và thực thể mã nguồn trong Knowledge Base

| Mục | Nội dung |
|---|---|
| Epic Jira | LD-11 Knowledge Base |
| Task Jira | LD-205 [Documentation Search] Implement Documentation Search |
| Task đã làm | LD-206, LD-207, LD-208, LD-209, LD-210 |
| Người thực hiện | Khôi Nguyễn Hữu Đăng |
| Thành phần | GitHub Integration Service (API tìm kiếm trong repository) và Frontend LivingDocs Web (trang Documentation Search) |
| Tác nhân | Người dùng LivingDocs (tìm kiếm tài liệu và mã nguồn), GitHub Integration Service (dữ liệu đã phân tích của repository) |

## 1. Mô tả

Hệ thống cho phép người dùng tìm kiếm trong tài liệu và các thực thể mã nguồn (class, hàm, endpoint) của một repository thuộc workspace của mình. Kết quả gồm cả tài liệu liên quan và thực thể mã liên kết, mỗi kết quả có đường dẫn tới file nguồn để người dùng mở trực tiếp trên GitHub.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-KB-04.1 | (LD-206) Tìm kiếm tài liệu của một repository theo từ khóa người dùng nhập. |
| FR-KB-04.2 | (LD-207) Tìm kiếm cả các thực thể mã nguồn đã được phân tích của repository (class, hàm, endpoint) bằng cùng một từ khóa. |
| FR-KB-04.3 | (LD-208) Hiển thị kết quả gồm loại kết quả (Documentation hoặc Code entity), tiêu đề, tóm tắt hoặc đoạn mã, repository, ngôn ngữ, và số lượng kết quả tìm thấy. |
| FR-KB-04.4 | (LD-209) Hiển thị đường dẫn file và số dòng của thực thể mã liên kết, kèm liên kết "View source" mở mã nguồn trên GitHub. |
| FR-KB-04.5 | (LD-206) Sắp xếp kết quả theo mức độ phù hợp (điểm), giảm dần, và giới hạn tối đa 50 kết quả. |
| FR-KB-04.6 | (LD-206) Cho phép chọn repository để tìm kiếm trong số các repository của workspace; đổi repository thì xóa kết quả cũ. |
| FR-KB-04.7 | (LD-208) Hiển thị trạng thái đang tải repository, đang tìm kiếm, không có kết quả và lỗi tìm kiếm. |

## 3. Giao diện

| Màn hình / thành phần | Nội dung hiển thị | Yêu cầu |
|---|---|---|
| Biểu mẫu tìm kiếm | Danh sách chọn repository, ô nhập từ khóa (tối đa 200 ký tự), nút Search | FR-KB-04.1 – 04.2, 04.6 |
| Danh sách kết quả | Tổng số kết quả; mỗi kết quả có nhãn loại, tiêu đề, tóm tắt hoặc đoạn mã, repository và ngôn ngữ | FR-KB-04.3, 04.5 |
| Điều hướng tới mã nguồn | Đường dẫn file kèm số dòng và liên kết "View source" mở trong tab mới | FR-KB-04.4 |
| Trạng thái | Đang tải, đang tìm kiếm, không có kết quả, lỗi | FR-KB-04.7 |

Frontend gọi `GET /api/repositories/{id}/documentation/search?q=...` của GitHub Integration Service qua Backend (BFF). Chi tiết endpoint theo hợp đồng API của service đó.

## 4. Luồng chính

1. Người dùng mở trang Documentation Search; giao diện tải danh sách repository của workspace.
2. Người dùng chọn repository và nhập từ khóa, rồi bấm Search.
3. Hệ thống tách từ khóa, tính điểm phù hợp cho từng tài liệu và thực thể mã của repository, sắp xếp giảm dần và trả tối đa 50 kết quả.
4. Giao diện hiển thị số kết quả và từng kết quả; người dùng bấm "View source" để mở mã nguồn tương ứng trên GitHub.

## 5. Luồng lỗi

| Trường hợp | Kết quả hiển thị |
|---|---|
| Từ khóa trống | Thông báo "Enter a search term.", không gửi yêu cầu |
| Từ khóa dài hơn 200 ký tự hoặc chứa ký tự điều khiển | Thông báo giới hạn độ dài; API trả lỗi 400 |
| Workspace chưa có repository | Thông báo thêm repository vào workspace trước khi tìm kiếm |
| Không tải được danh sách repository | Thông báo lỗi tải repository |
| Không có kết quả phù hợp | Trạng thái "No results found" và gợi ý đổi từ khóa hoặc đổi repository |
| Tìm kiếm thất bại (lỗi API) | Hiển thị thông báo lỗi trả về từ backend, không hiển thị kết quả cũ |

## 6. Quy tắc nghiệp vụ

- Chỉ tìm trong repository thuộc workspace của người dùng; backend kiểm tra quyền sở hữu repository trước khi trả kết quả.
- Kết quả của một repository không lẫn sang repository khác.
- Thứ tự kết quả theo điểm phù hợp giảm dần; số kết quả trả về không quá 50, tổng số kết quả tìm thấy vẫn được báo.
- Frontend không tự tính điểm hay tự lọc; toàn bộ việc tìm kiếm do GitHub Integration Service thực hiện.

## 7. Tiêu chí chấp nhận

- **AC-KB-04.1:** Nhập từ khóa hợp lệ và bấm Search thì hiển thị tài liệu và thực thể mã liên quan của repository đã chọn.
- **AC-KB-04.2:** Mỗi kết quả mã nguồn hiển thị đường dẫn file, số dòng và liên kết mở mã trên GitHub.
- **AC-KB-04.3:** Từ khóa trống, từ khóa quá dài, workspace chưa có repository, không có kết quả và lỗi API đều có thông báo tương ứng.
- **AC-KB-04.4:** Chọn repository khác thì kết quả của repository trước không còn hiển thị.
- **AC-KB-04.5:** Trạng thái đang tải và đang tìm kiếm hiển thị trong khi chờ phản hồi.

## 8. Kiểm thử

Jira có subtask kiểm thử LD-210 "Test Documentation Search". Kiểm thử tự động gồm `DocumentationSearchServiceTest`, `DocumentationSearchControllerTest` và `DocumentationSearchHttpIntegrationTest` (GitHub Integration Service) và các kịch bản giao diện trong `tests/test_frontend.py` (kết quả và điều hướng mã nguồn, từ khóa trống, tách biệt kết quả theo repository, trạng thái đang tải và không có kết quả, hiển thị lỗi API). Jira ghi nhận LD-205 hoàn thành ngày 10/11/2026; mã nguồn được merge qua pull request #89 trên GitHub.
