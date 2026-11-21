# FR-LD-177 Ghi nhận và hiển thị lịch sử thay đổi tài liệu

| Mục | Nội dung |
|---|---|
| **Story Jira** | LD-177 – Implement Documentation Change Log |
| **Task liên quan** | Record Documentation Changes; Record Change Timestamp and Trigger; Record Change User and Role; Display Documentation Change Timeline; Test Documentation Change Log |
| **Thành phần** | AI Service (`app/versions.py`, `app/version_models.py`, `main.py`); GitHub Integration Service (migration `V10__documentation_change_log.sql`); Frontend (`change-log-timeline/ChangeLogTimeline.tsx`) |
| **Tác nhân** | Người dùng tạo/chỉnh sửa/xét duyệt tài liệu; hệ thống sinh tài liệu và các luồng tự động liên quan |
| **Phạm vi** | Ghi nhận sự kiện thay đổi của tài liệu, lưu thông tin người thực hiện, vai trò, nguồn kích hoạt, trạng thái và thời điểm; cung cấp lịch sử để hiển thị theo dòng thời gian. |

## 1. Mô tả

LD-177 bổ sung khả năng theo dõi lịch sử thay đổi của tài liệu trong LivingDocs. Mỗi sự kiện phát sinh trong vòng đời tài liệu được ghi nhận cùng phiên bản liên quan, hành động, người thực hiện, vai trò, nguồn kích hoạt, trạng thái, ghi chú và thời điểm xảy ra.

Lịch sử được cung cấp qua API để giao diện Documentation hiển thị theo dạng timeline. Người xem có thể nhận biết ai đã thực hiện thay đổi, thay đổi thuộc loại nào, được kích hoạt từ đâu, trạng thái tài liệu tại thời điểm đó và thời gian xảy ra.

Trong phần triển khai hiện có:
- AI Service quản lý audit trail theo từng document và cung cấp API đọc lịch sử.
- `HistoryEvent` là cấu trúc dữ liệu của một sự kiện lịch sử.
- Frontend có component `ChangeLogTimeline` gọi API `/api/documentation/{documentId}/change-log` và hiển thị các entry theo thứ tự API trả về.
- GitHub Integration Service có migration tạo bảng `documentation_change_logs` với các trường phục vụ lưu change log.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| **FR-LD-177.1** | **Ghi nhận thay đổi tài liệu:** Khi tài liệu phát sinh sự kiện trong vòng đời quản lý phiên bản, hệ thống ghi một sự kiện lịch sử gắn với `document_id` và số phiên bản liên quan. Các action được mô hình hóa gồm `created`, `proposed`, `accepted`, `edited`, `dismissed`, `regenerated`, `superseded` và `rolled_back`. |
| **FR-LD-177.2** | **Ghi nhận người thực hiện:** Sự kiện lưu `actor` để nhận diện người hoặc tác nhân thực hiện thay đổi. Giá trị có thể là user ID/tên người dùng; với thao tác hệ thống có thể ghi nhận tác nhân hệ thống. |
| **FR-LD-177.3** | **Ghi nhận vai trò:** Sự kiện lưu `actor_role`. Các vai trò được chú thích trong mô hình gồm `DEVELOPER`, `STAFF`, `MANAGER`, `ADMINISTRATOR`, `SYSTEM`. |
| **FR-LD-177.4** | **Ghi nhận thời điểm:** Mỗi sự kiện có trường `at` kiểu datetime, mặc định lấy thời điểm hiện tại qua hàm `now()`. Migration change log cũng định nghĩa `created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP`. |
| **FR-LD-177.5** | **Ghi nhận nguồn kích hoạt:** Sự kiện lưu `trigger_source`. Các giá trị nguồn được định nghĩa gồm `AI_GENERATION`, `MANUAL_EDIT`, `DRIFT_SUGGESTION`, `PR_WEBHOOK`, `REVIEW_WORKFLOW` và `ROLLBACK`. |
| **FR-LD-177.6** | **Theo dõi trạng thái:** Sự kiện lưu `status` để phản ánh trạng thái phiên bản/tài liệu tại thời điểm ghi nhận. Các trạng thái phiên bản được mô hình hóa gồm `proposed`, `accepted`, `dismissed`, `superseded`. |
| **FR-LD-177.7** | **Lưu thông tin bổ sung:** Sự kiện có thể lưu `note` và `related_version` để giải thích thay đổi hoặc liên kết với phiên bản liên quan. |
| **FR-LD-177.8** | **Truy xuất lịch sử:** Cung cấp API lấy danh sách sự kiện lịch sử theo document. Phần triển khai AI Service có endpoint public và endpoint internal dành cho service tích hợp. |
| **FR-LD-177.9** | **Hiển thị timeline:** Giao diện hiển thị tiêu đề “Lịch sử thay đổi tài liệu”; mỗi entry thể hiện người thực hiện, thời gian, nội dung tóm tắt và loại sự kiện. Khi chưa có sự kiện, hiển thị thông báo chưa có thay đổi. |
| **FR-LD-177.10** | **Xử lý trạng thái tải và lỗi:** Giao diện thể hiện trạng thái đang tải; nếu bị từ chối quyền truy cập hoặc tài liệu không tồn tại thì hiển thị thông báo không có quyền xem lịch sử; các lỗi tải khác hiển thị thông báo không tải được lịch sử. |

## 3. Dữ liệu và mô hình

### 3.1. HistoryEvent

Mô hình `HistoryEvent` trong AI Service có cấu trúc:

| Trường | Kiểu / Giá trị | Ý nghĩa |
|---|---|---|
| `action` | `HistoryAction` | Hành động đã xảy ra. |
| `version` | integer | Số phiên bản liên quan đến sự kiện. |
| `actor` | string hoặc null | Người/tác nhân thực hiện. |
| `actor_role` | string hoặc null | Vai trò của người/tác nhân. |
| `trigger_source` | string hoặc null | Nguồn kích hoạt thay đổi. |
| `status` | string hoặc null | Trạng thái phiên bản tại thời điểm ghi nhận. |
| `note` | string hoặc null | Ghi chú hoặc lý do bổ sung. |
| `related_version` | integer hoặc null | Phiên bản liên quan, nếu có. |
| `at` | datetime | Thời điểm phát sinh; mặc định là `now()`. |

`HistoryEvent.event` là thuộc tính trả về giá trị chuỗi của `action`.

### 3.2. Danh sách action

| Action | Ý nghĩa |
|---|---|
| `created` | Tạo tài liệu/phiên bản đầu tiên. |
| `proposed` | Đề xuất phiên bản mới để chờ xét duyệt. |
| `accepted` | Phiên bản được chấp thuận. |
| `edited` | Tài liệu được chỉnh sửa. |
| `dismissed` | Phiên bản bị từ chối/loại bỏ. |
| `regenerated` | Phiên bản được sinh lại. |
| `superseded` | Phiên bản đề xuất bị thay thế bởi phiên bản mới hơn. |
| `rolled_back` | Thực hiện khôi phục phiên bản. |

### 3.3. Danh sách trigger source

| Trigger source | Ý nghĩa |
|---|---|
| `AI_GENERATION` | Thay đổi được tạo từ luồng AI sinh tài liệu. |
| `MANUAL_EDIT` | Người dùng chỉnh sửa tài liệu thủ công. |
| `DRIFT_SUGGESTION` | Thay đổi xuất phát từ đề xuất xử lý documentation drift. |
| `PR_WEBHOOK` | Thay đổi được kích hoạt từ webhook Pull Request. |
| `REVIEW_WORKFLOW` | Thay đổi phát sinh trong quy trình review. |
| `ROLLBACK` | Thay đổi được kích hoạt bởi thao tác rollback. |

### 3.4. Bảng lưu trữ change log

Migration `V10__documentation_change_log.sql` tạo bảng `documentation_change_logs`:

| Cột | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `id` | `VARCHAR(64)` – Primary Key | Định danh bản ghi. |
| `document_id` | `VARCHAR(64)` – NOT NULL | Tài liệu được thay đổi. |
| `repository_id` | `UUID` | Repository liên quan, nếu có. |
| `version_number` | `INTEGER` | Số phiên bản liên quan. |
| `action` | `VARCHAR(64)` – NOT NULL | Hành động thay đổi. |
| `summary` | `VARCHAR(500)` – NOT NULL | Nội dung tóm tắt thay đổi. |
| `actor_id` | `VARCHAR(128)` | ID người thực hiện. |
| `actor_name` | `VARCHAR(255)` | Tên người thực hiện. |
| `actor_role` | `VARCHAR(64)` – NOT NULL | Vai trò người thực hiện. |
| `trigger_source` | `VARCHAR(64)` – NOT NULL | Nguồn kích hoạt. |
| `status` | `VARCHAR(64)` – NOT NULL | Trạng thái thay đổi. |
| `reference_id` | `VARCHAR(128)` | Mã tham chiếu liên quan, nếu có. |
| `created_at` | `TIMESTAMP WITH TIME ZONE` – NOT NULL | Thời điểm tạo bản ghi, mặc định `CURRENT_TIMESTAMP`. |

Các index được tạo:
- `idx_doc_changelog_doc_created` trên `(document_id, created_at DESC)` để hỗ trợ truy vấn lịch sử theo tài liệu và thời gian.
- `idx_doc_changelog_repo_created` trên `(repository_id, created_at DESC)` để hỗ trợ truy vấn theo repository và thời gian.

## 4. API

### 4.1. AI Service

| Method | Endpoint | Kết quả | Mục đích |
|---|---|---|---|
| **GET** | `/documents/{doc_id}/history` | `200 OK` + `List[HistoryEvent]` | Lấy audit trail của tài liệu. |
| **GET** | `/internal/documents/{doc_id}/history` | `200 OK` + `List[HistoryEvent]` | Endpoint nội bộ để service tích hợp lấy lịch sử tài liệu. |

Endpoint public gọi `documents.history(doc_id)`. Hàm `history` kiểm tra document tồn tại và trả về danh sách sự kiện theo thứ tự cũ trước, mới sau. Endpoint internal cũng gọi cùng hàm lấy lịch sử và được bảo vệ bằng cơ chế xác thực internal service.

### 4.2. Frontend

| Method | Endpoint | Kết quả | Mục đích |
|---|---|---|---|
| **GET** | `/api/documentation/{documentId}/change-log` | JSON array các entry change log | Lấy dữ liệu để hiển thị timeline của tài liệu. |

Component frontend sử dụng các trường dữ liệu:
- `id`: định danh entry, dùng làm key khi render.
- `documentId`: ID tài liệu.
- `eventType`: loại sự kiện.
- `actorName`: tên người thực hiện.
- `summary`: nội dung tóm tắt.
- `occurredAt`: thời điểm xảy ra.

**Lưu ý về hợp đồng API:** Trong mã nguồn được cung cấp, AI Service khai báo route `/documents/{doc_id}/history` và `/internal/documents/{doc_id}/history`, trong khi component frontend gọi đường dẫn BFF `/api/documentation/{documentId}/change-log` với cấu trúc entry đã nêu. Chi tiết mapping giữa BFF, AI Service và bảng `documentation_change_logs` không thể hiện đầy đủ trong các phần mã nguồn đã kiểm tra.

## 5. Luồng chính

1. Một thao tác làm thay đổi vòng đời tài liệu được thực hiện, ví dụ tạo tài liệu từ job sinh tài liệu, đề xuất phiên bản, chỉnh sửa, xét duyệt, từ chối, sinh lại hoặc rollback.
2. Module quản lý phiên bản xác định action, số phiên bản và các thông tin ngữ cảnh của sự kiện.
3. Hệ thống ghi sự kiện vào lịch sử của document với `actor`, `actor_role`, `trigger_source`, `status`, `note`, `related_version` và thời điểm `at` khi các thông tin tương ứng được cung cấp.
4. Khi tạo tài liệu từ job, hệ thống ghi event `created`; vai trò và trigger source được lấy từ tham số truyền vào hoặc dùng giá trị mặc định theo luồng tạo tài liệu.
5. Khi người dùng mở khu vực lịch sử thay đổi, frontend gọi `GET /api/documentation/{documentId}/change-log`.
6. Frontend nhận danh sách entry và hiển thị theo dạng timeline. Mỗi entry hiển thị tên người thực hiện, thời gian, summary và event type.
7. Nếu danh sách rỗng, giao diện hiển thị “Chưa có thay đổi nào.”

## 6. Luồng lỗi

| Trường hợp | Xử lý / Kết quả |
|---|---|
| Document không tồn tại khi gọi API lịch sử AI Service | Trả lỗi `404` theo cơ chế `_not_found` của module quản lý phiên bản. |
| Người dùng không được phép xem lịch sử hoặc API trả `403` | Frontend hiển thị “Bạn không có quyền xem lịch sử thay đổi của tài liệu này.” |
| Document không tồn tại ở endpoint BFF hoặc API trả `404` | Frontend hiển thị cùng thông báo không có quyền xem lịch sử. |
| API trả lỗi khác `403`/`404` | Frontend hiển thị “Không tải được lịch sử thay đổi.” |
| Đang chờ API phản hồi | Frontend hiển thị “Đang tải…” và bật trạng thái loading. |
| Không có entry lịch sử | Hiển thị “Chưa có thay đổi nào.” |

## 7. Quy tắc nghiệp vụ

- Lịch sử được quản lý theo từng `document_id`; mỗi event liên kết với một `version`.
- Các sự kiện trong audit trail của AI Service được trả về theo thứ tự thời gian tăng dần (oldest first).
- `actor_role` và `trigger_source` có thể được truyền vào từ luồng gọi; một số luồng có giá trị mặc định. Ví dụ tạo tài liệu từ job dùng trigger mặc định `AI_GENERATION`; vai trò mặc định phụ thuộc việc tài liệu có owner hay không và actor có được cung cấp hay không.
- Thời điểm của event được khởi tạo tự động nếu caller không chỉ định.
- Ghi chú và phiên bản liên quan là thông tin tùy chọn.
- Frontend định dạng thời gian bằng `toLocaleString()` theo locale của trình duyệt.
- Migration change log có index theo document/time và repository/time để phục vụ truy vấn lịch sử.
- Phần mã nguồn hiện có thể hiện cả mô hình audit trail trong AI Service và schema bảng change log trong GitHub Integration Service. Không suy diễn rằng hai cơ chế đã được đồng bộ hoàn toàn khi chưa có phần triển khai mapping tương ứng.

## 8. Tiêu chí chấp nhận

- **AC-LD-177.1:** Khi tài liệu được tạo từ job sinh tài liệu, lịch sử có event `created` gắn với document và version đầu tiên.
- **AC-LD-177.2:** Event lưu được actor và actor role khi các thông tin này được cung cấp; giá trị mặc định của luồng tạo tài liệu được áp dụng khi thiếu thông tin.
- **AC-LD-177.3:** Event ghi nhận thời điểm xảy ra và trigger source tương ứng với thao tác (ví dụ `AI_GENERATION`, `MANUAL_EDIT`, `DRIFT_SUGGESTION`, `PR_WEBHOOK`, `REVIEW_WORKFLOW`, `ROLLBACK`).
- **AC-LD-177.4:** Event có thể lưu action, status, note và related version để mô tả đầy đủ sự kiện.
- **AC-LD-177.5:** Gọi API lấy lịch sử của document tồn tại trả về danh sách `HistoryEvent` theo thứ tự cũ trước, mới sau.
- **AC-LD-177.6:** Gọi API lịch sử với document không tồn tại trả về `404`.
- **AC-LD-177.7:** Frontend hiển thị timeline gồm actor, timestamp, summary và event type.
- **AC-LD-177.8:** Frontend hiển thị đúng trạng thái loading, danh sách rỗng, lỗi quyền truy cập và lỗi tải dữ liệu.
- **AC-LD-177.9:** Migration tạo bảng `documentation_change_logs` với các trường bắt buộc và hai index theo document/time và repository/time.

## 9. Kiểm thử

Các hạng mục kiểm thử được nêu trong yêu cầu Jira:
- Test Documentation Change Log.
- Record Change Timestamp and Trigger.
- Record Change User and Role.
- Display Documentation Change Timeline.
- Record Documentation Changes.

**Ghi chú:** Trong nội dung yêu cầu LD-177 và các phần mã nguồn đã kiểm tra, chưa xác định được tên cụ thể của các test case/file test chuyên biệt cho change log. Vì vậy tài liệu không tự gán tên file kiểm thử chưa được xác minh.
