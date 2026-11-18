"""LD-188 Test Documentation Diff & Comparison (LD-183: LD-184 .. LD-187), frontend side.

Runs in the browser (Playwright) against the built frontend at FRONTEND_URL (default
http://localhost:3000). Every /api request is mocked, so no backend is needed. The comparison
responses below have the shape GitHub Integration returns from the AI service's
/internal/documents/{id}/compare (ai-service/app/doc_diff.py, tested in ai-service/tests/test_doc_diff.py).

    cd frontend && npm ci && npm run build && npx vite preview --port 3000
    python -m pytest -o addopts="" -v tests/test_documentation_diff.py
"""
import os
import urllib.parse
import urllib.request

import pytest

pytest.importorskip("pytest_playwright", reason="cần cài pytest-playwright để chạy test giao diện")

from playwright.sync_api import Page, expect  # noqa: E402

from rbac_nav import open_screen  # noqa: E402

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
USER_ID = "42"
WORKSPACE_ID = f"ws-{USER_ID}"
REPOSITORY_ID = "5b1c6f0e-7d3a-4c2b-9a8e-183183183183"
WORKFLOW_ID = "wf-183"
DOCUMENT_ID = "doc-183"
JOB_ID = "job-ld183"


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


def version(number, status):
    return {"number": number, "status": status, "origin": "edit" if number > 1 else "generated",
            "created_at": f"2026-11-1{number}T08:00:00Z", "created_by": USER_ID, "note": None}


VERSIONS = [version(1, "superseded"), version(2, "superseded"), version(3, "current")]


def seg(*parts):
    return [{"text": text, "changed": changed} for text, changed in parts]


def unchanged(old, new, text, section):
    return {"kind": "unchanged", "old_number": old, "new_number": new, "old_text": text, "new_text": text,
            "old_segments": [], "new_segments": [], "section": section}


def comparison(from_number, to_number):
    """Version 1 -> 2: one modified line, one removed and one added line, a removed / added section."""
    rows = [
        unchanged(1, 1, "# Cart", "Cart"),
        unchanged(2, 2, "", "Cart"),
        {"kind": "modified", "old_number": 3, "new_number": 3,
         "old_text": "The cart total includes VAT.", "new_text": "The cart total includes VAT and shipping.",
         "old_segments": seg(("The cart total includes VAT.", False)),
         "new_segments": seg(("The cart total includes VAT", False), (" and shipping", True), (".", False)),
         "section": "Cart"},
        *[unchanged(4 + k, 4 + k, f"Unchanged paragraph {k + 1}.", "Cart") for k in range(10)],
        {"kind": "removed", "old_number": 14, "new_number": None, "old_text": "## Legacy", "new_text": None,
         "old_segments": [], "new_segments": [], "section": "Legacy"},
        {"kind": "added", "old_number": None, "new_number": 14, "old_text": None,
         "new_text": "## Shipping options", "old_segments": [], "new_segments": [], "section": "Shipping options"},
    ]
    return {
        "document_id": DOCUMENT_ID,
        "from_version": next(v for v in VERSIONS if v["number"] == from_number),
        "to_version": next(v for v in VERSIONS if v["number"] == to_number),
        "identical": False,
        "stats": {"added": 1, "removed": 1, "modified": 1, "unchanged": 12},
        "sections": [
            {"section": "Cart", "status": "modified", "added": 0, "removed": 0, "modified": 1},
            {"section": "Legacy", "status": "removed", "added": 0, "removed": 1, "modified": 0},
            {"section": "Shipping options", "status": "added", "added": 1, "removed": 0, "modified": 0},
        ],
        "rows": rows,
    }


class FakeApi:
    """Backend giả: trả dữ liệu cố định và ghi lại các request so sánh frontend đã gửi."""

    def __init__(self, versions=VERSIONS, comparison_error=None):
        self.versions = versions
        self.comparison_error = comparison_error   # (HTTP status, JSON body)
        self.comparisons = []                      # (from, to) of every comparison request

    def handle(self, route):
        request = route.request
        url = urllib.parse.urlsplit(request.url)
        path, query = url.path, urllib.parse.parse_qs(url.query)
        key = (request.method, path)
        workflow = f"/api/document-workflows/{WORKFLOW_ID}"

        if key == ("GET", "/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-ld183"})
        if key == ("GET", "/api/auth/me"):
            return route.fulfill(status=200, json={"id": USER_ID, "email": "ld183@example.com", "role": "DEVELOPER"})
        if key == ("GET", f"/api/workspaces/{WORKSPACE_ID}/repositories"):
            return route.fulfill(status=200, json=[{
                "id": REPOSITORY_ID, "workspaceId": WORKSPACE_ID, "githubRepoId": 183,
                "fullName": "acme/shop", "defaultBranch": "main", "privateRepo": False,
                "status": "CONNECTED", "lastSyncedAt": "2026-11-10T08:00:00Z",
            }])
        if key == ("GET", f"/api/repositories/{REPOSITORY_ID}/documentation"):
            return route.fulfill(status=200, json=[])
        if key == ("GET", "/api/documentation/templates"):
            return route.fulfill(status=200, json=[{
                "id": "default", "name": "Standard technical docs", "description": "",
                "instructions": "", "sections": ["Overview"], "built_in": True,
            }])
        if key == ("GET", "/api/document-workflows/history-accessible"):
            return route.fulfill(status=200, json={
                "content": [{"id": WORKFLOW_ID, "documentId": DOCUMENT_ID, "documentTitle": "Cart",
                             "status": "DRAFT"}],
                "page": 0, "size": 20, "totalElements": 1, "totalPages": 1, "first": True, "last": True,
            })
        if key == ("GET", f"{workflow}/history"):
            return route.fulfill(status=200, json=[])
        if key == ("GET", f"{workflow}/versions"):
            return route.fulfill(status=200, json=self.versions)
        if key == ("GET", f"{workflow}/comparison"):
            pair = (int(query["from"][0]), int(query["to"][0]))
            self.comparisons.append(pair)
            if self.comparison_error:
                status, body = self.comparison_error
                return route.fulfill(status=status, json=body)
            return route.fulfill(status=200, json=comparison(*pair))
        if key == ("POST", f"/api/repositories/{REPOSITORY_ID}/documentation/generate"):
            return route.fulfill(status=202, json={"id": JOB_ID, "status": "pending"})
        if key == ("GET", f"/api/documentation/jobs/{JOB_ID}"):
            return route.fulfill(status=200, json={"id": JOB_ID, "status": "completed", "progress": 1.0})
        if key == ("GET", f"/api/documentation/jobs/{JOB_ID}/result"):
            return route.fulfill(status=200, content_type="text/markdown; charset=utf-8", body=SESSION_MARKDOWN)
        if key == ("GET", f"/api/documentation/jobs/{JOB_ID}/report"):
            return route.fulfill(status=200, json={"files": []})
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {request.method} {path}"})


SESSION_MARKDOWN = "\n".join([
    "# acme/shop", "", "The cart total includes VAT.", "", "## Classes", "", "- create_order", "- cancel_order",
])


def open_documentation_page(page: Page, api: FakeApi) -> None:
    page.add_init_script(f"window.sessionStorage.setItem('livingdocs.userId', '{USER_ID}')")
    page.route("**/api/**", api.handle)
    page.goto(FRONTEND_URL + "/")
    open_screen(page, "Generated Documents")
    expect(page.get_by_role("heading", name="Documentation Management")).to_be_visible()


def comparison_section(page: Page):
    return page.locator(".documentation-version-comparison")


# ---------- LD-184 chọn version ----------

def test_default_compares_the_current_version_with_the_previous_one(page: Page):
    api = FakeApi()
    open_documentation_page(page, api)
    section = comparison_section(page)

    expect(section.get_by_role("heading", name="Compare document versions")).to_be_visible()
    expect(section.locator("#compare-from-version")).to_have_value("2")
    expect(section.locator("#compare-to-version")).to_have_value("3")
    expect(section.get_by_role("columnheader", name="Version 2 · superseded")).to_be_visible()
    expect(section.get_by_role("columnheader", name="Version 3 · current")).to_be_visible()
    assert api.comparisons == [(2, 3)]


def test_any_two_versions_can_be_chosen_and_swapped(page: Page):
    api = FakeApi()
    open_documentation_page(page, api)
    section = comparison_section(page)
    expect(section.locator(".diff-stats")).to_be_visible()

    section.locator("#compare-from-version").select_option("1")
    expect(section.get_by_role("columnheader", name="Version 1 · superseded")).to_be_visible()
    section.get_by_role("button", name="Swap versions").click()
    expect(section.locator("#compare-from-version")).to_have_value("3")
    expect(section.locator("#compare-to-version")).to_have_value("1")
    expect(section.get_by_role("columnheader", name="Version 3 · current")).to_be_visible()
    assert api.comparisons == [(2, 3), (1, 3), (3, 1)]


def test_same_version_twice_is_not_sent(page: Page):
    api = FakeApi()
    open_documentation_page(page, api)
    section = comparison_section(page)
    expect(section.locator(".diff-stats")).to_be_visible()

    section.locator("#compare-from-version").select_option("3")
    expect(section.get_by_text("Select two different versions to compare.")).to_be_visible()
    expect(section.locator(".diff-view")).to_have_count(0)
    section.locator("#compare-to-version").select_option("")
    expect(section.get_by_text("Select a version to display the comparison.")).to_be_visible()
    assert api.comparisons == [(2, 3)]


def test_a_single_version_asks_to_create_one_first(page: Page):
    api = FakeApi(versions=[version(1, "current")])
    open_documentation_page(page, api)

    expect(comparison_section(page).get_by_text("Create a version first to enable comparison.")).to_be_visible()
    expect(comparison_section(page).locator("select")).to_have_count(0)
    assert api.comparisons == []


def test_backend_error_is_shown_not_hidden(page: Page):
    api = FakeApi(comparison_error=(409, {"code": "DOCUMENT_COMPARISON_UNAVAILABLE",
                                          "message": "Create a version first to enable comparison."}))
    open_documentation_page(page, api)

    expect(comparison_section(page).get_by_role("alert")).to_be_visible()
    expect(comparison_section(page).locator(".diff-view")).to_have_count(0)


# ---------- LD-186 thêm / xoá, LD-187 sửa ----------

def test_added_removed_and_modified_content_is_marked(page: Page):
    open_documentation_page(page, FakeApi())
    section = comparison_section(page)

    expect(section.locator(".diff-stats")).to_have_text("1 added · 1 removed · 1 modified · 12 unchanged lines")
    expect(section.locator(".diff-removed")).to_have_count(1)
    expect(section.locator(".diff-removed")).to_contain_text("## Legacy")
    expect(section.locator(".diff-added")).to_have_count(1)
    expect(section.locator(".diff-added")).to_contain_text("## Shipping options")
    expect(section.locator(".diff-modified")).to_have_count(2)            # old and new side of one row
    expect(section.locator(".diff-inline-changed")).to_have_text(" and shipping")
    expect(section.get_by_role("cell", name="Removed line 14")).to_be_visible()
    expect(section.get_by_role("cell", name="Added line 14")).to_be_visible()

    sections = section.get_by_role("list", name="Changed sections")
    expect(sections.get_by_role("listitem")).to_have_count(3)
    expect(sections).to_contain_text("Legacy removed")
    expect(sections).to_contain_text("Shipping options added")
    expect(sections).to_contain_text("Cart modified (+0 / −0 / ~1)")


def test_long_unchanged_runs_are_folded_and_can_be_shown(page: Page):
    open_documentation_page(page, FakeApi())
    section = comparison_section(page)

    fold = section.get_by_role("button", name="Show 4 unchanged lines")
    expect(fold).to_be_visible()
    expect(section.get_by_text("Unchanged paragraph 5.")).to_have_count(0)
    fold.click()
    expect(section.get_by_text("Unchanged paragraph 5.")).to_have_count(2)   # old and new side
    expect(section.locator(".diff-fold")).to_have_count(0)


# ---------- Tab Compare trong phiên (dùng chung DiffView) ----------

def test_session_compare_tab_uses_the_same_view(page: Page):
    open_documentation_page(page, FakeApi(versions=[]))
    page.get_by_role("button", name="Generate documentation").click()
    expect(page.get_by_role("heading", name="Generated Documentation")).to_be_visible(timeout=10_000)

    page.get_by_role("button", name="Create version").click()
    page.locator("#documentation-editor").fill(SESSION_MARKDOWN.replace(
        "The cart total includes VAT.", "The cart total includes VAT and shipping.") + "\n- refund_order")
    page.get_by_role("tab", name="Compare").click()
    page.locator("#compare-version").select_option(index=1)

    view = page.locator(".documentation-diff.diff-view").last
    expect(view.locator(".diff-inline-changed")).to_have_text(" and shipping")
    expect(view.locator(".diff-added")).to_contain_text("- refund_order")
    expect(page.locator(".diff-stats").last).to_have_text("1 added · 0 removed · 1 modified · 7 unchanged lines")
