"""LD-312 frontend tests for reviewing saved workflow document suggestions."""

import json
import os

from playwright.sync_api import Page, expect

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
USER_ID = "42"
WORKSPACE_ID = f"ws-{USER_ID}"
REPOSITORY_ID = "11111111-1111-4111-8111-111111111111"
DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
WORKFLOW_ID = "33333333-3333-4333-8333-333333333333"
CURRENT_CONTENT = "# Shop guide\n\nUse GET /shop.\n"
PROPOSED_CONTENT = "# Shop guide\n\nUse GET /api/shop.\n\nAuthentication is required.\n"


def workflow(status="STAFF_REVIEWING"):
    return {
        "id": WORKFLOW_ID,
        "documentId": DOCUMENT_ID,
        "documentTitle": "Shop API Guide",
        "ownerUserId": "7",
        "status": status,
        "submittedDocumentVersion": 2,
        "reviewerUserId": USER_ID if status == "STAFF_REVIEWING" else None,
        "staffReviewResult": None,
        "managerDecision": None,
        "createdAt": "2026-11-10T09:30:00Z",
        "updatedAt": "2026-11-10T10:00:00Z",
    }


def comparison():
    return {
        "pending_version": {
            "number": 2,
            "status": "proposed",
            "origin": "source_change",
            "created_at": "2026-11-10T10:00:00Z",
            "content": PROPOSED_CONTENT,
            "changes": [{"path": "docs/shop.md", "action": "updated", "entities": ["ShopController"]}],
        },
        "approved_version": {
            "number": 1,
            "status": "accepted",
            "origin": "generated",
            "created_at": "2026-11-09T10:00:00Z",
            "content": CURRENT_CONTENT,
            "changes": [],
        },
        "has_approved_version": True,
        "diff": (
            "--- approved-v1\n+++ pending-v2\n@@ -1,3 +1,5 @@\n"
            " # Shop guide\n\n-Use GET /shop.\n+Use GET /api/shop.\n"
            "+\n+Authentication is required.\n"
        ),
        "template_sections": ["API"],
        "files": [],
    }


def review_evidence():
    return {
        "job_id": "job-77",
        "method": "ai",
        "files": [{
            "path": "src/shop.py",
            "status": "generated",
            "entities": [{
                "kind": "endpoint",
                "name": "GET /api/shop",
                "confidence": 0.94,
                "level": "high",
                "evidence": [{
                    "id": "E1", "kind": "source", "path": "src/shop.py", "line_start": 20,
                    "line_end": 25, "excerpt": "@app.get('/api/shop')",
                }],
            }],
            "context_used": [],
        }],
        "source_snapshot": {
            "repository_id": REPOSITORY_ID,
            "repository_full_name": "acme/shop",
            "branch": "main",
            "commit_sha": "abcdef1234567890abcdef1234567890abcdef12",
        },
        "source_verification": {"status": "MATCH", "message": "The repository source has not changed."},
    }


class FakeApi:
    def __init__(self, item, comparison_status=200, edit_status=200, workflow_status=200,
                 workflow_response=None):
        self.item = item
        self.comparison_status = comparison_status
        self.edit_status = edit_status
        self.workflow_status = workflow_status
        self.workflow_response = workflow_response
        self.requests = []
        self.edit_bodies = []

    def handle(self, route):
        request = route.request
        path = request.url.split("?", 1)[0].removeprefix(FRONTEND_URL)
        body = json.loads(request.post_data) if request.post_data else None
        self.requests.append((request.method, path, body))

        if (request.method, path) == ("GET", "/api/auth/me"):
            return route.fulfill(status=200, json={"id": int(USER_ID), "email": "reviewer@example.test"})
        if (request.method, path) == ("GET", "/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-ld312"})
        if (request.method, path) == ("GET", f"/api/workspaces/{WORKSPACE_ID}/repositories"):
            return route.fulfill(status=200, json=[{
                "id": REPOSITORY_ID, "workspaceId": WORKSPACE_ID, "fullName": "acme/shop",
                "defaultBranch": "main", "privateRepo": False, "status": "CONNECTED",
            }])
        if (request.method, path) == ("GET", f"/api/repositories/{REPOSITORY_ID}/documentation"):
            return route.fulfill(status=200, json=[])
        if (request.method, path) == ("GET", "/api/documentation/templates"):
            return route.fulfill(status=200, json=[{
                "id": "default", "name": "Standard technical docs", "description": "",
                "instructions": "", "sections": ["API"], "built_in": True,
            }])
        if (request.method, path) == ("GET", "/api/document-workflows/history-accessible"):
            if self.workflow_status != 200:
                return route.fulfill(status=self.workflow_status, json={"message": "Workflow list unavailable."})
            if self.workflow_response is not None:
                return route.fulfill(status=200, json=self.workflow_response)
            return route.fulfill(status=200, json={
                "content": [self.item] if self.item else [], "page": 0, "size": 20,
                "totalElements": 1 if self.item else 0,
                "totalPages": 1, "first": True, "last": True,
            })
        if (request.method, path) == ("GET", f"/api/document-workflows/{WORKFLOW_ID}/history"):
            return route.fulfill(status=200, json=[])
        if (request.method, path) == ("GET", f"/api/document-workflows/{WORKFLOW_ID}/document"):
            return route.fulfill(status=200, json={
                "documentId": DOCUMENT_ID, "version": 2, "content": PROPOSED_CONTENT,
            })
        if (request.method, path) == ("GET", f"/api/document-workflows/{WORKFLOW_ID}/review-comparison"):
            if self.comparison_status != 200:
                return route.fulfill(status=self.comparison_status, json={"message": "Workflow changed."})
            return route.fulfill(status=200, json=comparison())
        if (request.method, path) == ("GET", f"/api/document-workflows/{WORKFLOW_ID}/review-evidence"):
            return route.fulfill(status=200, json=review_evidence())
        if (request.method, path) == ("GET", f"/api/documentation/{DOCUMENT_ID}"):
            return route.fulfill(status=200, json={
                "id": DOCUMENT_ID, "repositoryId": REPOSITORY_ID, "generationJobId": "job-77",
                "markdown": PROPOSED_CONTENT, "createdAt": "2026-11-09T10:00:00Z",
            })
        if (request.method, path) == ("PUT", f"/api/document-workflows/{WORKFLOW_ID}/document"):
            self.edit_bodies.append(body)
            if self.edit_status != 200:
                return route.fulfill(status=self.edit_status, json={"message": "Workflow changed."})
            return route.fulfill(status=200, json=self.item)
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {request.method} {path}"})


def open_documentation(page: Page, api: FakeApi):
    page.route("**/api/**", api.handle)
    page.goto(FRONTEND_URL)
    page.get_by_role("button", name="Documentation Management").first.click()
    expect(page.get_by_role("heading", name="Documentation Management")).to_be_visible()
    expect(page.get_by_role("heading", name="AI Suggestion Review")).to_be_visible()


def test_assigned_staff_can_review_backend_comparison_and_evidence(page: Page):
    api = FakeApi(workflow())
    open_documentation(page, api)

    suggestion = page.get_by_role("button", name="Shop API Guide")
    expect(suggestion).to_contain_text("STAFF_REVIEWING")
    expect(suggestion).to_contain_text("2026")
    page.get_by_label("AI suggestion list").get_by_role("button", name="Shop API Guide").click()

    detail = page.get_by_label("AI suggestion detail")
    expect(detail).to_contain_text("acme/shop")
    expect(detail).to_contain_text("Current approved content (v1)")
    expect(detail.locator(".suggestion-version-grid")).to_contain_text(CURRENT_CONTENT)
    expect(detail.locator(".suggestion-version-grid")).to_contain_text(PROPOSED_CONTENT)
    expect(detail.get_by_text("+Use GET /api/shop.", exact=True)).to_be_visible()
    expect(detail.get_by_text("-Use GET /shop.", exact=True)).to_be_visible()
    expect(detail).to_contain_text("updated")
    expect(detail).to_contain_text("ShopController")
    expect(detail).to_contain_text("E1")
    expect(detail).to_contain_text("src/shop.py:20-25")
    expect(detail).to_contain_text("Source verification: MATCH")
    expect(detail.get_by_role("button", name="Accept")).to_have_count(0)
    expect(detail.get_by_role("button", name="Dismiss")).to_have_count(0)

    paths = [path for method, path, _ in api.requests if method == "GET"]
    assert f"/api/document-workflows/{WORKFLOW_ID}/document" in paths
    assert f"/api/document-workflows/{WORKFLOW_ID}/review-comparison" in paths
    assert f"/api/document-workflows/{WORKFLOW_ID}/review-evidence" in paths


def test_owner_can_edit_only_after_changes_requested_and_backend_confirms(page: Page):
    item = workflow("CHANGES_REQUESTED")
    item["ownerUserId"] = USER_ID
    api = FakeApi(item)
    open_documentation(page, api)
    page.get_by_label("AI suggestion list").get_by_role("button", name="Shop API Guide").click()

    page.get_by_role("button", name="Edit proposal").click()
    edited = PROPOSED_CONTENT + "\nUpdated by the owner.\n"
    page.get_by_label("Document content").fill(edited)
    page.get_by_label("Edit note (optional)").fill("Addressed staff request")
    page.get_by_role("button", name="Save edit").click()

    expect(page.get_by_role("status").filter(has_text="edited proposal was saved by the backend")).to_be_visible()
    assert api.edit_bodies == [{"content": edited, "note": "Addressed staff request"}]
    assert ("PUT", f"/api/document-workflows/{WORKFLOW_ID}/document", api.edit_bodies[0]) in api.requests
    assert not any(path == f"/api/documentation/{DOCUMENT_ID}" for _, path, _ in api.requests)
    expect(page.get_by_role("button", name="Accept")).to_have_count(0)
    expect(page.get_by_role("button", name="Dismiss")).to_have_count(0)


def test_edit_conflict_is_shown_without_success_message(page: Page):
    item = workflow("CHANGES_REQUESTED")
    item["ownerUserId"] = USER_ID
    api = FakeApi(item, edit_status=409)
    open_documentation(page, api)
    page.get_by_label("AI suggestion list").get_by_role("button", name="Shop API Guide").click()
    page.get_by_role("button", name="Edit proposal").click()
    page.get_by_role("button", name="Save edit").click()

    expect(page.get_by_role("alert").filter(has_text="workflow or document version changed")).to_be_visible()
    expect(page.get_by_role("status").filter(has_text="saved by the backend")).to_have_count(0)


def test_comparison_permission_and_conflict_errors_are_reported(page: Page):
    for status, expected in [
        (403, "You do not have permission to view comparison."),
        (409, "The workflow or document version changed."),
    ]:
        api = FakeApi(workflow(), comparison_status=status)
        page = page.context.new_page()
        open_documentation(page, api)
        page.get_by_label("AI suggestion list").get_by_role("button", name="Shop API Guide").click()
        expect(page.get_by_role("alert").filter(has_text=expected)).to_be_visible()
        expect(page.get_by_role("button", name="Retry loading review details")).to_be_visible()
        page.close()


def test_empty_suggestion_list_is_explained(page: Page):
    api = FakeApi(workflow())
    api.item = None
    open_documentation(page, api)

    expect(page.get_by_role("status").filter(has_text="No accessible review suggestions")).to_be_visible()
    expect(page.get_by_label("AI suggestion detail")).to_have_count(0)


def test_workflow_list_api_error_is_not_misreported_as_empty(page: Page):
    api = FakeApi(workflow(), workflow_status=503)
    open_documentation(page, api)

    expect(page.get_by_label("AI Suggestion Review").get_by_role("alert")).to_contain_text("Workflow list unavailable.")
    expect(page.get_by_role("status").filter(has_text="No accessible review suggestions")).to_have_count(0)


def test_invalid_workflow_list_response_is_not_misreported_as_empty(page: Page):
    api = FakeApi(workflow(), workflow_response={"items": []})
    open_documentation(page, api)

    expect(page.get_by_label("AI Suggestion Review").get_by_role("alert")).to_contain_text("workflow list response was invalid")
    expect(page.get_by_role("status").filter(has_text="No accessible review suggestions")).to_have_count(0)


def test_staff_can_retry_review_detail_after_api_error(page: Page):
    api = FakeApi(workflow(), comparison_status=503)
    open_documentation(page, api)
    page.get_by_label("AI suggestion list").get_by_role("button", name="Shop API Guide").click()
    expect(page.get_by_role("alert").filter(has_text="Workflow changed.")).to_be_visible()

    api.comparison_status = 200
    page.get_by_role("button", name="Retry loading review details").click()
    expect(page.get_by_text("Current approved content (v1)")).to_be_visible()
