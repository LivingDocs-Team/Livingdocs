"""LD-105: kiểm thử tính năng xem trước và chỉnh sửa tài liệu (Documentation Preview & Editing).

Test chạy trên giao diện thật trong trình duyệt (Playwright). Mọi request /api/** được giả lập,
nên chỉ cần frontend chạy ở FRONTEND_URL (mặc định http://localhost:3000), không cần backend.

Chạy trên máy:
    cd frontend && npm ci && npm run build && npx vite preview --port 3000
    pip install pytest pytest-playwright pytest-html && python -m playwright install chromium
    python -m pytest -o addopts="" -v tests/test_documentation_preview_editing.py

Kết quả và các lỗi phát hiện: frontend/docs/documentation-preview-editing-test-report.md
"""
import json
import os
import re
import urllib.request

import pytest

pytest.importorskip("pytest_playwright", reason="cần cài pytest-playwright để chạy test giao diện")

from playwright.sync_api import Page, expect  # noqa: E402

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
USER_ID = "42"
WORKSPACE_ID = f"ws-{USER_ID}"
REPOSITORY_ID = "5b1c6f0e-7d3a-4c2b-9a8e-105105105105"
JOB_ID = "job-ld105"

GENERATED_MARKDOWN = "\n".join([
    "# acme/shop",
    "",
    "Tài liệu kỹ thuật được sinh tự động.",
    "",
    "## Classes",
    "",
    "### ShopService",
    "",
    "- create_order: tạo đơn hàng",
    "- cancel_order: huỷ đơn hàng",
    "",
    "```python",
    "def create_order(items):",
    "    return Order(items)",
    "```",
    "",
    "---",
    "",
    "1. Bước đầu tiên",
])

# Trích từ tài liệu thật do ai-service sinh ra (19/10/2026)
AI_STYLE_MARKDOWN = "\n".join([
    "# app/analyzer.py",
    "",
    "Độ tin cậy chung: **0.32 (thấp)**",
    "",
    "#### `parse_python_ast`",
    "",
    "> Độ tin cậy: **0.30 (thấp)**",
    "",
    "| Tên | Kiểu |",
    "|---|---|",
    "| code | str |",
])


@pytest.fixture(scope="module", autouse=True)
def frontend_is_running():
    """Bỏ qua cả file nếu frontend chưa chạy; trong CI (FRONTEND_E2E_REQUIRED=true) thì báo lỗi."""
    try:
        urllib.request.urlopen(FRONTEND_URL, timeout=5).close()
    except OSError as error:
        message = f"Frontend chưa chạy ở {FRONTEND_URL}: {error}"
        if os.environ.get("FRONTEND_E2E_REQUIRED") == "true":
            pytest.fail(message)
        pytest.skip(message)


class FakeApi:
    """Backend giả: trả dữ liệu cố định và ghi lại các request frontend đã gửi."""

    def __init__(self, markdown=GENERATED_MARKDOWN, job_status="completed", job_error=None):
        self.markdown = markdown
        self.job_status = job_status
        self.job_error = job_error
        self.requests = []

    def handle(self, route):
        request = route.request
        path = request.url.split("?", 1)[0].removeprefix(FRONTEND_URL)
        self.requests.append((request.method, path, request.post_data))
        job_path = f"/api/documentation/jobs/{JOB_ID}"

        if (request.method, path) == ("GET", "/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-ld105"})
        if (request.method, path) == ("GET", f"/api/workspaces/{WORKSPACE_ID}/repositories"):
            return route.fulfill(status=200, json=[{
                "id": REPOSITORY_ID, "workspaceId": WORKSPACE_ID, "githubRepoId": 4242,
                "fullName": "acme/shop", "defaultBranch": "main", "privateRepo": False,
                "status": "CONNECTED", "lastSyncedAt": "2026-10-24T08:00:00Z",
            }])
        if (request.method, path) == ("GET", "/api/documentation/templates"):
            return route.fulfill(status=200, json=[{
                "id": "default", "name": "Standard technical docs", "description": "",
                "instructions": "", "sections": ["Overview"], "built_in": True,
            }])
        if (request.method, path) == ("POST", f"/api/repositories/{REPOSITORY_ID}/documentation/generate"):
            return route.fulfill(status=202, json={"id": JOB_ID, "status": "pending"})
        if (request.method, path) == ("GET", job_path):
            body = {"id": JOB_ID, "status": self.job_status, "progress": 1.0}
            if self.job_error:
                body["error"] = self.job_error
            return route.fulfill(status=200, json=body)
        if (request.method, path) == ("GET", f"{job_path}/result"):
            return route.fulfill(status=200, content_type="text/markdown; charset=utf-8", body=self.markdown)
        if (request.method, path) == ("GET", f"{job_path}/report"):
            return route.fulfill(status=200, json={"files": [{"entities": [{
                "name": "ShopService",
                "evidence": [{"path": "src/shop.py", "line_start": 4, "line_end": 12}],
            }]}]})
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {request.method} {path}"})


def open_documentation_page(page: Page, api: FakeApi) -> None:
    """Đăng nhập sẵn (userId trong sessionStorage) rồi mở màn hình Documentation Management."""
    page.add_init_script(f"window.sessionStorage.setItem('livingdocs.userId', '{USER_ID}')")
    page.route("**/api/**", api.handle)
    page.goto(FRONTEND_URL + "/")
    page.get_by_role("button", name="Documentation Management").first.click()
    expect(page.get_by_role("heading", name="Documentation Management")).to_be_visible()


def generate(page: Page) -> None:
    generate_button = page.get_by_role("button", name="Generate documentation")
    expect(generate_button).to_be_enabled()
    generate_button.click()


def open_generated_document(page: Page, markdown: str = GENERATED_MARKDOWN) -> FakeApi:
    api = FakeApi(markdown=markdown)
    open_documentation_page(page, api)
    generate(page)
    expect(page.get_by_role("heading", name="Generated Documentation")).to_be_visible(timeout=10_000)
    return api


def editor(page: Page):
    return page.locator("#documentation-editor")


def notice(page: Page, text: str):
    return page.get_by_role("status").filter(has_text=text)


def preview(page: Page):
    page.get_by_role("tab", name="Preview").click()
    return page.locator(".markdown-preview-content")


# ---------- Mở tài liệu vừa sinh ----------

def test_generated_document_opens_in_editor(page: Page):
    api = open_generated_document(page)

    expect(editor(page)).to_have_value(GENERATED_MARKDOWN)
    expect(page.get_by_role("tab", name="Edit")).to_have_attribute("aria-selected", "true")
    expect(page.get_by_text("All changes saved in the current page session.")).to_be_visible()
    expect(page.get_by_text("ShopService — src/shop.py:4-12")).to_be_visible()
    generate_bodies = [json.loads(body) for method, path, body in api.requests
                       if method == "POST" and path == f"/api/repositories/{REPOSITORY_ID}/documentation/generate"]
    assert len(generate_bodies) == 1
    assert generate_bodies[0]["templateId"] == "default"
    assert generate_bodies[0]["outputLanguage"] == "vi"


@pytest.mark.parametrize(("job_status", "job_error", "markdown", "message"), [
    ("failed", "AI service unavailable", GENERATED_MARKDOWN, "AI service unavailable"),
    ("completed", None, "   \n", "The documentation service returned an empty document."),
], ids=["job-failed", "empty-document"])
def test_generation_problem_shows_error_and_no_editor(page: Page, job_status, job_error, markdown, message):
    api = FakeApi(markdown=markdown, job_status=job_status, job_error=job_error)
    open_documentation_page(page, api)
    generate(page)

    expect(page.get_by_role("alert")).to_contain_text(message, timeout=10_000)
    expect(page.get_by_text("Generation failed")).to_be_visible()
    expect(page.get_by_role("heading", name="Generated Documentation")).to_have_count(0)
    expect(editor(page)).to_have_count(0)


# ---------- Chỉnh sửa ----------

def test_editing_shows_unsaved_state_and_save_draft_clears_it(page: Page):
    open_generated_document(page)
    edited = GENERATED_MARKDOWN + "\n\n## Ghi chú\n\nĐã chỉnh sửa bằng tay."

    editor(page).fill(edited)
    expect(page.get_by_text("You have unsaved edits.")).to_be_visible()

    page.get_by_role("button", name="Save draft").click()
    expect(notice(page, "Draft saved in this page session.")).to_be_visible()
    expect(page.get_by_text("All changes saved in the current page session.")).to_be_visible()
    expect(editor(page)).to_have_value(edited)


def test_empty_document_cannot_be_saved_versioned_or_previewed(page: Page):
    open_generated_document(page)

    editor(page).fill("   \n  ")
    page.get_by_role("button", name="Save draft").click()
    expect(page.get_by_role("alert")).to_have_text("Document content cannot be empty.")

    page.get_by_role("button", name="Create version").click()
    expect(page.get_by_role("alert")).to_have_text("Generate or enter document content before creating a version.")
    expect(page.get_by_role("tab", name="Versions")).to_have_text("Versions (0)")

    page.get_by_role("tab", name="Preview").click()
    expect(page.get_by_text("No content to preview.")).to_be_visible()


# ---------- Xem trước ----------

def test_preview_renders_supported_markdown(page: Page):
    open_generated_document(page)
    content = preview(page)

    expect(content.locator("h1")).to_have_text("acme/shop")
    expect(content.locator("h2")).to_have_text("Classes")
    expect(content.locator("h3")).to_have_text("ShopService")
    expect(content.locator("ul > li")).to_have_text(["create_order: tạo đơn hàng", "cancel_order: huỷ đơn hàng"])
    expect(content.locator("pre > code")).to_have_text("def create_order(items):\n    return Order(items)")
    expect(content.locator("hr")).to_have_count(1)
    expect(content.locator("p").filter(has_text="Tài liệu kỹ thuật được sinh tự động.")).to_have_count(1)
    expect(content.locator("ol > li")).to_have_text(["Bước đầu tiên"])


def test_preview_shows_unsaved_edits_and_edits_survive_tab_switch(page: Page):
    open_generated_document(page)
    edited = GENERATED_MARKDOWN.replace("# acme/shop", "# acme/shop (bản sửa)", 1)
    editor(page).fill(edited)

    expect(preview(page).locator("h1")).to_have_text("acme/shop (bản sửa)")

    page.get_by_role("tab", name="Edit").click()
    expect(editor(page)).to_have_value(edited)
    expect(page.get_by_text("You have unsaved edits.")).to_be_visible()


def test_preview_does_not_run_html_or_scripts(page: Page):
    """Nội dung từ AI hoặc do người dùng gõ phải hiện dạng chữ, không được chạy như HTML."""
    malicious = "\n".join([
        "# <b>Tiêu đề</b>",
        "<script>window.__ld105_xss = 'script'</script>",
        '<img src="x" onerror="window.__ld105_xss = \'img\'">',
        "- <a href=\"javascript:alert(1)\">link</a>",
        "- [bấm vào đây](javascript:alert(1))",
    ])
    open_generated_document(page, markdown=malicious)
    content = preview(page)

    expect(content.locator("h1")).to_have_text("<b>Tiêu đề</b>")
    expect(content).to_contain_text("<script>window.__ld105_xss = 'script'</script>")
    expect(content.locator("script, img, b, a")).to_have_count(0)

    page.get_by_role("tab", name="Edit").click()
    editor(page).fill(malicious + "\n<svg onload=\"window.__ld105_xss = 'svg'\"></svg>")
    expect(preview(page).locator("svg, script, img")).to_have_count(0)
    assert page.evaluate("window.__ld105_xss") is None


def test_preview_renders_inline_markdown_used_by_ai_output(page: Page):
    """In đậm, inline code, heading cấp 4 và link http(s) (preview hỗ trợ từ LD-101)."""
    open_generated_document(page, markdown=AI_STYLE_MARKDOWN + "\n\nXem [repo](https://github.com/LivingDocs-Team/Livingdocs).")
    content = preview(page)

    expect(content.locator("strong").first).to_have_text("0.32 (thấp)")
    expect(content.locator("h4 code")).to_have_text("parse_python_ast")
    link = content.locator("a")
    expect(link).to_have_text("repo")
    expect(link).to_have_attribute("href", "https://github.com/LivingDocs-Team/Livingdocs")
    expect(link).to_have_attribute("rel", "noopener noreferrer")


@pytest.mark.xfail(reason="Phát hiện F1 (phần còn lại) trong báo cáo: preview chưa hiển thị trích dẫn (>) "
                          "và bảng mà tài liệu do AI sinh ra có dùng", strict=False)
def test_preview_renders_blockquote_and_table(page: Page):
    open_generated_document(page, markdown=AI_STYLE_MARKDOWN)
    content = preview(page)

    expect(content.locator("blockquote")).to_have_count(1, timeout=2_000)
    expect(content.locator("table")).to_have_count(1, timeout=2_000)


# ---------- Phiên bản và so sánh ----------

def test_create_version_and_restore_it(page: Page):
    open_generated_document(page)

    page.get_by_role("button", name="Create version").click()
    expect(notice(page, "Version 1 created.")).to_be_visible()
    expect(page.get_by_role("tab", name="Versions")).to_have_text("Versions (1)")

    editor(page).fill("# Bản nháp mới")
    page.get_by_role("tab", name="Versions").click()
    expect(page.locator(".documentation-version-card")).to_contain_text("Version 1")
    expect(page.locator(".documentation-version-card")).to_contain_text(f"{len(GENERATED_MARKDOWN)} characters")

    # Bấm Cancel trong hộp xác nhận: không đổi gì
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("button", name="Restore this version").click()
    page.get_by_role("tab", name="Edit").click()
    expect(editor(page)).to_have_value("# Bản nháp mới")

    # Bấm OK: nội dung quay về Version 1
    messages = []

    def accept(dialog):
        messages.append(dialog.message)
        dialog.accept()

    page.get_by_role("tab", name="Versions").click()
    page.once("dialog", accept)
    page.get_by_role("button", name="Restore this version").click()
    expect(page.get_by_role("tab", name="Edit")).to_have_attribute("aria-selected", "true")
    expect(editor(page)).to_have_value(GENERATED_MARKDOWN)
    expect(notice(page, "Content restored from Version 1.")).to_be_visible()
    assert messages == ["Restore Version 1? Current unsaved edits will be replaced."]


def test_compare_marks_changed_lines(page: Page):
    open_generated_document(page)

    page.get_by_role("tab", name="Compare").click()
    expect(page.get_by_text("Create a version first to enable comparison.")).to_be_visible()

    page.get_by_role("tab", name="Edit").click()
    page.get_by_role("button", name="Create version").click()
    editor(page).fill(GENERATED_MARKDOWN.replace(
        "Tài liệu kỹ thuật được sinh tự động.", "Nội dung đã được cập nhật."))

    page.get_by_role("tab", name="Compare").click()
    page.locator("#compare-version").select_option(index=1)

    expect(page.locator(".diff-removed")).to_have_count(1)
    expect(page.locator(".diff-removed")).to_contain_text("Tài liệu kỹ thuật được sinh tự động.")
    expect(page.locator(".diff-added")).to_have_count(1)
    expect(page.locator(".diff-added")).to_contain_text("Nội dung đã được cập nhật.")


# ---------- Xuất file và làm lại ----------

def test_export_downloads_current_markdown(page: Page):
    open_generated_document(page)
    edited = GENERATED_MARKDOWN + "\n\nPhụ lục: đã kiểm tra."
    editor(page).fill(edited)

    with page.expect_download() as download_info:
        page.get_by_role("button", name="Export Markdown").click()
    download = download_info.value

    assert download.suggested_filename == "livingdocs-documentation.md"
    with open(download.path(), encoding="utf-8") as exported:
        assert exported.read() == edited


def test_reset_returns_to_initial_state(page: Page):
    open_generated_document(page)
    page.get_by_role("button", name="Create version").click()

    # Hiện tại Reset không hỏi xác nhận (lỗi F2). Khi có hộp xác nhận thì bấm OK, test vẫn đúng.
    page.on("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Reset").click()

    expect(page.get_by_text("Ready to generate")).to_be_visible()
    expect(page.get_by_role("heading", name="Generated Documentation")).to_have_count(0)
    expect(page.get_by_text(re.compile(r"Generation job:"))).to_have_count(0)
