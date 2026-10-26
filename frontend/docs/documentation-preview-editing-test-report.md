# Báo cáo kiểm thử: Documentation Preview & Editing (LD-105)

Người làm: Đăng (TV2). Ngày: 25/10/2026, cập nhật 26/10/2026 sau khi LD-101 cải tiến phần xem trước. Thuộc LD-101.

Phạm vi: màn hình **Documentation Management** của frontend (`frontend/src/DocumentationManagement.jsx`), phần sau khi sinh tài liệu: soạn thảo, xem trước, lưu nháp, phiên bản, so sánh, xuất file Markdown.

## 1. Tóm tắt

| Hạng mục | Kết quả |
|---|---|
| Test tự động (Playwright, backend giả lập) | 14 test: **13 đạt**, 1 xfail (phần còn lại của lỗi F1) |
| Bảo mật khi xem trước (HTML, script, link `javascript:` trong tài liệu) | Đạt: hiện dạng chữ, không chạy |
| Lỗi và vấn đề phát hiện | 4 vấn đề của tính năng (F1–F4, F1 đã sửa một phần ở LD-101), 1 test cũ đang lỗi (F5) |
| CI | Thêm job **Frontend E2E Test** chạy các test này ở mỗi lần push và pull request |

## 2. Cách chạy

Test mở giao diện thật trong trình duyệt Chromium. Mọi request `/api/**` được giả lập ngay trong test, nên **không cần backend**, chỉ cần frontend chạy ở cổng 3000.

1. Chạy frontend (hoặc dùng Docker Compose, frontend cũng ở cổng 3000):
   ```bash
   cd frontend
   npm ci
   npm run build
   npx vite preview --port 3000
   ```
2. Mở terminal khác ở thư mục gốc của repo:
   ```bash
   pip install pytest pytest-playwright pytest-html
   python -m playwright install chromium
   python -m pytest -o addopts="" -v tests/test_documentation_preview_editing.py
   ```

Frontend chưa chạy thì cả file test tự bỏ qua (skip). Trong CI, biến `FRONTEND_E2E_REQUIRED=true` biến việc bỏ qua thành lỗi.

Job CI **Frontend E2E Test** (`.github/workflows/ci.yml`): build frontend, chạy `vite preview` ở cổng 3000, cài Playwright Chromium, chạy test, lưu báo cáo HTML vào artifact `frontend-e2e-test-report`.

## 3. Các test case

File: `tests/test_documentation_preview_editing.py`

| # | Test | Kiểm tra gì | Kết quả |
|---|---|---|---|
| 1 | `test_generated_document_opens_in_editor` | Tài liệu vừa sinh nằm trong ô soạn thảo, tab Edit đang mở, báo "All changes saved", có danh sách bằng chứng; request sinh tài liệu gửi đúng `templateId`, `outputLanguage` | Đạt |
| 2 | `test_generation_problem_shows_error_and_no_editor` (2 trường hợp) | Job lỗi thì hiện lỗi từ AI service; tài liệu rỗng thì báo "returned an empty document"; không hiện ô soạn thảo | Đạt |
| 3 | `test_editing_shows_unsaved_state_and_save_draft_clears_it` | Sửa nội dung thì báo "You have unsaved edits."; bấm Save draft thì báo đã lưu và hết trạng thái chưa lưu | Đạt |
| 4 | `test_empty_document_cannot_be_saved_versioned_or_previewed` | Nội dung rỗng hoặc toàn khoảng trắng: không lưu nháp, không tạo phiên bản, Preview báo "No content to preview." | Đạt |
| 5 | `test_preview_renders_supported_markdown` | Preview hiển thị đúng heading cấp 1–3, danh sách gạch đầu dòng, danh sách đánh số, khối code, đường kẻ, đoạn văn tiếng Việt | Đạt |
| 6 | `test_preview_shows_unsaved_edits_and_edits_survive_tab_switch` | Preview hiện cả phần chưa lưu; chuyển qua lại giữa các tab không mất nội dung | Đạt |
| 7 | `test_preview_does_not_run_html_or_scripts` | `<script>`, `<img onerror>`, `<svg onload>`, thẻ `<a href="javascript:...">` và link Markdown `[...](javascript:...)` (từ AI hoặc do người dùng gõ) hiện dạng chữ, không chạy | Đạt. Đã thử bỏ bước escape HTML trong code thì test báo lỗi, tức test bắt được lỗi XSS |
| 8 | `test_preview_renders_inline_markdown_used_by_ai_output` | In đậm, inline code trong heading cấp 4, link `https://` (có `rel="noopener noreferrer"`) | Đạt (từ LD-101) |
| 9 | `test_preview_renders_blockquote_and_table` | Trích dẫn `>` và bảng | **XFAIL**: phần còn lại của lỗi F1 |
| 10 | `test_create_version_and_restore_it` | Tạo Version 1; khôi phục: bấm Cancel thì không đổi, bấm OK thì nội dung quay về Version 1; đúng câu hỏi xác nhận | Đạt |
| 11 | `test_compare_marks_changed_lines` | Chưa có phiên bản thì hiện hướng dẫn; sửa 1 dòng thì đánh dấu đúng 1 dòng xoá, 1 dòng thêm | Đạt |
| 12 | `test_export_downloads_current_markdown` | Tải file `livingdocs-documentation.md` đúng nội dung đang sửa, giữ nguyên tiếng Việt (UTF-8) | Đạt |
| 13 | `test_reset_returns_to_initial_state` | Bấm Reset thì về trạng thái "Ready to generate" | Đạt |

## 4. Lỗi và vấn đề phát hiện

| # | Mức độ | Vấn đề | Cách tái hiện | Đề xuất |
|---|---|---|---|---|
| F1 | Trung bình (đã sửa một phần) | Ban đầu preview chỉ hiểu heading cấp 1–3, danh sách gạch đầu dòng, khối code và `---`. **LD-101 (26/10) đã sửa phần lớn:** in đậm, nghiêng, inline code, heading cấp 4–6, link `http(s)`, danh sách đánh số đã hiển thị đúng. **Còn thiếu:** trích dẫn `>` và bảng, mà tài liệu do ai-service sinh ra có dùng (bản sinh ngày 19/10: 11 dòng trích dẫn, nhiều bảng), nên Preview vẫn hiện `&gt;` và `\|` thô ở các chỗ đó | Sinh tài liệu, mở tab Preview, xem phần độ tin cậy và bảng tham số | Bổ sung trích dẫn và bảng vào bộ hiển thị Markdown, vẫn giữ việc chặn HTML. Sửa xong thì bỏ `xfail` ở test 9 |
| F2 | Trung bình (kiểm tra lại 26/10: vẫn còn) | Bấm **Generate documentation** hoặc **Reset** khi đang có chỉnh sửa hoặc phiên bản: mất hết nội dung đã sửa và các phiên bản, không hỏi xác nhận | Sinh tài liệu → Create version → sửa nội dung → bấm Generate documentation: nội dung tự viết bị thay, "Versions (1)" thành "Versions (0)", không có hộp xác nhận | Hỏi xác nhận khi có chỉnh sửa chưa lưu hoặc có phiên bản |
| F3 | Trung bình (đã biết, 26/10: vẫn còn) | Bản nháp và phiên bản chỉ nằm trong bộ nhớ trang, tải lại trang là mất. Giao diện có ghi chú việc này | Lưu nháp, tải lại trang | Lưu bản nháp và phiên bản vào backend ở sprint sau |
| F4 | Thấp (26/10: vẫn còn) | Compare so theo số thứ tự dòng: chèn 1 dòng ở đầu một tài liệu 19 dòng thì cả 20 dòng bị đánh dấu "thêm" và 19 dòng "xoá" | Create version → thêm 1 dòng ở đầu → Compare | So sánh bằng thuật toán diff theo dòng (ví dụ thư viện `diff`) |
| F5 | Thấp, ngoài phạm vi (26/10: vẫn còn) | `tests/test_frontend.py::test_frontend_homepage_title` đang lỗi: tiêu đề trang là "frontend" (`frontend/index.html`), test mong "LivingDocs - Automated Documentation Generator" | Chạy test này khi frontend đang chạy | Sửa thẻ `<title>` trong `frontend/index.html` |

## 5. Ghi chú

- Backend được giả lập nên đây là kiểm thử giao diện. Phần sinh tài liệu phía server đã có test riêng (`DocumentationGenerationServiceTest` trong github-integration-service, test của ai-service).
- Test không phụ thuộc danh sách template, nên vẫn chạy được khi LD-96 (quản lý template) được merge.
- Test dùng role và nhãn trên giao diện (tên nút, tab, `#documentation-editor`). Đổi chữ trên các nút này thì cần sửa test theo.
