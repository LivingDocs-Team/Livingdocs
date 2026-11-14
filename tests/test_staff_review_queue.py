"""LD-313 Staff Review Queue browser tests using the real frontend and intercepted API responses."""

import json
import os
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, expect

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
USER_ID = "42"
WORKSPACE_ID = f"ws-{USER_ID}"
REPOSITORY_ID = "11111111-1111-4111-8111-111111111111"
DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
WORKFLOW_ID = "33333333-3333-4333-8333-333333333333"


def workflow(status="PENDING_STAFF_REVIEW", reviewer=None, workflow_id=WORKFLOW_ID, title="Shop API Guide"):
    return {
        "id": workflow_id,
        "documentId": DOCUMENT_ID,
        "documentTitle": title,
        "ownerUserId": "7",
        "status": status,
        "submittedDocumentVersion": 2,
        "reviewerUserId": reviewer,
        "staffReviewResult": None,
        "staffComment": None,
        "managerUserId": None,
        "managerDecision": None,
        "managerComment": None,
        "createdAt": "2026-11-10T09:30:00Z",
        "updatedAt": "2026-11-10T10:00:00Z",
        "optimisticVersion": 1,
    }


class FakeApi:
    def __init__(self, item=None, *, queue_status=200, workflow_status=200, claim_status=200,
                 release_status=200, review_status=200, queue_response=None, queue_pages=None):
        self.item = item
        self.queue_status = queue_status
        self.workflow_status = workflow_status
        self.claim_status = claim_status
        self.release_status = release_status
        self.review_status = review_status
        self.queue_response = queue_response
        self.queue_pages = queue_pages
        self.review_submitted = False
        self.requested_queue_pages = []
        self.requests = []
        self.review_bodies = []

    def handle(self, route):
        request = route.request
        path = request.url.split("?", 1)[0].removeprefix(FRONTEND_URL)
        body = json.loads(request.post_data) if request.post_data else None
        self.requests.append((request.method, path, body))

        if (request.method, path) == ("GET", "/api/auth/me"):
            return route.fulfill(status=200, json={"id": int(USER_ID), "email": "staff@example.test"})
        if (request.method, path) == ("GET", "/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-ld313"})
        if (request.method, path) == ("GET", "/api/github/connection"):
            return route.fulfill(status=200, json={"connected": True})
        if (request.method, path) == ("GET", "/api/documentation/templates"):
            return route.fulfill(status=200, json=[])
        if (request.method, path) == ("GET", f"/api/workspaces/{WORKSPACE_ID}/repositories"):
            return route.fulfill(status=200, json=[{
                "id": REPOSITORY_ID, "workspaceId": WORKSPACE_ID, "fullName": "acme/shop",
                "defaultBranch": "main", "privateRepo": False, "status": "CONNECTED",
            }])
        if (request.method, path) == ("GET", f"/api/repositories/{REPOSITORY_ID}/documentation"):
            return route.fulfill(status=200, json=[])
        if (request.method, path) == ("GET", "/api/document-workflows/history-accessible"):
            return route.fulfill(status=200, json={"content": [], "page": 0, "size": 20,
                "totalElements": 0, "totalPages": 0, "first": True, "last": True})
        if (request.method, path) == ("GET", "/api/document-workflows/staff/queue"):
            if self.queue_status != 200:
                return route.fulfill(status=self.queue_status, json={"message": "Staff queue unavailable."})
            if self.queue_response is not None:
                return route.fulfill(status=200, json=self.queue_response)
            if self.queue_pages is not None:
                page = int(parse_qs(urlparse(request.url).query).get("page", ["0"])[0])
                self.requested_queue_pages.append(page)
                if self.review_submitted:
                    items = [] if page > 0 else self.queue_pages.get(0, [])
                    return route.fulfill(status=200, json={"content": items, "page": page, "size": 20,
                        "totalElements": 20, "totalPages": 1, "first": page == 0, "last": True})
                items = self.queue_pages.get(page, [])
                return route.fulfill(status=200, json={"content": items, "page": page, "size": 20,
                    "totalElements": 21, "totalPages": 2, "first": page == 0, "last": page == 1})
            items = [self.item] if self.item and self.item["status"] in ("PENDING_STAFF_REVIEW", "STAFF_REVIEWING") else []
            return route.fulfill(status=200, json={"content": items, "page": 0, "size": 20,
                "totalElements": len(items), "totalPages": 1 if items else 0, "first": True, "last": True})
        if self.queue_pages is not None and request.method == "GET":
            workflow_id = path.removeprefix("/api/document-workflows/").split("/", 1)[0]
            for item in (entry for items in self.queue_pages.values() for entry in items):
                if str(item["id"]) == workflow_id and path.endswith(f"/{workflow_id}"):
                    return route.fulfill(status=200, json=item)
            if path.endswith("/document"):
                return route.fulfill(status=200, json={
                    "documentId": DOCUMENT_ID, "version": 2, "content": "# Shop guide\n\nCurrent API content.\n",
                })
        if (request.method, path) == ("GET", f"/api/document-workflows/{WORKFLOW_ID}"):
            if self.workflow_status != 200:
                return route.fulfill(status=self.workflow_status, json={"message": "Workflow not found."})
            return route.fulfill(status=200, json=self.item)
        if (request.method, path) == ("GET", f"/api/document-workflows/{WORKFLOW_ID}/document"):
            return route.fulfill(status=200, json={
                "documentId": DOCUMENT_ID, "version": 2, "content": "# Shop guide\n\nCurrent API content.\n",
            })
        if (request.method, path) == ("GET", f"/api/document-workflows/{WORKFLOW_ID}/review-comparison"):
            return route.fulfill(status=200, json={
                "approved_version": {"number": 1, "content": "# Shop guide\n\nOld API content.\n"},
                "pending_version": {"number": 2, "content": "# Shop guide\n\nCurrent API content.\n"},
                "diff": "-Old API content.\n+Current API content.\n",
            })
        if (request.method, path) == ("GET", f"/api/document-workflows/{WORKFLOW_ID}/review-evidence"):
            return route.fulfill(status=200, json={
                "files": [{"path": "src/shop.py", "status": "generated", "entities": [{
                    "kind": "endpoint", "name": "GET /shop", "evidence": [{
                        "id": "E1", "kind": "source", "path": "src/shop.py", "line_start": 10,
                        "line_end": 12, "excerpt": "@app.get('/shop')",
                    }],
                }]}],
                "source_snapshot": {"repository_full_name": "acme/shop", "branch": "main",
                    "commit_sha": "abcdef1234567890"},
                "source_verification": {"status": "MATCH", "message": "Snapshot verified."},
            })
        if (request.method, path) == ("POST", f"/api/document-workflows/{WORKFLOW_ID}/claim"):
            if self.claim_status != 200:
                return route.fulfill(status=self.claim_status, json={"message": "Workflow already claimed."})
            self.item.update(status="STAFF_REVIEWING", reviewerUserId=USER_ID)
            return route.fulfill(status=200, json=self.item)
        if (request.method, path) == ("POST", f"/api/document-workflows/{WORKFLOW_ID}/release"):
            if self.release_status != 200:
                return route.fulfill(status=self.release_status, json={"message": "Workflow changed."})
            self.item.update(status="PENDING_STAFF_REVIEW", reviewerUserId=None)
            return route.fulfill(status=200, json=self.item)
        if (request.method, path) == ("POST", f"/api/document-workflows/{WORKFLOW_ID}/staff-review"):
            self.review_bodies.append(body)
            if self.review_status != 200:
                return route.fulfill(status=self.review_status, json={"message": "Workflow changed."})
            result = body["result"]
            self.item.update(
                staffReviewResult=result,
                staffComment=body.get("comment"),
                status="PENDING_MANAGER_APPROVAL" if result == "PASSED" else "CHANGES_REQUESTED",
            )
            self.review_submitted = True
            return route.fulfill(status=200, json=self.item)
        return route.fulfill(status=404, json={"message": f"Unexpected request: {request.method} {path}"})


def open_documentation(page: Page, api: FakeApi):
    page.route("**/api/**", api.handle)
    page.goto(FRONTEND_URL)
    page.get_by_role("button", name="Documentation Management").first.click()
    expect(page.get_by_role("heading", name="Documentation Management")).to_be_visible()
    expect(page.get_by_role("heading", name="Staff Review Queue")).to_be_visible()
    page.get_by_role("button", name="Open Staff Review Queue").click()


def test_staff_queue_displays_workflow_details_and_review_evidence(page: Page):
    api = FakeApi(workflow("STAFF_REVIEWING", USER_ID))
    open_documentation(page, api)

    queue = page.get_by_label("Staff review queue items")
    expect(queue.get_by_role("button", name="Shop API Guide")).to_contain_text("STAFF_REVIEWING")
    expect(page.get_by_label("Staff review detail")).to_contain_text("acme/shop")
    expect(page.get_by_label("Staff review detail")).to_contain_text("Current API content.")
    expect(page.get_by_label("Staff review detail")).to_contain_text("AI suggestion comparison")
    expect(page.get_by_label("Staff review detail")).to_contain_text("src/shop.py:10-12")
    expect(page.get_by_label("Staff review detail")).to_contain_text("MATCH")
    assert ("GET", "/api/document-workflows/staff/queue", None) in api.requests
    assert ("GET", f"/api/document-workflows/{WORKFLOW_ID}", None) in api.requests


def test_empty_staff_queue(page: Page):
    open_documentation(page, FakeApi())
    expect(page.get_by_role("status").filter(has_text="No workflows are currently available")).to_be_visible()


def test_invalid_staff_queue_response_is_reported_instead_of_empty_state(page: Page):
    api = FakeApi(queue_response={"items": []})
    open_documentation(page, api)

    expect(page.get_by_role("alert")).to_contain_text("Staff queue response did not include a workflow list")
    expect(page.get_by_role("status").filter(has_text="No workflows are currently available")).to_have_count(0)


def test_claim_success_refreshes_queue_and_opens_review_controls(page: Page):
    api = FakeApi(workflow())
    open_documentation(page, api)
    page.get_by_role("button", name="Claim review").click()

    expect(page.get_by_role("status").filter(has_text="Workflow claimed.")).to_be_visible()
    expect(page.get_by_role("button", name="Release claim")).to_be_visible()
    expect(page.get_by_role("heading", name="Submit Staff review")).to_be_visible()
    assert ("POST", f"/api/document-workflows/{WORKFLOW_ID}/claim", None) in api.requests
    assert sum(path == "/api/document-workflows/staff/queue" for method, path, _ in api.requests if method == "GET") >= 2


def test_claim_conflict_does_not_claim_workflow(page: Page):
    api = FakeApi(workflow(), claim_status=409)
    open_documentation(page, api)
    page.get_by_role("button", name="Claim review").click()

    expect(page.get_by_role("alert").filter(has_text="claimed by another Staff member")).to_be_visible()
    expect(page.get_by_role("button", name="Claim review")).to_be_visible()
    expect(page.get_by_role("button", name="Release claim")).to_have_count(0)


def test_release_success_refreshes_and_unclaims_workflow(page: Page):
    api = FakeApi(workflow("STAFF_REVIEWING", USER_ID))
    open_documentation(page, api)
    page.get_by_role("button", name="Release claim").click()

    expect(page.get_by_role("status").filter(has_text="Workflow released.")).to_be_visible()
    expect(page.get_by_role("button", name="Claim review")).to_be_visible()
    assert ("POST", f"/api/document-workflows/{WORKFLOW_ID}/release", None) in api.requests


def test_staff_review_passed_submits_comment_and_displays_backend_result(page: Page):
    api = FakeApi(workflow("STAFF_REVIEWING", USER_ID))
    open_documentation(page, api)
    page.get_by_label("Decision").select_option("PASSED")
    page.get_by_label("Review comment").fill("The document matches the source.")
    page.get_by_role("button", name="Submit review").click()

    expect(page.get_by_role("heading", name="Review submitted")).to_be_visible()
    expect(page.get_by_label("Submitted Staff review result")).to_contain_text("PASSED")
    expect(page.get_by_label("Submitted Staff review result")).to_contain_text("PENDING_MANAGER_APPROVAL")
    assert api.review_bodies == [{"result": "PASSED", "comment": "The document matches the source."}]
    assert ("POST", f"/api/document-workflows/{WORKFLOW_ID}/staff-review", api.review_bodies[0]) in api.requests


def test_reviewing_last_item_on_last_page_returns_to_remaining_queue_items(page: Page):
    remaining = workflow(workflow_id="44444444-4444-4444-8444-444444444444", title="Remaining guide")
    assigned = workflow("STAFF_REVIEWING", USER_ID)
    api = FakeApi(assigned, queue_pages={0: [remaining], 1: [assigned]})
    open_documentation(page, api)

    page.get_by_role("button", name="Next").click()
    expect(page.get_by_role("status").filter(has_text="Page 2 of 2")).to_be_visible()
    page.get_by_label("Decision").select_option("PASSED")
    page.get_by_label("Review comment").fill("Reviewed against the source.")
    page.get_by_role("button", name="Submit review").click()

    expect(page.get_by_label("Staff review queue items").get_by_role("button", name="Remaining guide")).to_be_visible()
    expect(page.get_by_role("button", name="Next")).to_have_count(0)
    assert api.requested_queue_pages[-1] == 0


def test_changes_requested_requires_comment_and_backend_response_is_shown(page: Page):
    api = FakeApi(workflow("STAFF_REVIEWING", USER_ID))
    open_documentation(page, api)
    page.get_by_label("Decision").select_option("CHANGES_REQUESTED")
    expect(page.get_by_role("button", name="Submit review")).to_be_enabled()
    page.get_by_role("button", name="Submit review").click()
    expect(page.get_by_label("Review comment")).to_have_js_property("validity.valueMissing", True)
    assert api.review_bodies == []

    page.get_by_label("Review comment").fill("Please clarify the authentication requirements.")
    page.get_by_role("button", name="Submit review").click()
    expect(page.get_by_label("Submitted Staff review result")).to_contain_text("CHANGES_REQUESTED")
    assert api.review_bodies == [{"result": "CHANGES_REQUESTED", "comment": "Please clarify the authentication requirements."}]


def test_review_conflict_shows_error_without_fake_success(page: Page):
    api = FakeApi(workflow("STAFF_REVIEWING", USER_ID), review_status=409)
    open_documentation(page, api)
    page.get_by_label("Decision").select_option("PASSED")
    page.get_by_role("button", name="Submit review").click()

    expect(page.get_by_role("alert").filter(has_text="workflow changed or was claimed")).to_be_visible()
    expect(page.get_by_role("heading", name="Review submitted")).to_have_count(0)


def test_backend_permission_denial_and_missing_workflow_are_reported(page: Page):
    denied = FakeApi(queue_status=403)
    open_documentation(page, denied)
    expect(page.get_by_role("alert").filter(has_text="not authorized to view the Staff review queue")).to_be_visible()
    expect(page.get_by_role("button", name="Claim review")).to_have_count(0)

    missing = FakeApi(workflow("STAFF_REVIEWING", USER_ID), workflow_status=404)
    page2 = page.context.new_page()
    open_documentation(page2, missing)
    expect(page2.get_by_role("alert").filter(has_text="no longer available")).to_be_visible()
    expect(page2.get_by_role("button", name="Submit review")).to_have_count(0)


def test_expired_session_uses_existing_unauthenticated_flow(page: Page):
    api = FakeApi(queue_status=401)
    page.route("**/api/**", api.handle)
    page.goto(FRONTEND_URL)
    page.get_by_role("button", name="Documentation Management").first.click()
    page.get_by_role("button", name="Open Staff Review Queue").click()

    expect(page.get_by_role("alert").filter(has_text="Your LivingDocs session has expired")).to_be_visible()
    expect(page.get_by_role("button", name="Claim review")).to_have_count(0)
