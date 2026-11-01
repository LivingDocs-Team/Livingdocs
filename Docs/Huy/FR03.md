# FR-AI-03 Implement Documentation Generation & Preview/Editing

| Mục | Nội dung |
| :--- | :--- |
| **Story Jira** | LD-90 Implement Documentation Generation, LD-101 Documentation Preview & Editing |
| **Task đã làm** | LD-96 Implement Templates, LD-105 Test Preview/Edit, LD-340 Doc Generation From Analysis |
| **Người thực hiện** | Lâm Gia Huy |
| **Thành phần** | AI Service (`app/jobs.py`, `app/models.py`), Frontend Markdown Editor (`src/components/editor`) |
| **Tác nhân** | LLM Engine (FastAPI Service) |

---

## 1. Mô tả
Hệ thống nhận kết quả phân tích AST, áp dụng các khung mẫu tài liệu (Template: API Reference, Module Guide) và gửi prompt tới LLM để tự động sinh bản thảo tài liệu kỹ thuật dưới dạng Markdown. Người dùng có thể xem trước hiển thị Markdown thời gian thực (Preview) và chỉnh sửa trực tiếp trước khi gửi phê duyệt.

---

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
| :--- | :--- |
| **FR-AI-03.1** | Cho phép người dùng gửi yêu cầu sinh tài liệu cho 1 file, 1 module hoặc toàn bộ repository kèm theo `template_id`. |
| **FR-AI-03.2** | Khởi tạo công việc chạy nền (Background Job) và trả về ngay `job_id` cùng trạng thái ban đầu `pending`. |
| **FR-AI-03.3** | Định dạng kết quả sinh tài liệu theo cấu trúc của Template được chọn (có các phần Headings, Parameters, Code Examples). |
| **FR-AI-03.4** | Hiển thị màn hình Split-View: bên trái là Markdown Editor cho phép sửa văn bản, bên phải là giao diện Preview render HTML real-time. |
| **FR-AI-03.5** | Cho phép lưu bản thảo chỉnh sửa thủ công mà không làm mất các thông tin liên kết mã nguồn. |

---

## 3. API

| Method | Endpoint | Kết quả | Yêu cầu |
| :--- | :--- | :--- | :--- |
| **POST** | `/jobs/generate` | `202 Accepted` + Job Info | FR-AI-03.1, 03.2 |
| **GET** | `/jobs/{id}` | `200 OK` + Job Progress | FR-AI-03.2 |
| **GET** | `/jobs/{id}/result` | `200 OK` + Markdown Document | FR-AI-03.3, 03.4 |
| **PUT** | `/api/v1/documents/{id}` | `200 OK` + Updated Document | FR-AI-03.5 |

Ví dụ body `/jobs/generate`:
```json
{
  "scope": "file",
  "target": "app/models.py",
  "template_id": "api-reference-v1",
  "output_language": "vi",
  "files": [
    {
      "path": "app/models.py",
      "language": "python",
      "functions": [
        {
          "name": "create_evidence",
          "lineno": 10,
          "end_lineno": 15
        }
      ]
    }
  ]
}
```

---

## 4. Luồng chính
1. Người dùng chọn file code và bấm nút **"Generate Documentation"**.
2. Frontend gọi POST `/jobs/generate`, nhận về `job_id` và tiến hành poll trạng thái mỗi 1 giây.
3. Dịch vụ AI Service dựng prompt dựa trên cấu trúc AST và Template được chọn, gửi tới LLM.
4. Sau khi hoàn tất, job đổi trạng thái thành `completed`.
5. Frontend chuyển hướng người dùng tới trang Preview/Edit hiển thị nội dung Markdown vừa sinh.
6. Người dùng thực hiện chỉnh sửa nội dung và bấm **"Save Draft"**.

---

## 5. Luồng lỗi

| Trường hợp | HTTP | Kết quả |
| :--- | :--- | :--- |
| `template_id` không tồn tại | `404` | `{"detail": "Template 'id' not found"}` |
| Yêu cầu sinh tài liệu khi job chưa xong | `409` | `{"detail": "Job is still processing"}` |
| Lỗi ngắt kết nối LLM API | `500` | `{"detail": "AI Generation failed due to upstream timeout"}` |

---

## 6. Quy tắc nghiệp vụ
* Khung Markdown tạo ra phải bắt đầu bằng tiêu đề `# <path_file>`.
* Biên tập viên Markdown trên Frontend phải tự động lưu bản nháp (Auto-save) sau mỗi 30 giây nếu có thay đổi.

---

## 7. Tiêu chí chấp nhận
* **AC-AI-03.1:** 100% tài liệu được tạo có chứa đầy đủ các Section quy định trong Template.
* **AC-AI-03.2:** Màn hình Preview render chuẩn định dạng Markdown (code highlight, tables, lists) trong thời gian dưới 100ms khi nhập dữ liệu.

---

## 8. Kiểm thử
* `ai-service/tests/test_api.py`
* `frontend/tests/test_markdown_editor.spec.ts`
