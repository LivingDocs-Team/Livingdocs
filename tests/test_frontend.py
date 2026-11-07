import pytest
import re
from playwright.sync_api import Page, expect

REPOSITORY_ID = "11111111-1111-1111-1111-111111111111"
WORKSPACE_ID = "ws-42"

def test_frontend_homepage_title(page: Page):
    """LD-373: Kiểm tra tiêu đề giao diện Frontend Dashboard LivingDocs"""
    page.goto("http://localhost:3000/")
    expect(page).to_have_title("LivingDocs - Automated Documentation Generator")


def test_ld211_documentation_code_relationship_flow(page: Page):
    """LD-211: Exercise linking and navigating between generated docs and code entities."""
    calls = set()
    workspace_has_repository = False
    repository_synced = False
    relationships_saved = False

    def mock_api(route):
        nonlocal workspace_has_repository
        nonlocal repository_synced
        nonlocal relationships_saved
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
            return route.fulfill(status=202, json={"id": "job-123", "documentId": "doc-123", "status": "pending", "target": "acme/shop"})
        if path.endswith(f"/api/repositories/{REPOSITORY_ID}/code-entities") and request.method == "GET":
            return route.fulfill(status=200, json=[{
                "id": "entity-123", "entityType": "class", "name": "ShopService",
                "path": "src/shop.py", "lineStart": 4, "lineEnd": 12,
                "sourceUrl": "https://github.com/acme/shop/blob/abc123/src/shop.py#L4-L12",
                "sourceCommit": "abc123",
            }])
        if path.endswith(f"/api/repositories/{REPOSITORY_ID}/documentation") and request.method == "GET":
            return route.fulfill(status=200, json=[{
                "id": "doc-123", "repositoryId": REPOSITORY_ID,
                "generationJobId": "job-123", "markdown": "# Saved shop documentation",
                "sourceCommit": "abc123", "createdAt": "2026-10-21T12:00:00Z",
            }])
        if path.endswith("/api/documentation/doc-123") and request.method == "GET":
            return route.fulfill(status=200, json={
                "id": "doc-123", "repositoryId": REPOSITORY_ID,
                "generationJobId": "job-123", "markdown": "# Saved shop documentation",
                "sourceCommit": "abc123", "createdAt": "2026-10-21T12:00:00Z",
            })
        if path.endswith("/api/documentation/doc-related") and request.method == "GET":
            return route.fulfill(status=200, json={
                "id": "doc-related", "repositoryId": REPOSITORY_ID,
                "generationJobId": "job-related", "markdown": "# Related document\n\nOpened from code entity.",
                "sourceCommit": "abc123", "createdAt": "2026-10-21T12:00:00Z",
            })
        if path.endswith("/api/documentation/doc-123/code-entities") and request.method == "GET":
            return route.fulfill(status=200, json=([{
                "id": "entity-123", "entityType": "class", "name": "ShopService",
                "path": "src/shop.py", "lineStart": 4, "lineEnd": 12,
                "sourceUrl": "https://github.com/acme/shop/blob/abc123/src/shop.py#L4-L12",
                "sourceCommit": "abc123",
            }] if relationships_saved else []))
        if path.endswith("/api/documentation/doc-related/code-entities") and request.method == "GET":
            return route.fulfill(status=200, json=[])
        if path.endswith("/api/documentation/doc-123/code-entities") and request.method == "PUT":
            relationships_saved = True
            assert request.post_data_json["codeEntityIds"] == ["entity-123"]
            return route.fulfill(status=200, json=[{
                "id": "entity-123", "entityType": "class", "name": "ShopService",
                "path": "src/shop.py", "lineStart": 4, "lineEnd": 12,
                "sourceUrl": "https://github.com/acme/shop/blob/abc123/src/shop.py#L4-L12",
                "sourceCommit": "abc123",
            }])
        if path.endswith("/api/documentation/code-entities/entity-123/documents") and request.method == "GET":
            return route.fulfill(status=200, json=([{
                "id": "doc-related", "repositoryId": REPOSITORY_ID,
                "generationJobId": "job-related", "markdown": "# Related document\n\nOpened from code entity.",
                "sourceCommit": "abc123", "createdAt": "2026-10-21T12:00:00Z",
            }] if relationships_saved else []))
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
    expect(page.get_by_role("heading", name="Saved documentation")).to_be_visible()
    page.get_by_role("button", name="Open document").click()
    expect(page.locator(".markdown-preview-content")).to_contain_text("Saved shop documentation")
    page.get_by_role("button", name="Generate documentation").click()
    expect(page.get_by_role("heading", name="Generated Documentation")).to_be_visible(timeout=10_000)
    expect(page.locator("#documentation-editor")).to_have_value("# acme/shop\n\nGenerated from analyzed source.")
    expect(page.get_by_text("ShopService — src/shop.py:4-12")).to_be_visible()
    expect(page.get_by_role("heading", name="Related source code")).to_be_visible()
    expect(page.get_by_role("link", name="Open source")).to_have_attribute(
        "href", "https://github.com/acme/shop/blob/abc123/src/shop.py#L4-L12"
    )
    page.get_by_label(re.compile("ShopService class")).check()
    page.get_by_role("button", name="Save code links").click()
    expect(page.get_by_role("status").filter(has_text="Related source code saved")).to_be_visible()
    page.get_by_role("button", name="Related documents").click()
    page.get_by_role("button", name="Open generated document").click()
    expect(page.locator(".markdown-preview-content")).to_contain_text("Related document")
    expect(page.locator(".markdown-preview-content")).to_contain_text("Opened from code entity.")

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
        ("GET", f"http://localhost:3000/api/repositories/{REPOSITORY_ID}/code-entities"),
        ("GET", f"http://localhost:3000/api/repositories/{REPOSITORY_ID}/documentation"),
        ("GET", "http://localhost:3000/api/documentation/doc-123"),
        ("GET", "http://localhost:3000/api/documentation/doc-related"),
        ("GET", "http://localhost:3000/api/documentation/doc-123/code-entities"),
        ("PUT", "http://localhost:3000/api/documentation/doc-123/code-entities"),
        ("GET", "http://localhost:3000/api/documentation/code-entities/entity-123/documents"),
    }
    assert expected_calls <= calls

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
