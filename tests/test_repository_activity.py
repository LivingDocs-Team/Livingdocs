"""LD-73: kiểm thử màn hình "PR & Commit List" (LD-68) trong Repository Management.

Test chạy trên giao diện thật trong trình duyệt (Playwright). Mọi request /api/** được giả lập,
nên chỉ cần frontend chạy ở FRONTEND_URL (mặc định http://localhost:3000), không cần backend.

Chạy trên máy:
    cd frontend && npm ci && npm run build && npx vite preview --port 3000
    python -m pytest -o addopts="" -v tests/test_repository_activity.py
"""
import os
import urllib.request

import pytest

pytest.importorskip("pytest_playwright", reason="cần cài pytest-playwright để chạy test giao diện")

from playwright.sync_api import Page, expect  # noqa: E402

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
USER_ID = "42"
WORKSPACE_ID = f"ws-{USER_ID}"
REPOSITORY_ID = "6c2d7f1e-8e4b-4d3c-8b9f-680680680680"

PULL_REQUESTS = [
    {"number": 8, "title": "Add invoice export", "state": "open", "merged": False, "authorLogin": "lamhuyy",
     "headRef": "feature/export", "headSha": "b" * 40, "baseRef": "main",
     "htmlUrl": "https://github.com/acme/shop/pull/8", "createdAt": "2026-11-06T02:00:00Z",
     "updatedAt": "2026-11-06T03:00:00Z", "mergedAt": None, "source": "WEBHOOK"},
    {"number": 7, "title": "Fix totals", "state": "closed", "merged": True, "authorLogin": "d3r-bbb",
     "headRef": "fix/totals", "headSha": "c" * 40, "baseRef": "main",
     "htmlUrl": "https://github.com/acme/shop/pull/7", "createdAt": "2026-11-05T02:00:00Z",
     "updatedAt": "2026-11-05T05:00:00Z", "mergedAt": "2026-11-05T05:00:00Z", "source": "SYNC"},
]
COMMITS = [
    {"sha": "abcdef1" + "0" * 33, "branch": "main", "message": "Fix invoice totals\n\nRounds to cents.",
     "authorName": "Hai Dang", "authorLogin": "d3r-bbb", "committedAt": "2026-11-06T03:01:00Z",
     "htmlUrl": "https://github.com/acme/shop/commit/abcdef1", "source": "WEBHOOK"},
]


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
    """Backend giả cho trang Repository Management; activity_error = (HTTP status, JSON body)."""

    def __init__(self, pull_requests=PULL_REQUESTS, commits=COMMITS, activity_error=None, source_changes=()):
        self.pull_requests = pull_requests
        self.commits = commits
        self.activity_error = activity_error
        self.source_changes = list(source_changes)
        self.requests = []

    def handle(self, route):
        request = route.request
        path = request.url.split("?", 1)[0].removeprefix(FRONTEND_URL)
        self.requests.append((request.method, path))

        if (request.method, path) == ("GET", "/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-ld68"})
        if (request.method, path) == ("GET", "/api/auth/me"):
            return route.fulfill(status=200, json={"id": USER_ID, "email": "ld68@example.com"})
        if (request.method, path) == ("GET", "/api/managed-workspaces"):
            return route.fulfill(status=200, json=[])  # LD-267: chỉ có workspace cá nhân
        if (request.method, path) == ("GET", "/api/github/connection"):
            return route.fulfill(status=200, json={"connected": True, "githubLogin": "d3r-bbb", "status": "ACTIVE"})
        if (request.method, path) == ("GET", "/api/github/repos/available"):
            return route.fulfill(status=200, json=[])
        if (request.method, path) == ("GET", f"/api/workspaces/{WORKSPACE_ID}/repositories"):
            return route.fulfill(status=200, json=[{
                "id": REPOSITORY_ID, "workspaceId": WORKSPACE_ID, "githubRepoId": 4242,
                "fullName": "acme/shop", "defaultBranch": "main", "privateRepo": False,
                "status": "CONNECTED", "lastSyncedAt": "2026-11-06T03:05:00Z",
            }])
        if request.method == "GET" and path in (f"/api/repositories/{REPOSITORY_ID}/pull-requests",
                                                f"/api/repositories/{REPOSITORY_ID}/commits"):
            if self.activity_error:
                status, body = self.activity_error
                return route.fulfill(status=status, json=body)
            data = self.pull_requests if path.endswith("/pull-requests") else self.commits
            return route.fulfill(status=200, json=data)
        if (request.method, path) == ("GET", f"/api/repositories/{REPOSITORY_ID}/source-changes"):
            return route.fulfill(status=200, json=self.source_changes)
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {request.method} {path}"})


def open_workspace_repositories(page: Page, api: FakeApi) -> None:
    """Đăng nhập sẵn rồi mở tab Workspace của Repository Management."""
    page.add_init_script(f"window.sessionStorage.setItem('livingdocs.userId', '{USER_ID}')")
    page.route("**/api/**", api.handle)
    page.goto(FRONTEND_URL + "/")
    page.get_by_role("button", name="Repository Management").first.click()
    expect(page.get_by_role("heading", name="Repository Management")).to_be_visible()
    page.get_by_role("button", name="Workspace (1)").click()
    expect(page.get_by_role("heading", name="acme/shop")).to_be_visible()


def activity(page: Page):
    return page.get_by_role("region", name="Pull requests and commits of acme/shop")


def test_pull_requests_and_commits_are_listed_and_panel_can_be_hidden(page: Page):
    api = FakeApi()
    open_workspace_repositories(page, api)

    page.get_by_role("button", name="PRs & commits").click()

    panel = activity(page)
    expect(panel.get_by_role("heading", name="Pull requests (2)")).to_be_visible()
    expect(panel.get_by_role("link", name="#8 Add invoice export")).to_have_attribute(
        "href", "https://github.com/acme/shop/pull/8")
    expect(panel.get_by_role("listitem").filter(has_text="#8 Add invoice export")).to_contain_text("Open")
    expect(panel.get_by_role("listitem").filter(has_text="#7 Fix totals")).to_contain_text("Merged")
    expect(panel.get_by_text("feature/export → main · lamhuyy", exact=False)).to_be_visible()

    expect(panel.get_by_role("heading", name="Commits (1)")).to_be_visible()
    commit = panel.get_by_role("listitem").filter(has_text="abcdef1")
    expect(commit.get_by_role("link", name="Fix invoice totals")).to_be_visible()  # chỉ dòng đầu của message
    expect(commit).to_contain_text("main · d3r-bbb")
    assert ("GET", f"/api/repositories/{REPOSITORY_ID}/pull-requests") in api.requests
    assert ("GET", f"/api/repositories/{REPOSITORY_ID}/commits") in api.requests

    page.get_by_role("button", name="Hide PRs & commits").click()
    expect(activity(page)).to_have_count(0)


def test_repository_without_activity_shows_empty_lists(page: Page):
    open_workspace_repositories(page, FakeApi(pull_requests=[], commits=[]))

    page.get_by_role("button", name="PRs & commits").click()

    expect(activity(page).get_by_text("No pull requests received yet.")).to_be_visible()
    expect(activity(page).get_by_text("No commits received yet.")).to_be_visible()


def test_activity_error_is_shown_in_english(page: Page):
    service_message = "Repository này không thuộc kết nối GitHub của bạn."
    open_workspace_repositories(page, FakeApi(
        activity_error=(403, {"status": 403, "code": "FORBIDDEN", "message": service_message})))

    page.get_by_role("button", name="PRs & commits").click()

    expect(activity(page).get_by_role("alert")).to_have_text("You do not have access to this item.")
    expect(page.get_by_text(service_message)).to_have_count(0)


# ---------- LD-122 / LD-126 / LD-127: tài liệu bị ảnh hưởng của source change ----------

def source_change(sha, **extra):
    change = {"id": f"change-{sha}", "trigger": "COMMIT", "commitSha": sha * 40, "pullRequestNumber": None,
              "status": "PENDING", "errorCode": None, "errorMessage": None,
              "createdAt": "2026-11-06T03:02:00Z", "updatedAt": "2026-11-06T03:02:00Z",
              "files": [{"path": "shop/cart.py", "change": "MODIFIED", "entities": []}],
              "documentsStatus": "FOUND", "documentsErrorCode": None, "documentsErrorMessage": None,
              "affectedDocuments": []}
    change.update(extra)
    return change


AFFECTED = [
    {"documentId": "doc-1", "title": "acme/shop", "version": 2, "section": "shop/cart.py",
     "documentsFile": "shop/cart.py", "dependency": "DIRECT",
     "reasons": ["documents changed file shop/cart.py"], "evidence": []},
    {"documentId": "doc-1", "title": "acme/shop", "version": 2, "section": "shop/checkout.py",
     "documentsFile": "shop/checkout.py", "dependency": "DEPENDENT",
     "reasons": ["mentions `get_cart_total`"],
     "evidence": [{"target": "get_cart_total", "kind": "name", "line": 14,
                   "excerpt": "Charge the customer get_cart_total(cart_id) of the cart."}]},
]


def test_affected_documentation_is_listed_with_dependency_and_evidence(page: Page):
    open_workspace_repositories(page, FakeApi(source_changes=[source_change("a", affectedDocuments=AFFECTED)]))

    page.get_by_role("button", name="PRs & commits").click()

    expect(activity(page).get_by_role("heading", name="Source changes (1)")).to_be_visible()
    docs = activity(page).get_by_role("list", name="Documentation affected by aaaaaaa")
    direct = docs.get_by_role("listitem").filter(has_text="shop/cart.py").first
    expect(direct).to_contain_text("Direct")
    expect(direct).to_contain_text("documents changed file shop/cart.py")
    dependent = docs.get_by_role("listitem").filter(has_text="shop/checkout.py").first
    expect(dependent).to_contain_text("Dependent")
    expect(dependent).to_contain_text("mentions `get_cart_total`")
    expect(dependent).to_contain_text("Line 14: Charge the customer get_cart_total(cart_id) of the cart.")


def test_source_change_documentation_states_are_explained(page: Page):
    open_workspace_repositories(page, FakeApi(source_changes=[
        source_change("b"),
        source_change("c", documentsStatus="FAILED", documentsErrorCode="AI_SERVICE_UNAVAILABLE",
                      documentsErrorMessage="The AI service could not check which documentation is affected."),
        source_change("d", status="FAILED", errorCode="GITHUB_UNAVAILABLE", errorMessage="GitHub is unavailable.",
                      files=[], documentsStatus=None),
    ]))

    page.get_by_role("button", name="PRs & commits").click()

    panel = activity(page)
    expect(panel.get_by_role("heading", name="Source changes (3)")).to_be_visible()
    expect(panel.get_by_text("No documentation is affected.")).to_be_visible()
    expect(panel.get_by_role("alert")).to_have_text(
        "Affected documentation could not be checked: The AI service could not check which documentation is affected.")
    expect(panel.get_by_text("Changes could not be detected: GitHub is unavailable.")).to_be_visible()
