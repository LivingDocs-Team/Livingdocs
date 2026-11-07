import pytest
from playwright.sync_api import Page, expect

REPOSITORY_ID = "11111111-1111-1111-1111-111111111111"
WORKSPACE_ID = "ws-42"

def test_frontend_homepage_title(page: Page):
    """LD-373: Kiểm tra tiêu đề giao diện Frontend Dashboard LivingDocs"""
    page.goto("http://localhost:3000/")
    expect(page).to_have_title("LivingDocs - Automated Documentation Generator")

def test_github_oauth_failure_returns_to_login_with_guidance(page: Page):
    page.route("**/api/auth/me", lambda route: route.fulfill(status=401))
    page.goto("http://localhost:3000/?oauth=error")

    expect(page.get_by_role("heading", name="LivingDocs")).to_be_visible()
    expect(page.get_by_role("alert")).to_contain_text(
        "sign in with your password and connect GitHub from GitHub Connection"
    )


def test_frontend_upload_repo_flow(page: Page):
    """LD-388: Exercise frontend API requests through sync and documentation generation."""
    calls = set()
    workspace_has_repository = False
    repository_synced = False

    def mock_api(route):
        nonlocal workspace_has_repository
        nonlocal repository_synced
        request = route.request
        path = request.url.split("?", 1)[0]
        calls.add((request.method, path))
        assert request.headers.get("x-user-id") is None
        if request.method in {"POST", "DELETE", "PUT", "PATCH"}:
            assert request.headers.get("x-xsrf-token") == "csrf-test-token"

        if path.endswith("/api/auth/csrf") and request.method == "GET":
            return route.fulfill(status=200, json={"token": "csrf-test-token"})

        if path.endswith("/api/auth/login") and request.method == "POST":
            return route.fulfill(status=200, json={
                "message": "Login successful", "id": 42, "email": "user@example.test",
                "username": "test-user", "firstName": "Test", "lastName": "User", "role": "DEVELOPER",
            })
        if path.endswith("/api/github/connection") and request.method == "GET":
            return route.fulfill(status=200, json={"connected": True, "githubLogin": "test-user", "status": "ACTIVE"})
        if path.endswith("/api/github/repos/available") and request.method == "GET":
            return route.fulfill(status=200, json=[{
                "githubRepoId": 4242, "fullName": "acme/shop", "privateRepo": False,
                "defaultBranch": "main", "htmlUrl": "https://github.com/acme/shop",
            }])
        if path.endswith(f"/api/workspaces/{WORKSPACE_ID}/repositories") and request.method == "GET":
            items = ([{
                "id": REPOSITORY_ID, "githubRepoId": 4242, "workspaceId": WORKSPACE_ID,
                "fullName": "acme/shop", "defaultBranch": "main", "privateRepo": False,
                "status": "CONNECTED",
                "lastSyncedAt": "2026-10-21T12:00:00Z" if repository_synced else None,
            }] if workspace_has_repository else [])
            return route.fulfill(status=200, json=items)
        if path.endswith(f"/api/workspaces/{WORKSPACE_ID}/repositories") and request.method == "POST":
            workspace_has_repository = True
            return route.fulfill(status=201, json=[{
                "id": REPOSITORY_ID, "githubRepoId": 4242, "workspaceId": WORKSPACE_ID,
                "fullName": "acme/shop", "defaultBranch": "main", "privateRepo": False,
                "status": "CONNECTED", "lastSyncedAt": None,
            }])
        if path.endswith(f"/api/repositories/{REPOSITORY_ID}/sync") and request.method == "POST":
            repository_synced = True
            return route.fulfill(status=200, json={"syncedAt": "2026-10-21T12:00:00Z"})
        if path.endswith(f"/api/repositories/{REPOSITORY_ID}/documentation/generate") and request.method == "POST":
            return route.fulfill(status=202, json={"id": "job-123", "status": "pending", "target": "acme/shop"})
        if path.endswith("/api/documentation/jobs/job-123") and request.method == "GET":
            return route.fulfill(status=200, json={"id": "job-123", "status": "completed", "progress": 1.0})
        if path.endswith("/api/documentation/jobs/job-123/result") and request.method == "GET":
            return route.fulfill(status=200, content_type="text/markdown", body="# acme/shop\n\nGenerated from analyzed source.")
        if path.endswith("/api/documentation/jobs/job-123/report") and request.method == "GET":
            return route.fulfill(status=200, json={"files": [{"entities": [{
                "name": "ShopService", "evidence": [{"path": "src/shop.py", "line_start": 4, "line_end": 12}],
            }]}]})
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {request.method} {path}"})

    page.route("**/api/**", mock_api)
    page.goto("http://localhost:3000/")

    page.get_by_label("Email").fill("user@example.test")
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("status").filter(has_text="Signed in successfully")).to_be_visible()

    page.get_by_role("button", name="Repository Management").first.click()
    expect(page.get_by_role("heading", name="Repository Management")).to_be_visible()
    page.get_by_role("checkbox", name="Select acme/shop").check()
    page.get_by_role("button", name="Add selected to workspace").click()
    expect(page.get_by_role("status").filter(has_text="Selected repositories added")).to_be_visible()

    page.get_by_role("button", name="Workspace (1)").click()
    page.get_by_role("button", name="Sync now").click()
    expect(page.get_by_role("status").filter(has_text="acme/shop synchronized")).to_be_visible()

    page.get_by_role("button", name="Documentation Management").first.click()
    page.get_by_role("button", name="Generate documentation").click()
    expect(page.get_by_role("heading", name="Generated Documentation")).to_be_visible(timeout=10_000)
    expect(page.locator("#documentation-editor")).to_have_value("# acme/shop\n\nGenerated from analyzed source.")
    expect(page.get_by_text("ShopService — src/shop.py:4-12")).to_be_visible()

    expected_calls = {
        ("POST", "http://localhost:3000/api/auth/login"),
        ("GET", "http://localhost:3000/api/github/connection"),
        ("GET", "http://localhost:3000/api/github/repos/available"),
        ("POST", f"http://localhost:3000/api/workspaces/{WORKSPACE_ID}/repositories"),
        ("POST", f"http://localhost:3000/api/repositories/{REPOSITORY_ID}/sync"),
        ("POST", f"http://localhost:3000/api/repositories/{REPOSITORY_ID}/documentation/generate"),
        ("GET", "http://localhost:3000/api/documentation/jobs/job-123"),
        ("GET", "http://localhost:3000/api/documentation/jobs/job-123/result"),
        ("GET", "http://localhost:3000/api/documentation/jobs/job-123/report"),
    }
    assert expected_calls <= calls


def test_documentation_search_shows_documentation_and_code_navigation(page: Page):
    search_calls = []

    def mock_api(route):
        request = route.request
        path = request.url.split("?", 1)[0]
        if path.endswith("/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-test-token"})
        if path.endswith("/api/auth/login"):
            return route.fulfill(status=200, json={
                "message": "Login successful", "id": 42, "email": "user@example.test",
                "username": "test-user", "firstName": "Test", "lastName": "User", "role": "DEVELOPER",
            })
        if path.endswith("/api/workspaces/ws-42/repositories"):
            return route.fulfill(status=200, json=[{
                "id": REPOSITORY_ID, "workspaceId": WORKSPACE_ID, "fullName": "acme/shop",
                "defaultBranch": "main", "status": "CONNECTED",
            }])
        if path.endswith(f"/api/repositories/{REPOSITORY_ID}/documentation/search"):
            search_calls.append(request.url)
            return route.fulfill(status=200, json={"query": "checkout", "total": 2, "results": [
                {"id": "doc:src/Checkout.java:CheckoutService", "type": "documentation",
                 "title": "CheckoutService", "summary": "Handles checkout requests.",
                 "repositoryName": "acme/shop", "path": "src/Checkout.java", "language": "java",
                 "line": 8, "url": "https://github.com/acme/shop/blob/main/src/Checkout.java#L8", "score": 107},
                {"id": "code:src/Checkout.java:CheckoutService", "type": "code",
                 "title": "CheckoutService", "summary": "class", "repositoryName": "acme/shop",
                 "path": "src/Checkout.java", "language": "java", "line": 8,
                 "url": "https://github.com/acme/shop/blob/main/src/Checkout.java#L8", "score": 107},
            ]})
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {request.method} {path}"})

    page.route("**/api/**", mock_api)
    page.goto("http://localhost:3000/")
    page.get_by_label("Email").fill("user@example.test")
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("button", name="Documentation Search").click()
    page.get_by_label("Search terms").fill("checkout")
    page.get_by_role("button", name="Search", exact=True).click()

    expect(page.get_by_role("heading", name="Documentation Search")).to_be_visible()
    expect(page.get_by_role("heading", name="CheckoutService").first).to_be_visible()
    expect(page.get_by_text("Handles checkout requests.")).to_be_visible()
    expect(page.get_by_role("link", name="View source ↗").first).to_have_attribute(
        "href", "https://github.com/acme/shop/blob/main/src/Checkout.java#L8"
    )
    expect(page.get_by_role("link", name="View source ↗").first).to_have_attribute("target", "_blank")
    assert len(search_calls) == 1


def test_documentation_search_validates_empty_query(page: Page):
    def mock_api(route):
        path = route.request.url.split("?", 1)[0]
        if path.endswith("/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-test-token"})
        if path.endswith("/api/auth/login"):
            return route.fulfill(status=200, json={
                "message": "Login successful", "id": 42, "email": "user@example.test",
                "username": "test-user", "firstName": "Test", "lastName": "User", "role": "DEVELOPER",
            })
        if path.endswith("/api/workspaces/ws-42/repositories"):
            return route.fulfill(status=200, json=[{"id": REPOSITORY_ID, "fullName": "acme/shop"}])
        return route.fulfill(status=404, json={"message": "Unexpected API request"})

    page.route("**/api/**", mock_api)
    page.goto("http://localhost:3000/")
    page.get_by_label("Email").fill("user@example.test")
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("button", name="Documentation Search").click()
    page.get_by_role("button", name="Search", exact=True).click()
    expect(page.get_by_role("alert")).to_have_text("Enter a search term.")


def test_documentation_search_repository_selection_and_isolation(page: Page):
    repository_b = "22222222-2222-2222-2222-222222222222"
    search_requests = []

    def mock_api(route):
        request = route.request
        path = request.url.split("?", 1)[0]
        if path.endswith("/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-test-token"})
        if path.endswith("/api/auth/login"):
            return route.fulfill(status=200, json={
                "message": "Login successful", "id": 42, "email": "user@example.test",
                "username": "test-user", "firstName": "Test", "lastName": "User", "role": "DEVELOPER",
            })
        if path.endswith("/api/workspaces/ws-42/repositories"):
            return route.fulfill(status=200, json=[
                {"id": REPOSITORY_ID, "fullName": "acme/alpha"},
                {"id": repository_b, "fullName": "acme/beta"},
            ])
        if path.endswith("/documentation/search"):
            search_requests.append(request.url)
            return route.fulfill(status=200, json={"query": "checkout", "total": 1, "results": [{
                "id": "doc-beta", "type": "documentation", "title": "BetaCheckout",
                "summary": "Beta repository checkout flow.", "repositoryId": repository_b,
                "repositoryName": "acme/beta", "path": "src/beta.py", "language": "python",
                "line": 11, "url": "https://github.com/acme/beta/blob/main/src/beta.py#L11", "score": 108,
            }]})
        return route.fulfill(status=404, json={"message": f"Unexpected request: {path}"})

    page.route("**/api/**", mock_api)
    page.goto("http://localhost:3000/")
    page.get_by_label("Email").fill("user@example.test")
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("button", name="Documentation Search").click()
    expect(page.get_by_label("Repository")).to_have_value(REPOSITORY_ID)
    page.get_by_label("Repository").select_option(repository_b)
    page.get_by_label("Search terms").fill("checkout")
    page.get_by_role("button", name="Search", exact=True).click()

    expect(page.get_by_role("heading", name="BetaCheckout")).to_be_visible()
    expect(page.get_by_text("acme/beta · python")).to_be_visible()
    assert len(search_requests) == 1
    assert f"/api/repositories/{repository_b}/documentation/search?q=checkout" in search_requests[0]
    assert REPOSITORY_ID not in search_requests[0]


def test_documentation_search_loading_and_empty_results(page: Page):
    page.add_init_script("""
        (() => {
          const originalFetch = window.fetch.bind(window);
          window.fetch = (input, init) => {
            const url = typeof input === 'string' ? input : input.url;
            if (url.includes('/documentation/search')) {
              window.__searchRequestStarted = true;
              return new Promise((resolve, reject) => {
                window.__continueSearch = () => originalFetch(input, init).then(resolve, reject);
              });
            }
            return originalFetch(input, init);
          };
        })();
    """)

    def mock_api(route):
        path = route.request.url.split("?", 1)[0]
        if path.endswith("/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-test-token"})
        if path.endswith("/api/auth/login"):
            return route.fulfill(status=200, json={
                "message": "Login successful", "id": 42, "email": "user@example.test",
                "username": "test-user", "firstName": "Test", "lastName": "User", "role": "DEVELOPER",
            })
        if path.endswith("/api/workspaces/ws-42/repositories"):
            return route.fulfill(status=200, json=[{"id": REPOSITORY_ID, "fullName": "acme/shop"}])
        if path.endswith("/documentation/search"):
            return route.fulfill(status=200, json={"query": "missing", "total": 0, "results": []})
        return route.fulfill(status=404, json={"message": f"Unexpected request: {path}"})

    page.route("**/api/**", mock_api)
    page.goto("http://localhost:3000/")
    page.get_by_label("Email").fill("user@example.test")
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("button", name="Documentation Search").click()
    page.get_by_label("Search terms").fill("missing")
    page.get_by_role("button", name="Search", exact=True).click()

    expect(page.get_by_role("status").filter(has_text="Searching the selected repository"))\
        .to_be_visible(timeout=2_000)
    assert page.evaluate("window.__searchRequestStarted") is True
    page.evaluate("window.__continueSearch()")
    expect(page.get_by_role("status").filter(has_text="Searching the selected repository"))\
        .not_to_be_visible(timeout=2_000)
    expect(page.get_by_role("heading", name="No results found")).to_be_visible(timeout=5_000)


def test_documentation_search_displays_api_errors(page: Page):
    def mock_api(route):
        path = route.request.url.split("?", 1)[0]
        if path.endswith("/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-test-token"})
        if path.endswith("/api/auth/login"):
            return route.fulfill(status=200, json={
                "message": "Login successful", "id": 42, "email": "user@example.test",
                "username": "test-user", "firstName": "Test", "lastName": "User", "role": "DEVELOPER",
            })
        if path.endswith("/api/workspaces/ws-42/repositories"):
            return route.fulfill(status=200, json=[{"id": REPOSITORY_ID, "fullName": "acme/shop"}])
        if path.endswith("/documentation/search"):
            return route.fulfill(status=502, json={
                "code": "ANALYZER_FAILED", "message": "The code analyzer is unavailable for documentation search."
            })
        return route.fulfill(status=404, json={"message": f"Unexpected request: {path}"})

    page.route("**/api/**", mock_api)
    page.goto("http://localhost:3000/")
    page.get_by_label("Email").fill("user@example.test")
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("button", name="Documentation Search").click()
    page.get_by_label("Search terms").fill("checkout")
    page.get_by_role("button", name="Search", exact=True).click()
    expect(page.get_by_role("alert")).to_have_text(
        "The code analyzer is unavailable for documentation search."
    )


def test_login_can_open_github_connection_and_view_status(page: Page):
    def mock_api(route):
        path = route.request.url.split("?", 1)[0]
        if path.endswith("/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-test-token"})
        if path.endswith("/api/auth/login"):
            return route.fulfill(status=200, json={
                "message": "Login successful", "id": 42, "email": "user@example.test",
                "username": "test-user", "firstName": "Test", "lastName": "User", "role": "DEVELOPER",
            })
        if path.endswith("/api/github/connection"):
            return route.fulfill(status=200, json={
                "connected": True, "githubLogin": "test-user", "status": "ACTIVE"
            })
        return route.fulfill(status=404, json={"message": f"Unexpected request: {path}"})

    page.route("**/api/**", mock_api)
    page.goto("http://localhost:3000/")
    page.get_by_label("Email").fill("user@example.test")
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("status").filter(has_text="Signed in successfully")).to_be_visible()
    page.get_by_role("button", name="GitHub Connection").click()
    expect(page.get_by_role("heading", name="GitHub Integration")).to_be_visible()
    expect(page.get_by_role("status").filter(has_text="Connected as @test-user")).to_be_visible()
