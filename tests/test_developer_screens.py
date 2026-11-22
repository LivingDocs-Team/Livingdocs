"""Developer screens that used to be "Chưa triển khai": Notifications, Coverage Gaps, Change Log, Template Library.

The API is mocked with Playwright route interception (as in the other browser tests); the screens only use
endpoints the real Backend exposes.
"""
from playwright.sync_api import Page, expect

from rbac_nav import FRONTEND, menu_link, open_screen
from test_rbac_screen_flow import Api, ends_with, start

REPOSITORY_ID = "11111111-1111-4111-8111-111111111111"
WORKFLOW_ID = "33333333-3333-4333-8333-333333333333"
OTHER_WORKFLOW_ID = "44444444-4444-4444-8444-444444444444"
WORKSPACE_REPOSITORIES = {
    "/api/workspaces/ws-42/repositories": [{"id": REPOSITORY_ID, "fullName": "acme/shop", "status": "CONNECTED"}],
}


def gap(entity_id, entity_type, name, path, line):
    return {"id": entity_id, "entityType": entity_type, "name": name, "path": path, "lineStart": line,
            "lineEnd": line + 4, "sourceUrl": f"https://github.com/acme/shop/blob/abc/{path}#L{line}",
            "sourceCommit": "abc"}


def developer(routes):
    return Api("DEVELOPER", {**WORKSPACE_REPOSITORIES, **routes})


def workflow(workflow_id, title, **extra):
    base = {"id": workflow_id, "documentId": f"doc-{workflow_id[:4]}", "documentTitle": title, "ownerUserId": "42",
            "status": "PENDING_STAFF_REVIEW", "submittedDocumentVersion": 2, "reviewerUserId": None,
            "staffReviewResult": None, "staffComment": None, "managerUserId": None, "managerDecision": None,
            "managerComment": None, "createdAt": "2026-11-20T08:00:00Z", "updatedAt": "2026-11-20T08:00:00Z",
            "submittedAt": "2026-11-20T08:00:00Z", "reviewedAt": None, "decidedAt": None, "optimisticVersion": 1}
    return {**base, **extra}


def page_of(items):
    return {"content": items, "page": 0, "size": 20, "totalElements": len(items), "totalPages": 1,
            "first": True, "last": True}


# ---------- Coverage Gaps ----------

COVERAGE = {
    "repositoryId": REPOSITORY_ID, "totalEntities": 6, "documentedEntities": 2,
    # the API returns the gaps ordered by path
    "gaps": [gap("a4", "endpoint", "GET /cart", "src/Api.java", 20), gap("a1", "class", "Cart", "src/Cart.java", 3),
             gap("a2", "method", "total", "src/Cart.java", 9), gap("a3", "function", "format_price", "src/price.py", 1)],
}


def test_coverage_gaps_lists_undocumented_code_grouped_by_file(page: Page):
    start(page, developer({f"/api/repositories/{REPOSITORY_ID}/coverage-gaps": COVERAGE}))
    open_screen(page, "Coverage Gaps")
    expect(page).to_have_url(ends_with("#/documentation/coverage-gaps"))
    expect(page.get_by_role("heading", name="Coverage Gaps")).to_be_visible()
    expect(page.get_by_text("33% documented")).to_be_visible()
    expect(page.get_by_text("2 of 6 code entities have linked documentation.")).to_be_visible()
    expect(page.get_by_role("heading", name="4 undocumented entities")).to_be_visible()
    expect(page.locator(".insight-group h3")).to_have_text(["src/Api.java", "src/Cart.java", "src/price.py"])
    expect(page.get_by_role("link", name="View source").first).to_have_attribute(
        "href", "https://github.com/acme/shop/blob/abc/src/Api.java#L20")
    expect(page.get_by_text("Chưa triển khai")).to_have_count(0)
    expect(menu_link(page, "Coverage Gaps")).not_to_have_attribute("data-status", "placeholder")


def test_coverage_gaps_filters_by_entity_type(page: Page):
    start(page, developer({f"/api/repositories/{REPOSITORY_ID}/coverage-gaps": COVERAGE}))
    open_screen(page, "Coverage Gaps")
    page.get_by_label("Type").select_option("method")
    expect(page.get_by_role("heading", name="1 undocumented entity")).to_be_visible()
    expect(page.locator(".insight-group li")).to_contain_text(["total"])
    expect(page.get_by_text("format_price")).to_have_count(0)


def test_coverage_gaps_reports_full_coverage_and_empty_repositories(page: Page):
    full = {"repositoryId": REPOSITORY_ID, "totalEntities": 3, "documentedEntities": 3, "gaps": []}
    start(page, developer({f"/api/repositories/{REPOSITORY_ID}/coverage-gaps": full}))
    open_screen(page, "Coverage Gaps")
    expect(page.get_by_text("100% documented")).to_be_visible()
    expect(page.get_by_role("heading", name="No coverage gaps")).to_be_visible()


def test_coverage_gaps_without_a_repository_explains_what_to_do(page: Page):
    start(page, Api("DEVELOPER", {"/api/workspaces/ws-42/repositories": []}))
    open_screen(page, "Coverage Gaps")
    expect(page.get_by_role("heading", name="No repositories yet")).to_be_visible()


def test_coverage_gaps_error_can_be_retried(page: Page):
    api = developer({})
    start(page, api)
    open_screen(page, "Coverage Gaps")
    expect(page.get_by_role("heading", name="Coverage Gaps")).to_be_visible()
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    api.routes[f"/api/repositories/{REPOSITORY_ID}/coverage-gaps"] = COVERAGE
    page.get_by_role("button", name="Retry").click()
    expect(page.get_by_text("33% documented")).to_be_visible()


# ---------- Change Log ----------

VERSIONS = [
    {"number": 1, "status": "APPROVED", "origin": "GENERATED", "changes": [], "warnings": [], "manual": False,
     "created_by": "42", "created_at": "2026-11-18T08:00:00Z"},
    {"number": 2, "status": "PENDING", "origin": "DRIFT_UPDATE", "base_version": 1, "manual": True,
     "changes": [{"path": "Classes/Cart", "action": "UPDATED", "entities": ["Cart.total"]}],
     "warnings": [], "note": "Totals now include tax.", "created_by": "42", "created_at": "2026-11-19T08:00:00Z"},
]


def change_log_routes():
    return {
        "/api/document-workflows/history-accessible": page_of([
            workflow(WORKFLOW_ID, "Shop guide"), workflow(OTHER_WORKFLOW_ID, "Billing guide")]),
        f"/api/document-workflows/{WORKFLOW_ID}/versions": VERSIONS,
        f"/api/document-workflows/{OTHER_WORKFLOW_ID}/versions": [],
    }


def test_change_log_shows_each_version_newest_first_with_its_changes(page: Page):
    start(page, developer(change_log_routes()))
    open_screen(page, "Change Log")
    expect(page).to_have_url(ends_with("#/versions/change-log"))
    expect(page.get_by_role("heading", name="Change Log")).to_be_visible()
    entries = page.locator(".changelog-entry h3")
    expect(entries).to_have_count(2)
    expect(entries.first).to_contain_text("Version 2")
    expect(entries.last).to_contain_text("Version 1")
    newest = page.locator(".changelog-entry").first
    expect(newest).to_contain_text("edited by hand")
    expect(newest).to_contain_text("Built on version 1.")
    expect(newest).to_contain_text("Totals now include tax.")
    expect(newest.get_by_role("list", name="Changes in version 2")).to_contain_text("Classes/Cart")
    expect(page.locator(".changelog-entry").last).to_contain_text("No section changes were recorded")


def test_change_log_switches_document_and_handles_a_document_without_versions(page: Page):
    start(page, developer(change_log_routes()))
    open_screen(page, "Change Log")
    expect(page.locator(".changelog-entry")).to_have_count(2)
    page.get_by_label("Document", exact=True).select_option(OTHER_WORKFLOW_ID)
    expect(page.get_by_role("heading", name="No versions recorded")).to_be_visible()
    expect(page.locator(".changelog-entry")).to_have_count(0)


def test_change_log_without_documents_is_an_empty_state(page: Page):
    start(page, developer({"/api/document-workflows/history-accessible": page_of([])}))
    open_screen(page, "Change Log")
    expect(page.get_by_role("heading", name="No documents yet")).to_be_visible()


def test_change_log_rejects_a_malformed_version_list(page: Page):
    routes = change_log_routes()
    routes[f"/api/document-workflows/{WORKFLOW_ID}/versions"] = {"not": "a list"}
    start(page, developer(routes))
    open_screen(page, "Change Log")
    expect(page.get_by_role("alert").filter(has_text="The version list was not valid.")).to_be_visible()


# ---------- Notifications ----------

def notification_routes(preferences=None):
    return {
        "/api/document-workflows/history-accessible": page_of([
            workflow(WORKFLOW_ID, "Shop guide", status="APPROVED", reviewerUserId="43",
                     staffReviewResult="PASSED", staffComment="Looks accurate.", reviewedAt="2026-11-21T08:00:00Z",
                     managerDecision="APPROVED", managerComment="Ship it.", decidedAt="2026-11-22T08:00:00Z")]),
        "/api/profile/notification-preferences": preferences or {
            "emailUpdates": True, "documentChanges": True, "reviewRequests": True, "systemNotifications": True},
    }


def test_notifications_list_review_messages_newest_first(page: Page):
    start(page, developer(notification_routes()))
    open_screen(page, "Notifications")
    expect(page).to_have_url(ends_with("#/account/notifications"))
    expect(page.get_by_role("heading", name="Notifications")).to_be_visible()
    items = page.get_by_role("list", name="Notifications").get_by_role("listitem")
    expect(items).to_have_count(4)
    expect(items.first).to_contain_text("Manager decision")
    expect(items.last).to_contain_text("Submitted for review")
    expect(page.get_by_text("4 unread")).to_be_visible()
    expect(page.get_by_text("Chưa triển khai")).to_have_count(0)


def test_notification_details_and_mark_all_as_read(page: Page):
    start(page, developer(notification_routes()))
    open_screen(page, "Notifications")
    page.get_by_role("button", name="Manager decision").click()
    details = page.get_by_role("region", name="Notification details")
    expect(details).to_contain_text("Shop guide")
    expect(details).to_contain_text("Ship it.")
    expect(details.get_by_role("link", name="Open review feedback")).to_have_attribute(
        "href", "#/documentation/documents/feedback")
    page.get_by_role("button", name="Mark all as read").click()
    expect(page.get_by_text("All caught up")).to_be_visible()
    page.reload()
    expect(page.get_by_text("All caught up")).to_be_visible()


def test_notifications_follow_the_notification_preferences(page: Page):
    preferences = {"emailUpdates": True, "documentChanges": False, "reviewRequests": True, "systemNotifications": True}
    start(page, developer(notification_routes(preferences)))
    open_screen(page, "Notifications")
    items = page.get_by_role("list", name="Notifications").get_by_role("listitem")
    expect(items).to_have_count(2)                                   # submitted + review started only
    page.get_by_label("Show 2 messages turned off in your preferences").check()
    expect(items).to_have_count(4)


def test_notifications_without_messages_is_an_empty_state_and_the_sub_screen_opens_the_same_page(page: Page):
    start(page, developer({"/api/document-workflows/history-accessible": page_of([])}),
          f"{FRONTEND}/#/account/notifications/details")
    expect(page.get_by_role("heading", name="No notifications")).to_be_visible()
    expect(page.get_by_role("navigation", name="Breadcrumb").get_by_role("listitem")).to_have_text(
        ["Account Management", "Notifications", "Notification Details"])


# ---------- Template Library ----------

TEMPLATES = [
    {"id": "default", "name": "Standard technical docs", "description": "Overview, classes and functions.",
     "instructions": "Explain every class.", "sections": ["Overview", "Classes"], "built_in": True},
    {"id": "onboarding", "name": "Onboarding guide", "description": "For new teammates.",
     "instructions": "Keep it friendly.", "sections": ["Overview"], "built_in": False},
]


def test_developer_template_library_is_read_only(page: Page):
    start(page, developer({"/api/documentation/templates": TEMPLATES}))
    open_screen(page, "Template Library")
    expect(page).to_have_url(ends_with("#/knowledge/templates"))
    expect(page.get_by_role("heading", name="Template Library")).to_be_visible()
    catalog = page.get_by_role("list", name="Documentation templates")
    expect(catalog.get_by_role("listitem")).to_have_count(2)
    catalog.get_by_text("Onboarding guide").click()
    expect(catalog).to_contain_text("Keep it friendly.")
    expect(catalog).to_contain_text("Custom")
    for name in ("New template", "Edit Onboarding guide", "Delete Onboarding guide"):
        expect(page.get_by_role("button", name=name)).to_have_count(0)
    expect(page.get_by_text("Chưa triển khai")).to_have_count(0)


def test_developer_template_library_reports_a_load_error(page: Page):
    start(page, developer({}))
    open_screen(page, "Template Library")
    expect(page.get_by_role("heading", name="Template Library")).to_be_visible()
    expect(page.get_by_role("alert")).to_be_visible()


# ---------- the Developer flow has no unbuilt screen left ----------

def test_developer_menu_has_no_placeholder_screens(page: Page):
    start(page, developer({}))
    expect(page.locator("nav[aria-label='Main menu'] a[data-status='placeholder']")).to_have_count(0)
