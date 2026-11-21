"""Role-based screen flows (frontend/src/rbac): public screens, per-role menus, route guard, placeholders.

Runs against the built frontend on http://localhost:3000 with every /api call mocked. The expected menus
are copied from the team's screen flows (Developer, Staff, Manager) and from the provisional flows of
Technical Lead and Administrator, so a change to a flow file must be reflected here on purpose.
"""
import json
import re

import pytest
from playwright.sync_api import Page, expect

from rbac_nav import FRONTEND, LOGIN_URL, main_menu, menu_link, open_screen, open_tile, sign_in

# The menu lists the main screens of each flow only; sub-screens are reached from their parent page.
MENUS = {
    "DEVELOPER": {
        "modules": ["Account Management", "GitHub Integration", "Documentation Generation",
                    "Versions & Change Log", "Knowledge Base"],
        "screens": ["Profile & Settings", "Notifications", "GitHub Connection", "Repository List", "PR & Commit List", "Drift Alerts",
                    "Coverage Gaps", "Generated Documents", "Version History", "Change Log",
                    "Documentation Collections", "Knowledge Search", "Template Library"],
        "landing": "#/github/connection",
    },
    "STAFF": {
        "modules": ["Account Management", "Document Review"],
        "screens": ["Profile & Settings", "Review Queue", "Review History"],
        "landing": "#/review/queue",
    },
    "MANAGER": {
        "modules": ["Account Management", "Final Approval", "Approval Policies"],
        "screens": ["Profile & Settings", "Approval Queue", "Approval History", "Approval Delegation",
                    "Approval Policy", "Merge Policy"],
        "landing": "#/approval/queue",
    },
    "TECHNICAL_LEAD": {
        "modules": ["Account Management", "Code & Documentation", "Review & Approval", "Drift", "Versions",
                    "Knowledge Base", "Reports"],
        "screens": ["Profile & Settings", "Pull Requests & Commits", "Documentation", "Workflow Status",
                    "Staff Review", "Manager Approval", "Approval Audit Trail & History",
                    "Drift Policies & Thresholds", "Version History & Comparison", "Document Rollback",
                    "Documentation Collections", "Knowledge Search", "Documentation Templates", "Health Metrics, Dependency Graph & Reports"],
        "landing": "#/knowledge/search",
    },
    "ADMINISTRATOR": {
        "modules": ["Account Management", "Repositories", "Administration", "Monitoring & Audit"],
        "screens": ["Profile & Settings", "Repository Management & Synchronization", "Users, Roles & Permissions",
                    "Workspace & Repository Administration", "System Configuration", "Notification Policies",
                    "Monitoring, Audit Logs & Analytics", "Approval Audit Trail & History"],
        "landing": "#/account/profile",
    },
}


REPOSITORY_ID = "11111111-1111-4111-8111-111111111111"
DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
# One saved document in the user's personal workspace (ws-42), opened from Documentation Management.
SAVED_DOCUMENT_ROUTES = {
    "/api/workspaces/ws-42/repositories": [{"id": REPOSITORY_ID, "fullName": "acme/shop", "status": "CONNECTED"}],
    f"/api/repositories/{REPOSITORY_ID}/documentation": [
        {"id": DOCUMENT_ID, "markdown": "# Shop guide\n", "createdAt": "2026-11-17T08:00:00Z"}],
    f"/api/documentation/{DOCUMENT_ID}": {"id": DOCUMENT_ID, "repositoryId": REPOSITORY_ID,
                                         "markdown": "# Shop guide\n", "generationJobId": None},
}


class Api:
    def __init__(self, role=None, routes=None):
        self.role = role
        self.routes = routes or {}
        self.requests = []

    def user(self):
        return {"message": "Login successful", "id": 42, "email": f"{(self.role or 'x').lower()}@example.test",
                "username": "rbac", "firstName": "Test", "lastName": "User", "role": self.role}

    def handle(self, route):
        request = route.request
        path = request.url.split("?", 1)[0].removeprefix(FRONTEND)
        body = json.loads(request.post_data) if request.post_data else None
        self.requests.append((request.method, path, body))
        if path == "/api/auth/me":
            return route.fulfill(status=200, json=self.user()) if self.role else route.fulfill(status=401, json={})
        if path == "/api/auth/csrf":
            return route.fulfill(status=200, json={"token": "csrf-rbac"})
        if path == "/api/auth/login":
            self.role = self.role or "DEVELOPER"
            return route.fulfill(status=200, json=self.user())
        if path == "/api/auth/logout":
            self.role = None
            return route.fulfill(status=200, json={"message": "Logged out"})
        if path == "/api/auth/register":
            return route.fulfill(status=201, json={"message": "Registration successful."})
        if request.method == "GET" and path in self.routes:
            return route.fulfill(status=200, json=self.routes[path])
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {request.method} {path}"})


def ends_with(fragment):
    return re.compile(re.escape(fragment) + "$")


def start(page: Page, api: Api, url=f"{FRONTEND}/"):
    page.route("**/api/**", api.handle)
    page.goto(url)


def expect_menu_screens(page: Page, screens):
    """Waits until the menu lists exactly these screens (the page may still be loading on a slow runner)."""
    expect(main_menu(page).get_by_role("link")).to_have_text(screens)


def menu_modules(page: Page):
    return main_menu(page).locator("section").evaluate_all("s => s.map(e => e.getAttribute('aria-label'))")


# ---------- screen 1: public ----------

def test_signed_out_user_sees_only_home_login_and_register(page: Page):
    start(page, Api())
    expect(page.get_by_role("heading", name="LivingDocs")).to_be_visible()
    public = page.get_by_role("navigation", name="Public")
    expect(public.get_by_role("link")).to_have_text(["Home", "Login", "Register"])
    expect(main_menu(page)).to_have_count(0)
    for internal in ("GitHub Connection", "Repository Management", "Documentation Management", "Profile",
                     "Notifications", "Documentation Drift"):
        expect(page.get_by_role("button", name=internal)).to_have_count(0)


@pytest.mark.parametrize("path", ["#/github/connection", "#/review/queue", "#/approval/queue", "#/admin/users",
                                  "#/account/profile", "#/no-such-page"])
def test_internal_url_without_a_session_redirects_to_login(page: Page, path):
    start(page, Api(), f"{FRONTEND}/{path}")
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()
    expect(page).to_have_url(ends_with("#/login"))
    expect(main_menu(page)).to_have_count(0)


def test_after_sign_in_the_requested_page_opens_when_the_role_may_see_it(page: Page):
    api = Api()
    start(page, api, f"{FRONTEND}/#/review/queue/decision")
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()
    api.role = "STAFF"
    sign_in(page, "staff@example.test")
    expect(page.get_by_role("navigation", name="Breadcrumb")).to_contain_text("Review Decision")
    expect(page).to_have_url(ends_with("#/review/queue/decision"))


def test_register_creates_only_developer_accounts(page: Page):
    api = Api()
    start(page, api, f"{FRONTEND}/#/register")
    expect(page.get_by_text("Registration creates a Developer account")).to_be_visible()
    expect(page.get_by_label("Role")).to_have_count(0)
    expect(page.get_by_role("combobox")).to_have_count(0)


def test_login_redirects_to_the_role_landing_page_and_logout_returns_home(page: Page):
    api = Api()
    start(page, api, LOGIN_URL)
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()   # session check finished
    api.role = "MANAGER"
    sign_in(page, "manager@example.test")
    expect(page.get_by_role("heading", name="Manager Approval")).to_be_visible()
    expect(page).to_have_url(ends_with("#/approval/queue"))

    page.get_by_role("button", name="Logout").click()
    expect(page.get_by_role("navigation", name="Public")).to_be_visible()
    expect(main_menu(page)).to_have_count(0)
    expect(page).to_have_url(ends_with("#/"))


# ---------- screen 2: menus per role ----------

# Rows #4, #14 and #15 remain outside the web app.
@pytest.mark.parametrize("role", list(MENUS))
@pytest.mark.parametrize("path", ["#/dashboard", "#/auto-update/settings", "#/auto-update/documents",
                                  "#/drift/analysis", "#/drift/history"])
def test_removed_functions_are_not_reachable_by_any_role(page: Page, role, path):
    start(page, Api(role), f"{FRONTEND}/{path}")
    expect(page).to_have_url(ends_with(MENUS[role]["landing"]))
    expect(page.get_by_role("heading", name="Access denied")).to_have_count(0)
    expect(page.get_by_role("heading", name="Documentation Drift")).to_have_count(0)


def test_developer_reviews_drift_alert(page: Page):
    base = f"/api/repositories/{REPOSITORY_ID}/drift"
    finding = {"id": "F1", "message": "Outdated parameter", "file": "shop/cart.py",
               "severity": "high", "suggestion": "Use qty.", "resolution": {"status": "open"}}
    report = {"id": "report-1", "pull_request": {"number": 7}, "findings": [finding]}

    class DriftApi(Api):
        def handle(self, route):
            request = route.request
            if request.method == "POST" and request.url.endswith(f"{base}/analyze"):
                assert request.post_data_json == {"pullRequestNumber": 7}
                return route.fulfill(status=201, json=report)
            if request.method == "PUT" and request.url.endswith(f"{base}/reports/report-1/findings/F1/resolution"):
                body = request.post_data_json
                self.requests.append((request.method, request.url, body))
                proposed = finding["suggestion"] if body["decision"] == "accept" else body.get("proposed")
                return route.fulfill(status=200, json={**finding, "resolution": {**body, "proposed": proposed}})
            return super().handle(route)

    api = DriftApi("DEVELOPER", {
        **SAVED_DOCUMENT_ROUTES,
        f"{base}/reports": [{"id": "report-1", "pull_request_number": 7, "pull_request_title": "Update cart"}],
    })
    start(page, api, f"{FRONTEND}/#/drift/alerts")
    expect(page.get_by_role("heading", name="Drift Alerts")).to_be_visible()
    page.get_by_label("Pull request number").fill("7")
    page.get_by_role("button", name="Check for drift").click()
    expect(page.get_by_role("heading", name="Outdated parameter")).to_be_visible()
    page.get_by_role("button", name="Accept", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Accepted")).to_be_visible()
    page.get_by_role("button", name="Edit", exact=True).click()
    page.get_by_label("Proposed text").fill("Pass qty as an integer.")
    page.get_by_role("button", name="Save edit").click()
    expect(page.get_by_role("status").filter(has_text="Pass qty as an integer.")).to_be_visible()
    page.get_by_role("button", name="Dismiss", exact=True).click()
    page.get_by_label("Dismissal reason").fill("Already handled elsewhere.")
    page.get_by_role("button", name="Confirm dismissal").click()
    expect(page.get_by_role("status").filter(has_text="Dismissed")).to_be_visible()
    assert [body["decision"] for method, _, body in api.requests if method == "PUT"] == ["accept", "edit", "dismiss"]


@pytest.mark.parametrize("role", ["DEVELOPER", "TECHNICAL_LEAD"])
def test_collections_browse_and_manage_controls_follow_role(page: Page, role):
    path = "/api/workspaces/ws-42/collections"
    detail = f"{path}/{REPOSITORY_ID}"
    document = {"id": DOCUMENT_ID, "title": "Shop guide", "assignedOwnerId": "42"}
    routes = {
        **SAVED_DOCUMENT_ROUTES,
        "/api/managed-workspaces": [],
        path: [{"id": REPOSITORY_ID, "name": "Platform guides", "repositoryId": REPOSITORY_ID,
                "repositoryName": "acme/shop"}],
        f"{detail}/documents": [document],
        f"{detail}/document-candidates": [document],
    }
    api = Api(role, routes)
    start(page, api, f"{FRONTEND}/#/knowledge/collections")
    page.get_by_role("button", name="Platform guides").click()
    expect(page.get_by_text("Shop guide", exact=True)).to_be_visible()
    expect(page.get_by_text("Owner #42", exact=True)).to_be_visible()
    can_manage = role == "TECHNICAL_LEAD"
    for name in ("New collection", "Edit collection", "Delete collection", "Save owner"):
        expect(page.get_by_role("button", name=name)).to_have_count(int(can_manage))
    if not can_manage:
        assert not any(request[1].endswith("/document-candidates") for request in api.requests)


@pytest.mark.parametrize("role", ["STAFF", "MANAGER", "ADMINISTRATOR"])
def test_disallowed_role_cannot_open_collections_directly(page: Page, role):
    start(page, Api(role), f"{FRONTEND}/#/knowledge/collections")
    expect(page.get_by_role("heading", name="Access denied")).to_be_visible()
    expect(menu_link(page, "Documentation Collections")).to_have_count(0)


@pytest.mark.parametrize("role", list(MENUS))
def test_each_role_sees_exactly_its_flow_menu_and_lands_on_its_default_page(page: Page, role):
    start(page, Api(role))
    expect(main_menu(page)).to_be_visible()
    expect(page).to_have_url(ends_with(MENUS[role]["landing"]))
    expect_menu_screens(page, MENUS[role]["screens"])
    assert menu_modules(page) == MENUS[role]["modules"]
    provisional = page.get_by_text("Provisional flow")
    expect(provisional).to_have_count(1 if role in ("TECHNICAL_LEAD", "ADMINISTRATOR") else 0)


def test_legacy_admin_role_uses_the_administrator_flow(page: Page):
    start(page, Api("ADMIN"))
    expect(main_menu(page)).to_be_visible()
    expect_menu_screens(page, MENUS["ADMINISTRATOR"]["screens"])


def test_account_without_a_known_role_gets_no_menu(page: Page):
    start(page, Api("GUEST"))
    expect(page.get_by_role("heading", name="No role assigned")).to_be_visible()
    expect(main_menu(page)).to_have_count(0)
    expect(page.get_by_role("button", name="Logout")).to_be_visible()


# ---------- route guard ----------

@pytest.mark.parametrize("role, path", [
    ("DEVELOPER", "#/approval/queue"),
    ("DEVELOPER", "#/review/queue"),
    ("DEVELOPER", "#/admin/users"),
    ("STAFF", "#/github/connection"),
    ("STAFF", "#/documentation/documents"),
    ("STAFF", "#/drift/alerts"),
    ("MANAGER", "#/review/queue"),
    ("TECHNICAL_LEAD", "#/github/connection"),
    ("ADMINISTRATOR", "#/approval/queue"),
    # rows removed from the matrix because the role's flow has no screen for them (2026-11-17)
    ("DEVELOPER", "#/approval/history"),      # #11
    ("STAFF", "#/github/activity"),           # #7
    ("MANAGER", "#/github/activity"),         # #7
    ("MANAGER", "#/versions/history"),        # #18
    ("MANAGER", "#/documentation/documents"), # #8, #9
])
def test_typing_the_url_of_a_screen_outside_the_role_is_blocked(page: Page, role, path):
    start(page, Api(role), f"{FRONTEND}/{path}")
    expect(page.get_by_role("heading", name="Access denied")).to_be_visible()
    page.get_by_role("link", name="Go to your home page").click()
    expect(page).to_have_url(ends_with(MENUS[role]["landing"]))


def test_unknown_internal_url_goes_to_the_landing_page(page: Page):
    start(page, Api("STAFF"), f"{FRONTEND}/#/does/not/exist")
    expect(page.get_by_role("heading", name="Staff Review Queue")).to_be_visible()
    expect(page).to_have_url(ends_with("#/review/queue"))


def test_signed_in_user_opening_login_goes_to_the_landing_page(page: Page):
    start(page, Api("DEVELOPER"), LOGIN_URL)
    expect(main_menu(page)).to_be_visible()
    expect(page).to_have_url(ends_with("#/github/connection"))


# ---------- placeholders ----------

def test_placeholder_screen_keeps_its_place_in_the_flow(page: Page):
    start(page, Api("DEVELOPER"))
    link = menu_link(page, "Coverage Gaps")
    expect(link).to_have_attribute("data-status", "placeholder")
    expect(link).to_have_class(re.compile(r"\bis-placeholder\b"))          # dimmed
    expect(link).to_have_attribute("title", "Chưa triển khai")
    expect(menu_link(page, "Generated Documents")).not_to_have_class(re.compile(r"\bis-placeholder\b"))

    link.click()
    expect(page.get_by_role("heading", name="Coverage Gaps")).to_be_visible()
    expect(page.get_by_text("Chưa triển khai")).to_be_visible()
    breadcrumb = page.get_by_role("navigation", name="Breadcrumb")
    expect(breadcrumb.get_by_role("listitem")).to_have_text(["Documentation Generation", "Coverage Gaps"])
    expect(page.get_by_text("#8 Documentation Generation & Editing")).to_be_visible()


def test_menu_lists_main_screens_only_and_the_parent_stays_highlighted_on_a_sub_screen(page: Page):
    start(page, Api("STAFF"), f"{FRONTEND}/#/review/queue/comments")
    expect(main_menu(page)).to_be_visible()
    expect_menu_screens(page, MENUS["STAFF"]["screens"])
    expect(main_menu(page).locator("ul ul")).to_have_count(0)               # no nested sub-screens
    expect(menu_link(page, "Review Queue")).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("navigation", name="Breadcrumb")).to_contain_text("Comments & Change Requests")


def test_sub_screen_breadcrumb_links_back_to_its_parent(page: Page):
    start(page, Api("STAFF"), f"{FRONTEND}/#/review/queue/template-check")
    breadcrumb = page.get_by_role("navigation", name="Breadcrumb")
    expect(breadcrumb.get_by_role("listitem")).to_have_text(
        ["Document Review", "Review Queue", "Template & Code Check"])
    breadcrumb.get_by_role("link", name="Review Queue").click()
    expect(page.get_by_role("heading", name="Staff Review Queue")).to_be_visible()


def test_profile_settings_lists_its_sub_screens(page: Page):
    start(page, Api("MANAGER"))
    open_screen(page, "Profile & Settings")
    expect(page.locator(".tile b")).to_have_text(["Profile", "Notification Preferences"])
    open_tile(page, "Notification Preferences")
    expect(page).to_have_url(ends_with("#/account/notification-preferences"))
    expect(menu_link(page, "Profile & Settings")).to_have_attribute("aria-current", "page")


# ---------- action buttons follow can() ----------

def open_staff_document_editor(page: Page):
    """Document Editor is a page of its own; Staff open it from the Review Queue header."""
    open_screen(page, "Review Queue")
    page.get_by_role("link", name="Document Editor").click()


def test_staff_document_editor_hides_actions_the_matrix_does_not_grant(page: Page):
    start(page, Api("STAFF"))
    expect(menu_link(page, "Document Editor")).to_have_count(0)
    open_staff_document_editor(page)
    expect(page.get_by_role("heading", name="Documentation Management")).to_be_visible()
    for name in ("Generate documentation", "Manage templates", "Submit for review"):
        expect(page.get_by_role("button", name=name)).to_have_count(0)
    expect(page.get_by_role("button", name="Reset")).to_be_visible()


@pytest.mark.parametrize("role, allowed", [
    ("DEVELOPER", True),     # matrix #8: Developer C-R-U-E
    ("STAFF", False),        # matrix #8: Staff R-U, no E
])
def test_export_markdown_is_offered_only_to_roles_with_export(page: Page, role, allowed):
    start(page, Api(role, SAVED_DOCUMENT_ROUTES))
    if role == "STAFF":
        open_staff_document_editor(page)
    else:
        open_screen(page, "Generated Documents")
    page.get_by_role("button", name="Open document").click()
    page.get_by_role("tab", name="Edit").click()
    expect(page.get_by_role("button", name="Restore original")).to_be_visible()
    expect(page.get_by_role("button", name="Export Markdown")).to_have_count(1 if allowed else 0)


def test_developer_generation_request_shows_its_create_action(page: Page):
    start(page, Api("DEVELOPER"))
    open_screen(page, "Generated Documents")
    expect(page.get_by_role("button", name="Generate documentation")).to_have_count(1)
    expect(page.get_by_role("button", name="Manage templates")).to_have_count(0)   # templates: R only


def test_technical_lead_template_library_offers_template_management(page: Page):
    start(page, Api("TECHNICAL_LEAD"))
    open_screen(page, "Documentation Templates")
    expect(page.get_by_role("heading", name="Documentation Templates")).to_be_visible()
    expect(page.get_by_role("button", name="New template")).to_be_visible()
