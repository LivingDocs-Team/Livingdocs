# FR-EVI-04 Implement Evidence & Submission

| Mục | Nội dung |
| :--- | :--- |
| **Story Jira** | LD-106 Implement Evidence & Submission |
| **Task đã làm** | LD-107 Evidence Extraction, LD-109 Status Tracking, LD-110 Submission Workflow, LD-111 CI Check |
| **Người thực hiện** | Lâm Gia Huy |
| **Thành phần** | Backend API (`app/submission`), AI Service (`app/evidence`), Frontend (`src/pages/submission`) |
| **Tác nhân** | GitHub CI Pipeline |

---

## 1. Mô tả
Hệ thống cho phép trích xuất các bằng chứng mã nguồn (`GroundingEvidence`) bao gồm đường dẫn file, dòng bắt đầu/kết thúc và đoạn code snippet thực tế đính kèm vào từng phần của tài liệu. Người dùng theo dõi tiến độ hoàn tất thời gian thực và thực hiện nộp tài liệu (Submission) chuyển sang quy trình phê duyệt của Staff.

---

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
| :--- | :--- |
| **FR-EVI-04.1** | Tự động liên kết mỗi đoạn văn bản tài liệu sinh ra với thông tin vị trí code nguồn gốc (`file_path`, `start_line`, `end_line`, `commit_hash`). |
| **FR-EVI-04.2** | Hiển thị giao diện đối chiếu side-by-side hoặc popup giữa đoạn tài liệu và code snippet thực tế khi nhấp chọn. |
| **FR-EVI-04.3** | Theo dõi trạng thái tiến độ sinh bằng chứng (`progress_percentage`) theo thời gian thực. |
| **FR-EVI-04.4** | Cho phép Developer nhấn nút **"Submit for Review"** để đóng gói tài liệu kèm bộ bằng chứng. |
| **FR-EVI-04.5** | Khóa quyền chỉnh sửa tài liệu và chuyển trạng thái workflow sang `submitted` sau khi gửi thành công. |
| **FR-EVI-04.6** | Tích hợp kích hoạt luồng kiểm thử CI Pipeline tự động trên GitHub Actions khi có yêu cầu phê duyệt mới. |

---

## 3. API

| Method | Endpoint | Kết quả | Yêu cầu |
| :--- | :--- | :--- | :--- |
| **GET** | `/api/v1/documents/{id}/evidence` | `200 OK` + List[Evidence] | FR-EVI-04.1, 04.2 |
| **GET** | `/api/v1/documents/{id}/status` | `200 OK` + Status JSON | FR-EVI-04.3 |
| **POST** | `/api/v1/documents/{id}/submit` | `200 OK` + Submission Status | FR-EVI-04.4, 04.5, 04.6 |

Ví dụ body response `/api/v1/documents/{id}/evidence`:
```json
{
  "document_id": "doc-ld-106-001",
  "evidence_list": [
    {
      "evidence_id": "evi-8812",
      "file_path": "app/models.py",
      "start_line": 10,
      "end_line": 15,
      "code_snippet": "def create_evidence(code, status):\n    return Evidence(code=code, status=status)",
      "commit_hash": "a1b2c3d4e5f6"
    }
  ]
}
```

---

## 4. Luồng chính
1. Developer truy cập màn hình chi tiết bản thảo tài liệu.
2. Hệ thống tải nội dung tài liệu cùng bộ bằng chứng đối chiếu `GroundingEvidence`.
3. Developer nhấp vào từng vùng tài liệu để xem đoạn mã nguồn tương ứng được highlight vị trí dòng.
4. Developer kiểm tra thanh tiến độ đạt `100%` và nút **"Submit for Review"** sáng lên.
5. Developer nhấn **"Submit for Review"**.
6. Backend đổi trạng thái tài liệu sang `submitted`, ghi nhận Audit Log và phát sự kiện tới CI Pipeline để chạy 7/7 kịch bản kiểm thử tự động.

---

## 5. Luồng lỗi

| Trường hợp | HTTP | Kết quả |
| :--- | :--- | :--- |
| Gửi phê duyệt khi tài liệu chưa sinh xong (`status` = `processing`) | `400` | `{"detail": "Cannot submit document while generation is in progress"}` |
| Thiếu dữ liệu bằng chứng mã nguồn | `422` | `{"detail": "Missing grounding evidence for required sections"}` |
| Tài liệu đã nằm ở trạng thái `submitted` hoặc `approved` | `409` | `{"detail": "Document is locked and already submitted"}` |

---

## 6. Quy tắc nghiệp vụ
* Tài liệu không thể gửi phê duyệt nếu không có ít nhất 1 liên kết bằng chứng mã nguồn (`GroundingEvidence`) hợp lệ.
* Ngay sau khi bấm Submit, tài liệu sẽ chuyển sang chế độ Read-Only đối với Developer cho đến khi nhận được phản hồi (Approve/Reject) từ Staff.

---

## 7. Tiêu chí chấp nhận
* **AC-EVI-04.1:** Bằng chứng mã nguồn hiển thị đúng chính xác `file_path` và số dòng thực tế trong Repository.
* **AC-EVI-04.2:** Khi bấm Submit, trạng thái trên giao diện chuyển thành `submitted` và thông báo thành công xuất hiện trong < 1 giây.
* **AC-EVI-04.3:** Kích hoạt kịch bản CI Check thành công trên GitHub Actions (`7/7 checks pass`).

---

## 8. Kiểm thử
* `backend/tests/test_evidence_submission.py`
* `ai-service/tests/test_evidence_extraction.py`
* `.github/workflows/ci.yml`
