# FR-EVI-04 Implement Evidence & Submission

| Mục | Nội dung |
| :--- | :--- |
| **Story Jira** | LD-106 Implement Evidence & Submission |
| **Task đã làm** | LD-107 Evidence Extraction, LD-108 Evidence Display, LD-109 Status Tracking, LD-110 Submission Workflow, LD-111 CI Check |
| **Người thực hiện** | Lâm Gia Huy |
| **Thành phần** | Backend API (`app/models.py`, `app/submission.py`), Test Suite (`tests/test_evidence_submission.py`), GitHub CI (`.github/workflows/ci.yml`) |
| **Tác nhân** | Developer, Staff Reviewer, GitHub CI Pipeline |

---

## 1. Mô tả
Hệ thống cho phép tự động trích xuất và lưu trữ bộ bằng chứng mã nguồn (`GroundingEvidence`) bao gồm đường dẫn file (`file_path`), dòng bắt đầu/kết thúc (`start_line`, `end_line`), `commit_hash` và đoạn mã nguồn tương ứng (`code_snippet`) gắn liền với nội dung tài liệu. Người dùng có thể theo dõi tiến độ sinh tài liệu/bằng chứng theo thời gian thực (`GenerationStatus`), xem giao diện đối chiếu và thực hiện nộp tài liệu (`DocumentationSubmission`) để chuyển sang quy trình phê duyệt của Staff, đồng thời khóa quyền chỉnh sửa và kích hoạt kiểm thử CI.

---

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
| :--- | :--- |
| **FR-EVI-04.1** | Tự động trích xuất và liên kết mỗi đoạn nội dung tài liệu sinh ra với vị trí mã nguồn gốc (`file_path`, `start_line`, `end_line`, `code_snippet`, `commit_hash`). |
| **FR-EVI-04.2** | Cung cấp dịch vụ hiển thị (`EvidenceDisplayService`) để lấy danh sách bằng chứng mã nguồn hỗ trợ giao diện đối chiếu side-by-side hoặc popup cho Developer. |
| **FR-EVI-04.3** | Cập nhật và theo dõi trạng thái tiến độ sinh tài liệu/bằng chứng (`progress_percentage`, `status`) theo thời gian thực thông qua `StatusTracker`. |
| **FR-EVI-04.4** | Cho phép Developer kích hoạt quy trình nộp bài (`SubmissionWorkflow.submit_documentation`) đóng gói tài liệu cùng toàn bộ bằng chứng liên kết. |
| **FR-EVI-04.5** | Chuyển trạng thái workflow của tài liệu sang `submitted` và khóa quyền chỉnh sửa của Developer sau khi nộp thành công. |
| **FR-EVI-04.6** | Đảm bảo tính sẵn sàng tích hợp với GitHub Actions CI Pipeline khi diễn ra luồng kiểm thử tự động của hệ thống. |

---

## 3. API

| Method | Endpoint | Kết quả | Yêu cầu |
| :--- | :--- | :--- | :--- |
| **GET** | `/api/v1/documents/{id}/evidence` | `200 OK` + List[GroundingEvidence] | FR-EVI-04.1, FR-EVI-04.2 |
| **GET** | `/api/v1/documents/{id}/status` | `200 OK` + GenerationStatus JSON | FR-EVI-04.3 |
| **POST** | `/api/v1/documents/{id}/submit` | `200 OK` + DocumentationSubmission | FR-EVI-04.4, FR-EVI-04.5, FR-EVI-04.6 |

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
      "code_snippet": "class GroundingEvidence(BaseModel):\n    evidence_id: str\n    file_path: str\n    start_line: int\n    end_line: int\n    code_snippet: str\n    commit_hash: str",
      "commit_hash": "a1b2c3d4e5f6"
    }
  ]
}
```

Ví dụ body response `/api/v1/documents/{id}/submit`:
```json
{
  "submission_id": "sub-9901",
  "document_id": "doc-ld-106-001",
  "submitted_by": "lamgiahuy",
  "status": "submitted",
  "submitted_at": "2026-03-30T10:15:00Z"
}
```

---

## 4. Luồng chính
1. Developer truy cập vào giao diện quản lý bản thảo tài liệu.
2. Hệ thống tải dữ liệu tài liệu cùng danh sách bằng chứng mã nguồn (`GroundingEvidence`) thông qua `EvidenceDisplayService`.
3. Developer nhấp chọn phần tài liệu để xem đoạn `code_snippet` tương ứng được đánh dấu số dòng và commit hash trong mã nguồn.
4. `StatusTracker` cập nhật tiến độ sinh đạt `100%` với trạng thái `completed`.
5. Developer nhấn **"Submit for Review"**.
6. `SubmissionWorkflow` kiểm tra điều kiện, chuyển trạng thái tài liệu sang `submitted`, tạo bản ghi `DocumentationSubmission` và khóa quyền chỉnh sửa tài liệu.
7. Hệ thống kích hoạt quy trình CI Pipeline trên GitHub Actions để chạy bộ kiểm thử tự động.

---

## 5. Luồng lỗi

| Trường hợp | HTTP | Kết quả |
| :--- | :--- | :--- |
| Gửi nộp khi tài liệu chưa hoàn tất (`status` $\neq$ `completed` hoặc `progress_percentage` < `100`) | `400` | `{"detail": "Cannot submit document while generation is in progress or incomplete"}` |
| Thiếu bằng chứng mã nguồn liên kết (`evidence_list` rỗng) | `422` | `{"detail": "Missing grounding evidence for required sections"}` |
| Tài liệu đã ở trạng thái `submitted` hoặc `approved` | `409` | `{"detail": "Document is locked and already submitted"}` |

---

## 6. Quy tắc nghiệp vụ
- Bằng chứng mã nguồn (`GroundingEvidence`) bắt buộc phải chứa đầy đủ thông tin định vị (`file_path`, `start_line`, `end_line`, `commit_hash`) và đoạn code thực tế (`code_snippet`).
- Tài liệu chỉ đủ điều kiện nộp khi tiến độ `progress_percentage` đạt `100%` và `status` ở trạng thái `completed`.
- Ngay sau khi thực hiện submit thành công, hệ thống phải khóa quyền chỉnh sửa (chuyển sang Read-Only) đối với Developer cho đến khi có kết quả đánh giá từ Staff.

---

## 7. Tiêu chí chấp nhận
- **AC-EVI-04.1:** Dữ liệu `GroundingEvidence` lưu trữ đúng cấu trúc model và ánh xạ chính xác vị trí dòng code trong Repository.
- **AC-EVI-04.2:** Hàm `submit_documentation` chuyển trạng thái sang `submitted` và trả về đối tượng `DocumentationSubmission` hợp lệ.
- **AC-EVI-04.3:** Toàn bộ 100% bộ unit test trong `tests/test_evidence_submission.py` chạy qua thành công (`PASSED`).
- **AC-EVI-04.4:** Workflow CI trên GitHub Actions tích hợp thành công kịch bản build/test nền tảng backend.

---

## 8. Kiểm thử
- `app/models.py` (Core models: `GroundingEvidence`, `GenerationStatus`, `DocumentationSubmission`)
- `app/submission.py` (Core logic: `EvidenceCollector`, `EvidenceDisplayService`, `StatusTracker`, `SubmissionWorkflow`)
- `tests/test_evidence_submission.py` (Unit tests cho LD-107, LD-108, LD-109, LD-110)
- `.github/workflows/ci.yml` (CI configuration & Pipeline validation)
