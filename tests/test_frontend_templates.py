"""Documentation templates in the frontend: view, choose, create, edit, delete, apply.

Runs against the built frontend on http://localhost:3000 with every /api call mocked, like
test_frontend.py.
"""
import json

from playwright.sync_api import Page, expect

REPOSITORY_ID = "11111111-1111-1111-1111-111111111111"
WORKSPACE_ID = "ws-42"

BUILT_IN = [
    {"id": "default", "name": "Standard technical docs", "description": "Overview, classes, functions and API endpoints.",
     "instructions": "Explain every item.", "sections": ["Overview", "Classes", "Functions", "API Endpoints"],
     "built_in": True},
    {"id": "api-reference", "name": "API reference", "description": "Focus on HTTP endpoints.",
     "instructions": "Document only the public API.", "sections": ["Overview", "API Endpoints"], "built_in": True},
    {"id": "brief", "name": "Brief summary", "description": "Short summary.",
     "instructions": "Write a concise summary.", "sections": ["Overview", "Classes", "Functions"], "built_in": True},
]


def install_api(page: Page, state: dict):
    state.setdefault("custom", [])
    state.setdefault("generate_bodies", [])

    def handle(route):
        request = route.request
        path = request.url.split("?", 1)[0].replace("http://localhost:3000", "")
        method = request.method
        body = json.loads(request.post_data) if request.post_data else None
        if method in {"POST", "PUT", "DELETE"}:
            assert request.headers.get("x-xsrf-token") == "csrf-test-token"

        if path == "/api/auth/csrf":
            return route.fulfill(status=200, json={"token": "csrf-test-token"})
        if path == "/api/auth/login":
            return route.fulfill(status=200, json={
                "message": "Login successful", "id": 42, "email": "user@example.test", "username": "test-user",
                "firstName": "Test", "lastName": "User", "role": "DEVELOPER"})
        if path == "/api/github/connection":
            return route.fulfill(status=200, json={"connected": True, "githubLogin": "test-user", "status": "ACTIVE"})
        if path == "/api/github/repos/available":
            return route.fulfill(status=200, json=[])
        if path == f"/api/workspaces/{WORKSPACE_ID}/repositories":
            return route.fulfill(status=200, json=[{
                "id": REPOSITORY_ID, "githubRepoId": 4242, "workspaceId": WORKSPACE_ID, "fullName": "acme/shop",
                "defaultBranch": "main", "privateRepo": False, "status": "CONNECTED",
                "lastSyncedAt": "2026-10-21T12:00:00Z"}])

        if path == "/api/documentation/templates" and method == "GET":
            return route.fulfill(status=200, json=BUILT_IN + sorted(state["custom"], key=lambda t: t["name"]))
        if path == "/api/documentation/templates" and method == "POST":
            if any(t["name"].lower() == body["name"].lower() for t in BUILT_IN + state["custom"]):
                return route.fulfill(status=409, json={"code": "TEMPLATE_NAME_TAKEN",
                                                       "message": "A template with this name already exists."})
            created = {**body, "id": f"c{len(state['custom']) + 1}", "built_in": False}
            state["custom"].append(created)
            return route.fulfill(status=201, json=created)
        if path.startswith("/api/documentation/templates/"):
            tid = path.rsplit("/", 1)[1]
            current = next((t for t in state["custom"] if t["id"] == tid), None)
            if current is None:
                return route.fulfill(status=404, json={"code": "TEMPLATE_NOT_FOUND", "message": "Not found."})
            if method == "PUT":
                current.update(body)
                return route.fulfill(status=200, json=current)
            if method == "DELETE":
                state["custom"].remove(current)
                return route.fulfill(status=204, body="")

        if path == f"/api/repositories/{REPOSITORY_ID}/documentation/generate":
            state["generate_bodies"].append(body)
            if body["templateId"] == "gone":
                return route.fulfill(status=400, json={"code": "TEMPLATE_NOT_FOUND",
                                                       "message": "The selected documentation template does not exist."})
            return route.fulfill(status=202, json={"id": "job-1", "status": "pending"})
        if path == "/api/documentation/jobs/job-1":
            name = next((t["name"] for t in BUILT_IN + state["custom"]
                         if t["id"] == state["generate_bodies"][-1]["templateId"]), None)
            return route.fulfill(status=200, json={"id": "job-1", "status": "completed", "template_name": name})
        if path == "/api/documentation/jobs/job-1/result":
            return route.fulfill(status=200, content_type="text/markdown", body="# acme/shop\n\nDocs.")
        if path == "/api/documentation/jobs/job-1/report":
            return route.fulfill(status=200, json={"files": []})
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {method} {path}"})

    page.route("**/api/**", handle)


def open_documentation(page: Page):
    page.goto("http://localhost:3000/")
    page.get_by_label("Email").fill("user@example.test")
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("status").filter(has_text="Signed in successfully")).to_be_visible()
    page.get_by_role("button", name="Documentation Management").first.click()


def test_user_views_and_chooses_template_and_it_is_applied(page: Page):
    state = {}
    install_api(page, state)
    open_documentation(page)

    cards = page.get_by_role("radiogroup", name="Documentation template")
    for name in ("Standard technical docs", "API reference", "Brief summary"):
        expect(cards.get_by_text(name)).to_be_visible()
    expect(page.get_by_label("Selected template details")).to_contain_text(
        "Overview, Classes, Functions, API Endpoints")

    page.get_by_role("radio", name="API reference").check()
    expect(page.get_by_label("Selected template details")).to_contain_text("Overview, API Endpoints")
    page.get_by_role("button", name="Generate documentation").click()

    expect(page.get_by_role("status").filter(has_text='using the "API reference" template')).to_be_visible()
    assert state["generate_bodies"][-1] == {"templateId": "api-reference", "outputLanguage": "vi"}


def test_user_manages_custom_templates(page: Page):
    state = {}
    install_api(page, state)
    open_documentation(page)

    page.get_by_role("button", name="Manage templates").click()
    expect(page.get_by_text("No custom templates yet.")).to_be_visible()

    # create: Overview + Functions, then move Functions first
    page.get_by_role("button", name="New template").click()
    page.get_by_label("Name").fill("Onboarding")
    page.get_by_label("Description").fill("For new team members")
    page.get_by_role("checkbox", name="Functions").check()
    page.get_by_role("button", name="Move Functions up").click()
    page.get_by_label("Writing instructions for the AI").fill("One sentence per function.")
    page.get_by_role("button", name="Save template").click()

    expect(page.get_by_role("status").filter(has_text='Template "Onboarding" saved.')).to_be_visible()
    assert state["custom"][0]["sections"] == ["Functions", "Overview"]
    assert state["custom"][0]["description"] == "For new team members"
    expect(page.get_by_role("radio", name="Onboarding")).to_be_checked()     # new template is selected

    # duplicate name: API message is shown
    page.get_by_role("button", name="New template").click()
    page.get_by_label("Name").fill("api reference")
    page.get_by_label("Writing instructions for the AI").fill("x")
    page.get_by_role("button", name="Save template").click()
    expect(page.get_by_role("alert").filter(has_text="already exists")).to_be_visible()
    page.get_by_role("button", name="Cancel").click()

    # edit
    page.get_by_role("button", name="Edit Onboarding").click()
    page.get_by_role("checkbox", name="Classes").check()
    page.get_by_role("button", name="Save template").click()
    expect(page.get_by_role("status").filter(has_text='Template "Onboarding" saved.')).to_be_visible()
    assert state["custom"][0]["sections"] == ["Functions", "Overview", "Classes"]

    # apply the custom template
    page.get_by_role("button", name="Generate documentation").click()
    expect(page.get_by_role("status").filter(has_text='using the "Onboarding" template')).to_be_visible()
    assert state["generate_bodies"][-1]["templateId"] == "c1"

    # delete needs a second click; selection falls back to the default template
    page.get_by_role("button", name="Delete Onboarding").click()
    page.get_by_role("button", name="Confirm delete Onboarding").click()
    expect(page.get_by_role("status").filter(has_text='Template "Onboarding" deleted.')).to_be_visible()
    assert state["custom"] == []
    expect(page.get_by_role("radio", name="Standard technical docs")).to_be_checked()


def test_built_in_templates_shown_when_template_list_unavailable(page: Page):
    state = {}
    install_api(page, state)
    page.route("**/api/documentation/templates", lambda route: route.fulfill(status=502, json={}))
    open_documentation(page)

    expect(page.get_by_text("Could not load templates from the server")).to_be_visible()
    expect(page.get_by_role("radio", name="Brief summary")).to_be_visible()
