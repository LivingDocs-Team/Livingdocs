"""Staff Review History, Administrator Approval Audit Trail & Repository Management (screens that were "Chưa triển khai").

The API is mocked with Playwright route interception, like the other browser tests.
"""
from playwright.sync_api import Page, expect

from rbac_nav import menu_link, open_screen
from test_rbac_screen_flow import Api, ends_with, start

WORKFLOW_ID = "33333333-3333-4333-8333-333333333333"
OTHER_WORKFLOW_ID = "44444444-4444-4444-8444-444444444444"
REPOSITORY_ID = "11111111-1111-4111-8111-111111111111"


def workflow(workflow_id, title, status="PENDING_MANAGER_APPROVAL", **extra):
    return {"id": workflow_id, "documentId": f"doc-{workflow_id[:4]}", "documentTitle": title, "ownerUserId": "7",
            "status": status, "submittedDocumentVersion": 2, "reviewerUserId": "42", "createdAt": "2026-11-20T08:00:00Z",
            "updatedAt": "2026-11-21T08:00:00Z", "optimisticVersion": 1, **extra}


def event(event_id, action, previous, new, comment=None, role="STAFF", at="2026-11-21T08:00:00Z", version=2):
    return {"id": event_id, "workflowId": WORKFLOW_ID, "actorUserId": "42", "actorRole": role, "action": action,
            "previousStatus": previous, "newStatus": new, "previousReviewerUserId": None,
            "newReviewerUserId": "42" if action == "CLAIMED" else None, "comment": comment, "createdAt": at,
            "documentId": "doc-3333", "documentVersion": version, "triggerSource": None}


def page_of(items):
    return {"content": items, "page": 0, "size": 20, "totalElements": len(items), "totalPages": 1,
            "first": True, "last": True}


def audit_routes():
    return {
        "/api/document-workflows/history-accessible": page_of([
            workflow(WORKFLOW_ID, "Shop guide"), workflow(OTHER_WORKFLOW_ID, "Billing guide", "APPROVED")]),
        f"/api/document-workflows/{WORKFLOW_ID}/history": [
            event("e1", "SUBMITTED", "DRAFT", "PENDING_STAFF_REVIEW", role="DEVELOPER", at="2026-11-20T08:00:00Z"),
            event("e2", "CLAIMED", "PENDING_STAFF_REVIEW", "STAFF_REVIEWING", at="2026-11-20T09:00:00Z"),
            event("e3", "STAFF_REVIEWED", "STAFF_REVIEWING", "PENDING_MANAGER_APPROVAL", "Looks accurate.")],
        f"/api/document-workflows/{OTHER_WORKFLOW_ID}/history": [],
    }


def test_staff_review_history_shows_the_audit_trail_of_a_document(page: Page):
    start(page, Api("STAFF", audit_routes()))
    open_screen(page, "Review History")
    expect(page).to_have_url(ends_with("#/review/history"))
    expect(page.get_by_role("heading", name="Review History")).to_be_visible()
    entries = page.locator(".changelog-entry")
    expect(entries).to_have_count(3)
    expect(entries.first).to_contain_text("submitted")
    expect(entries.first).to_contain_text("draft → pending staff review")
    expect(entries.last).to_contain_text("Looks accurate.")
    expect(entries.last).to_contain_text("(staff)")
    expect(page.get_by_text("Chưa triển khai")).to_have_count(0)
    expect(menu_link(page, "Review History")).not_to_have_attribute("data-status", "placeholder")


def test_review_history_switches_document_and_handles_an_empty_trail(page: Page):
    start(page, Api("STAFF", audit_routes()))
    open_screen(page, "Review History")
    expect(page.locator(".changelog-entry")).to_have_count(3)
    page.get_by_label("Document", exact=True).select_option(OTHER_WORKFLOW_ID)
    expect(page.get_by_role("heading", name="No events recorded")).to_be_visible()


def test_review_history_without_documents_is_an_empty_state(page: Page):
    start(page, Api("STAFF", {"/api/document-workflows/history-accessible": page_of([])}))
    open_screen(page, "Review History")
    expect(page.get_by_role("heading", name="No history yet")).to_be_visible()


def test_review_history_error_can_be_retried(page: Page):
    api = Api("STAFF", {})
    start(page, api)
    open_screen(page, "Review History")
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    api.routes.update(audit_routes())
    page.get_by_role("button", name="Retry").click()
    expect(page.locator(".changelog-entry")).to_have_count(3)


def test_administrator_approval_audit_trail_uses_the_same_page(page: Page):
    start(page, Api("ADMINISTRATOR", audit_routes()))
    open_screen(page, "Approval Audit Trail & History")
    expect(page).to_have_url(ends_with("#/admin/approval-audit"))
    expect(page.get_by_role("heading", name="Approval Audit Trail & History")).to_be_visible()
    expect(page.locator(".changelog-entry")).to_have_count(3)
    expect(page.get_by_text("Chưa triển khai")).to_have_count(0)


def administrator_with_repository():
    return Api("ADMINISTRATOR", {
        "/api/managed-workspaces": [],
        "/api/github/connection": {"connected": True, "githubLogin": "admin", "status": "ACTIVE"},
        "/api/github/repos/available": [],
        "/api/workspaces/ws-42/repositories": [{
            "id": REPOSITORY_ID, "workspaceId": "ws-42", "githubRepoId": 4242, "fullName": "acme/shop",
            "defaultBranch": "main", "privateRepo": False, "status": "CONNECTED",
            "lastSyncedAt": "2026-11-06T03:05:00Z"}],
    })


def test_administrator_repository_management_has_no_pull_request_panel(page: Page):
    start(page, administrator_with_repository())
    open_screen(page, "Repository Management & Synchronization")
    expect(page).to_have_url(ends_with("#/admin/repositories"))
    page.get_by_role("button", name="Workspace (1)").click()
    expect(page.get_by_role("button", name="Sync now")).to_be_visible()
    # #7 Pull Request & Commit data is not an Administrator permission
    expect(page.get_by_role("button", name="PRs & commits")).to_have_count(0)
    expect(page.get_by_text("Chưa triển khai")).to_have_count(0)
