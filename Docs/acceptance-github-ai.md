# Nghiệm thu GitHub và AI trên môi trường thử nghiệm

Trạng thái **chưa chạy UAT**. Ghi phiên bản triển khai, thời gian UTC và bằng chứng theo từng ca. Chỉ sử dụng repo thử đã được chỉ định, phiên bản ứng dụng cô lập và volume mới dành riêng cho thử nghiệm.

## Điều kiện chạy

- Repo thử với nhánh mặc định dành cho thử nghiệm và một repo thứ hai làm đối chứng. Commit-back chỉ hỗ trợ bản sửa đổi phát sinh từ push lên nhánh mặc định. GitHub App được cài trên các repo được phép, đăng ký sự kiện Push và Pull request. Cấu hình webhook HTTPS trỏ tới `/api/github/webhook` của môi trường thử và đặt `GITHUB_WEBHOOK_SECRET` qua nơi lưu secret.
- Tài khoản Developer, Staff và Manager ở workspace A. Tài khoản với từng vai trò tương đương ở workspace B, không có quyền ở A. Cấp kết nối GitHub đọc repo cho Developer và quyền ghi Contents lên nhánh thử cho Manager. Chuẩn bị một kết nối chỉ đọc để kiểm ca từ chối ghi.
- OAuth đăng nhập cho bản thử nghiệm, khóa AI hoạt động (`ANTHROPIC_API_KEY`), dữ liệu mẫu có thay đổi mã kiểm chứng được và một tài liệu đã publish để thử tạo bản sửa đổi. Giữ thông tin xác thực ngoài kết quả kiểm thử.

## Kịch bản

| Ca | Thao tác và tiêu chí đạt | Bằng chứng lưu |
| --- | --- | --- |
| 1 | Developer kết nối và đồng bộ repo thử. Mở PR thay đổi một hành vi có thể kiểm chứng, rồi push commit tiếp theo. Đối chiếu webhook Push và Pull request với hoạt động repo, SHA HEAD và kết quả phân tích. | Delivery ID, số PR, SHA, thời gian nhận và ID phân tích. |
| 2 | Tạo tài liệu hoặc bản sửa đổi từ commit đã phân tích. Xác nhận có lần gọi LLM thật và tài liệu mô tả đúng thay đổi. Mở evidence và đối chiếu đường dẫn, dòng và nội dung với đúng SHA nguồn. | Job ID, chế độ AI, ID tài liệu, số phiên bản và evidence đã lọc dữ liệu nhạy cảm. |
| 3 | Developer xem trước, chỉnh bản nháp và submit đúng phiên bản. Staff claim, kiểm bằng chứng và yêu cầu chỉnh sửa. Developer gửi lại. Staff xác nhận đạt và chuyển đúng phiên bản cho Manager. | Trạng thái và audit theo từng bước, actor và số phiên bản. |
| 4 | Manager approve phiên bản Staff đã duyệt. Kiểm tra bản publish có nội dung đã duyệt và bản nháp vẫn tách biệt. Thực hiện thêm một push trên nhánh mặc định của repo thử để tạo bản sửa đổi, rồi gửi lại qua các bước review và approve. Manager đã duyệt thực hiện commit-back khi HEAD vẫn là SHA nguồn. Lặp lại thao tác để kiểm tra chỉ có một lần ghi. | Audit APPROVED, phiên bản publish, SHA commit-back và diff trên GitHub. |
| 5 | Gửi webhook thiếu hoặc sai chữ ký, sau đó redeliver cùng delivery ID hợp lệ. Request sai bị từ chối. Redelivery không tạo bản ghi hoặc job trùng. | HTTP status, delivery ID, số job và bản ghi trước/sau. |
| 6 | Thử approve trước khi Staff pass, approve phiên bản cũ sau khi tài liệu đổi và rollback về phiên bản hiện tại. Thử commit-back khi chưa approve, khi kết nối GitHub chỉ đọc hoặc khi HEAD đã tiến sau lúc approve. Các thao tác bị từ chối và không đổi nội dung đã publish, audit nghiệp vụ hoặc HEAD nhánh thử. | HTTP status, phiên bản, audit, HEAD trước/sau. |
| 7 | Dùng tài khoản B và ID đã biết của A để thử đọc workflow, tài liệu, evidence, history, versions và PR/commit. Thử claim, approve, rollback và commit-back dưới vai trò tương ứng. API từ chối và danh sách ở B không chứa dữ liệu A. Lặp lại với thành viên cùng workspace nhưng sai vai trò. | Vai trò và workspace, HTTP status, ảnh UI và đối chiếu dữ liệu trước/sau. |
| 8 | Manager thử rollback từ phiên bản đã publish về phiên bản cũ hợp lệ. Kiểm tra tạo phiên bản mới, audit ghi nguồn và lý do, chuyển lại Staff review và giữ nguyên bản publish cho đến khi duyệt lại. | Diff phiên bản, audit rollback, bản đang publish và trạng thái review. |

Nếu bằng chứng ở bất kỳ ca nào thiếu, ghi **chưa xác minh** kèm điều kiện còn thiếu. Kết quả fixture, webhook ping và chế độ AI offline được ghi theo đúng loại kiểm thử.

## Đo hiệu năng

Chốt ngưỡng từ đúng bản đề cương trước khi kết luận. Trên bản triển khai thử, ghi commit, kích cỡ repo, máy chạy, số worker, cấu hình LLM, trạng thái cache và dữ liệu mẫu. Đo riêng thời gian nhận webhook, thời gian chờ hàng đợi, xử lý PR và tổng thời gian đến khi tài liệu sẵn sàng. Chạy lặp với một PR và 20 PR đồng thời, kiểm tra tỷ lệ lỗi và so mức suy giảm với tiêu chí đã thống nhất. Với API thường dùng, ghi p50, p95, p99 và giá trị lớn nhất sau warm-up với tải đã thống nhất. Đo availability trên cửa sổ có quan trắc đã định nghĩa, độc lập với bài đo tải ngắn.

Bản đối chiếu tạm `Project_CNPM.docx` trên OneDrive ghi ba ngưỡng là ít nhất 20 PR đồng thời, API thông thường tối đa 2 giây dưới tải bình thường và availability ít nhất 99,5%. Cần kiểm tra lại với `Project_CNPM(4).docx` và định nghĩa tải bình thường, mức suy giảm chấp nhận được và cửa sổ quan trắc trước khi chấm.
