# FR-AST-02 Implement Source Code Analysis

| Mục | Nội dung |
| :--- | :--- |
| **Story Jira** | LD-85 Source Code Analysis |
| **Task đã làm** | LD-328 Source Code AST Analysis Implementation |
| **Người thực hiện** | Lâm Gia Huy |
| **Thành phần** | AI Service (`ai-service/analyzer`), Code Parser Engine |
| **Tác nhân** | Background Task Engine |

---

## 1. Mô tả
Hệ thống sử dụng các bộ parser cú pháp (Abstract Syntax Tree - AST) để phân tích chi tiết tệp mã nguồn thuộc các ngôn ngữ hỗ trợ (Python, Java, TypeScript/JavaScript). Quá trình phân tích trích xuất danh sách các lớp (classes), phương thức (methods/functions), tham số (parameters), kiểu trả về (return types) và các mối quan hệ phụ thuộc để chuẩn bị dữ liệu đầu vào cho AI sinh tài liệu.

---

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
| :--- | :--- |
| **FR-AST-02.1** | Nhận đầu vào là mã nguồn của một file, một module hoặc toàn bộ repository từ dịch vụ lưu trữ. |
| **FR-AST-02.2** | Trích xuất toàn bộ các thực thể code (code entities): Class, Method, Field, Function Signature, Decorator, Docstring hiện có. |
| **FR-AST-02.3** | Ghi nhận vị trí chính xác của từng thực thể bao gồm đường dẫn file (`file_path`), dòng bắt đầu (`start_line`), và dòng kết thúc (`end_line`). |
| **FR-AST-02.4** | Bỏ qua các tệp không nằm trong phạm vi hỗ trợ (binary, images, dependencies như `node_modules`, `venv`, build artifacts). |
| **FR-AST-02.5** | Trả về cấu trúc JSON AST chuẩn hóa chứa thông tin chi tiết về từng thực thể mã nguồn. |

---

## 3. API

| Method | Endpoint | Kết quả | Yêu cầu |
| :--- | :--- | :--- | :--- |
| **POST** | `/api/v1/analyzer/ast` | `200 OK` + AST Structure | FR-AST-02.1 - 02.3 |
| **POST** | `/api/v1/analyzer/coverage-gap` | `200 OK` + Gap List | FR-AST-02.2, 02.5 |

Ví dụ body `/api/v1/analyzer/ast`:
```json
{
  "repo_id": "repo-livingdocs-01",
  "branch": "main",
  "files": ["app/services/document.py"]
}
```

---

## 4. Luồng chính
1. Dịch vụ AI Service nhận yêu cầu phân tích tệp mã nguồn từ công việc sinh tài liệu.
2. Trình phân tích kiểm tra định dạng đuôi file (`.py`, `.java`, `.ts`, `.js`).
3. Khởi tạo bộ parse AST tương ứng (ví dụ: mô-đun `ast` của Python, `tree-sitter` cho Java/TS).
4. Duyệt qua cây cú pháp và trích xuất thông tin chữ ký hàm (function signatures), dòng mã, và docstrings.
5. Đóng gói kết quả thành cấu trúc AST metadata JSON và chuyển sang pipeline sinh tài liệu.

---

## 5. Luồng lỗi

| Trường hợp | HTTP | Kết quả |
| :--- | :--- | :--- |
| File bị lỗi cú pháp không parse được (Syntax Error) | `422` | `{"detail": "Syntax error at line X in file Y", "status": "invalid"}` |
| Định dạng tệp không được hỗ trợ | `400` | `{"detail": "Unsupported file extension"}` |
| File rỗng không có dung lượng | `200` | `{"status": "skipped", "reason": "empty_file"}` |

---

## 6. Quy tắc nghiệp vụ
* Thời gian phân tích AST cho 1 file không quá 500ms đối với các file có quy mô dưới 5,000 dòng code.
* Nếu tệp chứa cú pháp lỗi, hệ thống phải ghi nhận cảnh báo `SyntaxError` nhưng không được ngắt toàn bộ tiến trình phân tích của các tệp còn lại trong cùng Repository.

---

## 7. Tiêu chí chấp nhận
* **AC-AST-02.1:** Trích xuất chính xác 100% dòng bắt đầu và kết thúc của toàn bộ phương thức trong tệp mã nguồn Python và TypeScript.
* **AC-AST-02.2:** Loại bỏ đúng các thư viện ngoài và thư mục bỏ qua (`.git`, `node_modules`).

---

## 8. Kiểm thử
* `ai-service/tests/test_ast_analyzer.py`
* `ai-service/tests/test_syntax_parsers.py`
