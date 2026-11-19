"""LD-403 frontend logic fixes, against the built frontend with every /api call mocked:

- signing out (Logout in the app shell) ends the session and returns to the public Home page
- removing a repository from a workspace asks for confirmation
- a documentation generation that was reset does not write its late result back over the screen
"""
import os

from playwright.sync_api import Page, expect

from rbac_nav import LOGIN_URL, open_screen, sign_in

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
USER = {"id": 42, "email": "user@example.test", "username": "user", "firstName": "Test",
        "lastName": "User", "role": "DEVELOPER"}
REPOSITORY_ID = "11111111-1111-4111-8111-111111111111"
REPOSITORY = {"id": REPOSITORY_ID, "githubRepoId": 4242, "fullName": "acme/shop", "privateRepo": False,
              "defaultBranch": "main", "status": "CONNECTED", "lastSyncedAt": "2026-11-10T10:00:00Z"}


class Api:
    """Mocked backend. `signed_in` decides whether /api/auth/me restores a session."""

    def __init__(self, signed_in=True, logout_status=200):
        self.signed_in = signed_in
        self.logout_status = logout_status
        self.requests = []
        self.job_polls = 0

    def handle(self, route):
        request = route.request
        path = request.url.split("?", 1)[0].removeprefix(FRONTEND_URL)
        self.requests.append((request.method, path))
        send = lambda status, payload=None: route.fulfill(status=status, json=payload if payload is not None else {})

        if (request.method, path) == ("GET", "/api/auth/me"):
            return send(200, USER) if self.signed_in else send(401)
        if (request.method, path) == ("GET", "/api/auth/csrf"):
            return send(200, {"token": "csrf-test"})
        if (request.method, path) == ("POST", "/api/auth/login"):
            self.signed_in = True
            return send(200, {"message": "Login successful", **USER})
        if (request.method, path) == ("POST", "/api/auth/logout"):
            if self.logout_status == 200:
                self.signed_in = False
            return send(self.logout_status, {"message": "Logout"})
        if (request.method, path) == ("GET", "/api/managed-workspaces"):
            return send(200, [])
        if (request.method, path) == ("GET", "/api/github/connection"):
            return send(200, {"connected": True, "githubLogin": "user", "status": "ACTIVE"})
        if (request.method, path) == ("GET", "/api/github/repos/available"):
            return send(200, [])
        if (request.method, path) == ("GET", "/api/workspaces/ws-42/repositories"):
            return send(200, [REPOSITORY])
        if (request.method, path) == ("DELETE", f"/api/repositories/{REPOSITORY_ID}"):
            return route.fulfill(status=204)
        if (request.method, path) == ("GET", "/api/documentation/templates"):
            return send(200, [])
        if (request.method, path) == ("GET", "/api/document-workflows/history-accessible"):
            return send(200, {"content": [], "page": 0, "size": 20, "totalElements": 0, "totalPages": 0,
                              "first": True, "last": True})
        # documentation generation: the job stays "running" for the first polls
        if (request.method, path) == ("POST", f"/api/repositories/{REPOSITORY_ID}/documentation/generate"):
            return send(202, {"id": "job-1", "status": "running", "progress": 0.1, "message": "Generating"})
        if (request.method, path) == ("GET", "/api/documentation/jobs/job-1"):
            self.job_polls += 1
            done = self.job_polls >= 3
            return send(200, {"id": "job-1", "status": "completed" if done else "running",
                              "progress": 1 if done else 0.4, "message": "Generating"})
        if (request.method, path) == ("GET", "/api/documentation/jobs/job-1/result"):
            return route.fulfill(status=200, body="# Shop guide\n", content_type="text/markdown")
        if (request.method, path) == ("GET", "/api/documentation/jobs/job-1/report"):
            return send(200, {"files": []})
        return send(404, {"message": f"Unexpected API request: {request.method} {path}"})


def open_app(page: Page, api: Api, url=f"{FRONTEND_URL}/"):
    page.route("**/api/**", api.handle)
    page.goto(url)


# ---------- sign out ----------

def test_logout_after_signing_in_clears_the_session_and_returns_home(page: Page):
    api = Api(signed_in=False)
    open_app(page, api, LOGIN_URL)
    expect(page.get_by_role("button", name="Logout")).to_have_count(0)

    sign_in(page, USER["email"])
    expect(page.get_by_text("Signed in successfully")).to_be_visible()
    expect(page.get_by_role("button", name="Logout")).to_be_visible()

    page.get_by_role("button", name="Logout").click()
    expect(page.get_by_role("button", name="Logout")).to_have_count(0)
    expect(page.get_by_text("Signed in successfully")).to_have_count(0)   # no stale success message
    expect(page.get_by_role("heading", name="LivingDocs")).to_be_visible()
    assert page.url.endswith("#/")
    assert ("POST", "/api/auth/logout") in api.requests
    assert page.evaluate("sessionStorage.getItem('livingdocs.userId')") is None


def test_sign_out_failure_is_reported_and_keeps_the_user_signed_in(page: Page):
    api = Api(signed_in=False, logout_status=500)
    open_app(page, api, LOGIN_URL)
    sign_in(page, USER["email"])
    page.get_by_role("button", name="Logout").click()

    expect(page.get_by_role("alert").filter(has_text="Could not sign out")).to_be_visible()
    expect(page.get_by_role("button", name="Logout")).to_be_visible()
    expect(page.get_by_text("Signed in successfully")).to_be_visible()


# ---------- remove repository needs confirmation ----------

def open_workspace_tab(page: Page, api: Api):
    open_app(page, api)
    open_screen(page, "Repository List")
    page.get_by_role("button", name="Workspace (1)").click()
    expect(page.get_by_role("heading", name="acme/shop")).to_be_visible()


def test_removing_a_repository_does_nothing_when_the_confirmation_is_declined(page: Page):
    api = Api()
    open_workspace_tab(page, api)
    messages = []

    def decline(dialog):
        messages.append(dialog.message)
        dialog.dismiss()

    page.once("dialog", decline)
    page.get_by_role("button", name="Remove", exact=True).click()

    assert messages == ["Remove acme/shop from this workspace?"]
    expect(page.get_by_role("heading", name="acme/shop")).to_be_visible()
    assert not any(method == "DELETE" for method, _ in api.requests)


def test_removing_a_repository_deletes_it_after_the_confirmation_is_accepted(page: Page):
    api = Api()
    open_workspace_tab(page, api)
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Remove", exact=True).click()

    expect(page.get_by_text("acme/shop removed from workspace.")).to_be_visible()
    assert ("DELETE", f"/api/repositories/{REPOSITORY_ID}") in api.requests


# ---------- a reset generation must not come back ----------

def test_late_result_of_a_reset_generation_does_not_overwrite_the_screen(page: Page):
    api = Api()
    open_app(page, api)
    open_screen(page, "Generated Documents")
    expect(page.get_by_role("button", name="Generate documentation")).to_be_enabled()
    page.get_by_role("button", name="Generate documentation").click()
    expect(page.get_by_text("Generating…").first).to_be_visible()

    page.get_by_role("button", name="Reset").click()
    expect(page.get_by_text("Ready to generate")).to_be_visible()

    # The job would have completed (3 polls of 750 ms) and been fetched without the guard. Wait through Playwright
    # (not time.sleep), otherwise the mocked requests of the old polling loop are not processed during the wait.
    page.wait_for_timeout(3500)
    expect(page.get_by_text("Ready to generate")).to_be_visible()
    expect(page.get_by_text("Generation completed")).to_have_count(0)
    expect(page.get_by_role("heading", name="Generated Documentation")).to_have_count(0)
    assert not any(path.endswith("/result") for _, path in api.requests)


def test_generation_that_is_not_reset_still_completes(page: Page):
    api = Api()
    open_app(page, api)
    open_screen(page, "Generated Documents")
    page.get_by_role("button", name="Generate documentation").click()
    expect(page.get_by_text("Generation completed")).to_be_visible(timeout=15000)
    expect(page.get_by_role("heading", name="Generated Documentation")).to_be_visible()
