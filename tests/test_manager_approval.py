"""LD-314 Manager Approval UI tests against the built frontend with intercepted API responses."""

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from math import ceil
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Page, expect

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
MANAGER_ID = "84"
STAFF_ID = "42"
WORKSPACE_ID = f"ws-{MANAGER_ID}"
REPOSITORY_ID = "11111111-1111-4111-8111-111111111111"
DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
WORKFLOW_ID = "33333333-3333-4333-8333-333333333333"


def workflow(status="PENDING_MANAGER_APPROVAL", workflow_id=WORKFLOW_ID, *, manager_comment=None, title="Shop API Guide"):
    return {
        "id": workflow_id,
        "documentId": DOCUMENT_ID,
        "documentTitle": title,
        "ownerUserId": "7",
        "status": status,
        "submittedDocumentVersion": 3 if status == "APPROVED" else 2,
        "reviewerUserId": STAFF_ID,
        "staffReviewResult": "PASSED",
        "staffComment": "The source evidence supports this update.",
        "managerUserId": MANAGER_ID if status in ("APPROVED", "REJECTED") else None,
        "managerDecision": status if status in ("APPROVED", "REJECTED") else None,
        "managerComment": manager_comment,
        "createdAt": "2026-11-09T08:00:00Z",
        "updatedAt": "2026-11-10T10:00:00Z",
        "submittedAt": "2026-11-10T09:00:00Z",
        "reviewedAt": "2026-11-10T09:30:00Z",
        "decidedAt": "2026-11-10T10:00:00Z" if status in ("APPROVED", "REJECTED") else None,
        "optimisticVersion": 3,
    }


def event(action, previous, new, actor=STAFF_ID, role="STAFF", comment="Reviewed evidence."):
    return {
        "id": f"audit-{action}", "actorUserId": actor, "actorRole": role, "action": action,
        "previousStatus": previous, "newStatus": new, "previousReviewerUserId": STAFF_ID,
        "newReviewerUserId": None, "comment": comment, "createdAt": "2026-11-10T10:05:00Z",
    }


def page_response(items, page, size):
    total = len(items)
    pages = ceil(total / size) if size else 0
    start = page * size
    return {
        "content": items[start:start + size], "page": page, "size": size,
        "totalElements": total, "totalPages": pages,
        "first": page == 0, "last": pages == 0 or page >= pages - 1,
    }


class FakeApi:
    def __init__(self, item=None, *, user_role="MANAGER", user_id=MANAGER_ID, queue_status=200, workflow_status=200, evidence_status=200,
                 history_status=200, approve_status=200, reject_status=200, rollback_status=200,
                 queue_items=None, history_items=None, page_size=20, queue_page_delay_seconds=0):
        self.item = item
        self.queue_items = queue_items
        self.history_items = history_items
        self.page_size = page_size
        self.queue_page_delay_seconds = queue_page_delay_seconds
        all_items = [item] if item else []
        all_items.extend(queue_items or [])
        all_items.extend(history_items or [])
        self.items_by_id = {str(row["id"]): row for row in all_items}
        self.user_role = user_role
        self.user_id = user_id
        self.queue_status = queue_status
        self.workflow_status = workflow_status
        self.evidence_status = evidence_status
        self.history_status = history_status
        self.approve_status = approve_status
        self.reject_status = reject_status
        self.rollback_status = rollback_status
        self.requests = []
        self.query_requests = []
        self.events = [event("PASSED", "STAFF_REVIEWING", "PENDING_MANAGER_APPROVAL")]
        self.events_by_workflow = {}

    def handle(self, route):
        request = route.request
        parsed_url = urlsplit(request.url)
        path = parsed_url.path.removeprefix(urlsplit(FRONTEND_URL).path)
        query = parse_qs(parsed_url.query)
        page = int(query.get("page", ["0"])[0])
        size = int(query.get("size", [str(self.page_size)])[0])
        body = json.loads(request.post_data) if request.post_data else None
        self.requests.append((request.method, path, body))
        self.query_requests.append((request.method, path, query))

        if (request.method, path) == ("GET", "/api/auth/me"):
            return route.fulfill(status=200, json={"id": int(self.user_id), "email": "manager@example.test", "role": self.user_role})
        if (request.method, path) == ("GET", "/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-ld314"})
        if (request.method, path) == ("GET", "/api/github/connection"):
            return route.fulfill(status=200, json={"connected": True})
        if (request.method, path) == ("GET", "/api/documentation/templates"):
            return route.fulfill(status=200, json=[])
        if (request.method, path) == ("GET", f"/api/workspaces/{WORKSPACE_ID}/repositories"):
            return route.fulfill(status=200, json=[{"id": REPOSITORY_ID, "fullName": "acme/shop", "status": "CONNECTED"}])
        if (request.method, path) == ("GET", f"/api/repositories/{REPOSITORY_ID}/documentation"):
            return route.fulfill(status=200, json=[])
        if (request.method, path) == ("GET", "/api/document-workflows/history-accessible"):
            items = self.history_items if self.history_items is not None else ([self.item] if self.item else [])
            return route.fulfill(status=200, json=page_response(items, page, size))
        if (request.method, path) == ("GET", "/api/document-workflows/manager/queue"):
            if page > 0 and self.queue_page_delay_seconds:
                time.sleep(self.queue_page_delay_seconds)
            if self.queue_status != 200:
                return route.fulfill(status=self.queue_status, json={"message": "Approval queue unavailable."})
            source = self.queue_items if self.queue_items is not None else ([self.item] if self.item else [])
            items = [row for row in source if row["status"] == "PENDING_MANAGER_APPROVAL"]
            return route.fulfill(status=200, json=page_response(items, page, size))
        if (request.method, path) == ("GET", "/api/document-workflows/staff/queue"):
            items = [self.item] if self.item and self.item["status"] in ("PENDING_STAFF_REVIEW", "STAFF_REVIEWING") else []
            return route.fulfill(status=200, json={"content": items, "page": 0, "size": 20,
                "totalElements": len(items), "totalPages": 1 if items else 0, "first": True, "last": True})
        if request.method == "GET" and path.startswith("/api/document-workflows/") and path.count("/") == 3:
            if self.workflow_status != 200:
                return route.fulfill(status=self.workflow_status, json={"message": "Workflow not found."})
            row = self.items_by_id.get(path.rsplit("/", 1)[-1], self.item)
            return route.fulfill(status=200, json=row)
        if request.method == "GET" and path.startswith("/api/document-workflows/") and path.endswith("/document"):
            selected = path.split("/")[-2]
            row = self.items_by_id.get(selected, self.item)
            return route.fulfill(status=200, json={"documentId": DOCUMENT_ID,
                "version": row["submittedDocumentVersion"], "content": "# Shop guide\n\nReviewed API contract.\n"})
        if request.method == "GET" and path.startswith("/api/document-workflows/") and path.endswith("/evidence"):
            if self.evidence_status != 200:
                return route.fulfill(status=self.evidence_status, json={"message": "Evidence unavailable."})
            return route.fulfill(status=200, json={"job_id": "job-1", "method": "ai", "files": [{
                "path": "src/shop.py", "status": "generated", "entities": [{"kind": "endpoint", "name": "GET /shop",
                    "evidence": [{"id": "E1", "kind": "source", "path": "src/shop.py", "line_start": 18,
                        "line_end": 21, "excerpt": "@app.get('/shop')"}]}], "context_used": [],
            }]})
        if request.method == "GET" and path.startswith("/api/document-workflows/") and path.endswith("/history"):
            if self.history_status != 200:
                return route.fulfill(status=self.history_status, json={"message": "History unavailable."})
            workflow_id = path.split("/")[-2]
            return route.fulfill(status=200, json=self.events_by_workflow.get(workflow_id, self.events))
        if (request.method, path) == ("POST", f"/api/document-workflows/{WORKFLOW_ID}/approve"):
            if self.approve_status != 200:
                return route.fulfill(status=self.approve_status, json={"message": "Workflow changed."})
            self.item.update(status="APPROVED", managerDecision="APPROVED", managerUserId=MANAGER_ID,
                managerComment=None, decidedAt="2026-11-11T10:00:00Z")
            self.events.append(event("APPROVED", "PENDING_MANAGER_APPROVAL", "APPROVED", MANAGER_ID, "MANAGER", None))
            return route.fulfill(status=200, json=self.item)
        if (request.method, path) == ("POST", f"/api/document-workflows/{WORKFLOW_ID}/reject"):
            if self.reject_status != 200:
                return route.fulfill(status=self.reject_status, json={"message": "Workflow changed."})
            self.item.update(status="REJECTED", managerDecision="REJECTED", managerUserId=MANAGER_ID,
                managerComment=body.get("comment"), decidedAt="2026-11-11T10:00:00Z")
            self.events.append(event("REJECTED", "PENDING_MANAGER_APPROVAL", "REJECTED", MANAGER_ID,
                "MANAGER", body.get("comment")))
            return route.fulfill(status=200, json=self.item)
        if (request.method, path) == ("POST", f"/api/document-workflows/{WORKFLOW_ID}/rollback"):
            if self.rollback_status != 200:
                return route.fulfill(status=self.rollback_status, json={"message": "Document version changed."})
            self.item.update(status="PENDING_STAFF_REVIEW", submittedDocumentVersion=4,
                reviewerUserId=None, staffReviewResult=None, staffComment=None, managerDecision=None,
                managerUserId=None, managerComment=None)
            self.events.append(event("ROLLBACK_REQUESTED", "APPROVED", "PENDING_STAFF_REVIEW", MANAGER_ID,
                "MANAGER", f"Restored from version {body['sourceVersion']}. Reason: {body['reason']}"))
            return route.fulfill(status=200, json=self.item)
        return route.fulfill(status=404, json={"message": f"Unexpected request: {request.method} {path}"})


def open_manager_approval(page: Page, api: FakeApi):
    page.route("**/api/**", api.handle)
    page.goto(FRONTEND_URL)
    page.get_by_role("button", name="Documentation Management").first.click()
    expect(page.get_by_role("heading", name="Manager Approval")).to_be_visible()
    page.get_by_role("button", name="Open Manager Approval").click()


def test_manager_queue_detail_shows_staff_result_evidence_and_audit(page: Page):
    api = FakeApi(workflow())
    open_manager_approval(page, api)

    expect(page.get_by_label("Manager approval queue").get_by_role("button", name="Shop API Guide")).to_contain_text("PASSED")
    detail = page.get_by_label("Manager approval detail")
    expect(detail).to_contain_text("Reviewed API contract.")
    expect(detail).to_contain_text("The source evidence supports this update.")
    expect(detail).to_contain_text("src/shop.py:18-21")
    expect(detail.get_by_label("Approval audit history")).to_contain_text("PASSED")
    expect(detail.get_by_label("Approval audit history")).to_contain_text("STAFF")
    assert ("GET", f"/api/document-workflows/{WORKFLOW_ID}/evidence", None) in api.requests
    assert ("GET", f"/api/document-workflows/{WORKFLOW_ID}/history", None) in api.requests


def test_empty_manager_queue(page: Page):
    open_manager_approval(page, FakeApi())
    expect(page.get_by_role("status").filter(has_text="No documents are waiting for Manager approval")).to_be_visible()


def test_approved_and_rejected_history_survives_reload_and_uses_backend_fields(page: Page):
    approved = workflow("APPROVED", "44444444-4444-4444-8444-444444444444")
    rejected_with_reason = workflow(
        "REJECTED", "55555555-5555-4555-8555-555555555555",
        manager_comment="Backend rejection reason from managerComment.",
    )
    rejected_without_reason = workflow("REJECTED", "66666666-6666-4666-8666-666666666666")
    api = FakeApi(history_items=[approved, rejected_with_reason, rejected_without_reason])
    api.events_by_workflow[rejected_with_reason["id"]] = [
        event("REJECTED", "PENDING_MANAGER_APPROVAL", "REJECTED", MANAGER_ID, "MANAGER",
              "Backend rejection reason from managerComment.")
    ]
    open_manager_approval(page, api)

    history = page.get_by_label("Manager decision history")
    expect(history.get_by_role("button", name="Shop API Guide").filter(has_text="APPROVED")).to_be_visible()
    expect(history.get_by_role("heading", name="Previously rejected")).to_be_visible()
    rejected_button = history.get_by_role("button", name="Shop API Guide").filter(has_text="REJECTED").first
    expect(rejected_button).to_be_visible()
    expect(page.get_by_label("Pending Manager decisions").get_by_role("button", name="Shop API Guide")).to_have_count(0)

    rejected_button.click()
    detail = page.get_by_label("Manager approval detail")
    expect(detail.get_by_label("Manager rejection reason")).to_contain_text(
        "Backend rejection reason from managerComment.")
    expect(detail.get_by_label("Approval audit history")).to_contain_text("REJECTED")
    expect(detail.get_by_label("Approval audit history")).to_contain_text(MANAGER_ID)
    expect(detail).to_contain_text("Decision time")

    page.reload()
    page.get_by_role("button", name="Documentation Management").first.click()
    page.get_by_role("button", name="Open Manager Approval").click()
    history = page.get_by_label("Manager decision history")
    expect(history.get_by_role("button", name="Shop API Guide").filter(has_text="REJECTED")).to_have_count(2)
    missing_reason = history.get_by_role("button", name="Shop API Guide").filter(has_text="REJECTED").nth(1)
    missing_reason.click()
    expect(page.get_by_label("Manager rejection reason")).to_contain_text(
        "The Backend did not provide a rejection reason.")


def test_manager_queue_pagination_uses_backend_metadata_and_bounds(page: Page):
    items = [workflow(workflow_id=f"77777777-7777-4777-8777-{index:012d}", title=f"Queue item {index}")
             for index in range(1, 26)]
    api = FakeApi(queue_items=items, history_items=[])
    open_manager_approval(page, api)

    queue = page.get_by_label("Pending Manager decisions")
    pagination = page.get_by_role("group", name="Manager approval queue pagination")
    expect(pagination.get_by_role("button", name="Previous")).to_be_disabled()
    expect(pagination).to_contain_text("Page 1 of 2 · 25 pending workflow(s)")
    expect(queue.get_by_role("button", name=re.compile(r"^Queue item "))).to_have_count(20)
    assert ("GET", "/api/document-workflows/manager/queue", {"page": ["0"], "size": ["20"]}) in api.query_requests

    pagination.get_by_role("button", name="Next").click()
    expect(pagination).to_contain_text("Page 2 of 2 · 25 pending workflow(s)")
    expect(queue.get_by_role("button", name=re.compile(r"^Queue item "))).to_have_count(5)
    expect(queue.get_by_role("button", name="Queue item 1")).to_have_count(0)
    expect(queue.get_by_role("button", name="Queue item 21")).to_be_visible()
    expect(pagination.get_by_role("button", name="Next")).to_be_disabled()
    expect(pagination.get_by_role("button", name="Previous")).to_be_enabled()
    assert ("GET", "/api/document-workflows/manager/queue", {"page": ["1"], "size": ["20"]}) in api.query_requests

    pagination.get_by_role("button", name="Previous").click()
    expect(pagination).to_contain_text("Page 1 of 2 · 25 pending workflow(s)")
    pages = [query["page"][0] for method, path, query in api.query_requests
             if method == "GET" and path == "/api/document-workflows/manager/queue"]
    assert pages == ["0", "1", "0"]


def test_manager_decision_history_pagination_keeps_rejected_items_reachable(page: Page):
    history_items = [
        workflow("REJECTED" if index == 25 else "APPROVED",
                 f"88888888-8888-4888-8888-{index:012d}",
                 manager_comment=f"Decision note {index}" if index == 25 else None)
        for index in range(1, 26)
    ]
    api = FakeApi(history_items=history_items)
    open_manager_approval(page, api)

    pagination = page.get_by_role("group", name="Manager decision history pagination")
    history = page.get_by_label("Manager decision history")
    expect(pagination).to_contain_text("Page 1 of 2 · 25 workflow(s)")
    expect(pagination.get_by_role("button", name="Previous")).to_be_disabled()
    expect(history.get_by_role("button", name="Shop API Guide").filter(has_text="REJECTED")).to_have_count(0)

    pagination.get_by_role("button", name="Next").click()
    expect(pagination).to_contain_text("Page 2 of 2 · 25 workflow(s)")
    expect(pagination.get_by_role("button", name="Next")).to_be_disabled()
    expect(history.get_by_role("button", name="Shop API Guide").filter(has_text="REJECTED")).to_have_count(1)
    assert ("GET", "/api/document-workflows/history-accessible", {"page": ["1"], "size": ["20"]}) in api.query_requests


def test_manager_queue_page_change_shows_loading_without_previous_page_rows(page: Page):
    items = [workflow(workflow_id=f"99999999-9999-4999-8999-{index:012d}", title=f"Delayed queue item {index}")
             for index in range(1, 26)]
    api = FakeApi(queue_items=items, history_items=[])
    open_manager_approval(page, api)

    class DelayedQueueHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(0.8)
            body = json.dumps(page_response(items, 1, 20)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "http://localhost:3000"))
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), DelayedQueueHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    page.route(
        "**/api/document-workflows/manager/queue?page=1&size=20",
        lambda route: route.continue_(url=f"http://localhost:{server.server_port}/delayed-queue"),
    )
    pagination = page.get_by_role("group", name="Manager approval queue pagination")
    try:
        pagination.get_by_role("button", name="Next").click()

        expect(page.get_by_role("status").filter(has_text="Loading Manager approval workflows")).to_be_visible()
        expect(page.get_by_role("button", name="Delayed queue item 1")).to_be_hidden()

        expect(page.get_by_role("group", name="Manager approval queue pagination")).to_contain_text("Page 2 of 2 · 25 pending workflow(s)")
        expect(page.get_by_role("button", name="Delayed queue item 21")).to_be_visible()
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


def test_approve_posts_without_body_refreshes_queue_and_audit(page: Page):
    api = FakeApi(workflow())
    open_manager_approval(page, api)
    page.get_by_role("button", name="Approve document").click()

    expect(page.get_by_role("status").filter(has_text="Backend confirmed APPROVED")).to_be_visible()
    expect(page.get_by_label("Last Manager workflow result")).to_contain_text("APPROVED")
    assert ("POST", f"/api/document-workflows/{WORKFLOW_ID}/approve", None) in api.requests
    expect(page.get_by_label("Approval audit history")).to_contain_text("APPROVED", timeout=7000)
    assert any(method == "GET" and path == f"/api/document-workflows/{WORKFLOW_ID}/history" for method, path, _ in api.requests)
    assert sum(method == "GET" and path == "/api/document-workflows/manager/queue" for method, path, _ in api.requests) >= 2


def test_reject_requires_reason_and_posts_backend_request(page: Page):
    api = FakeApi(workflow())
    open_manager_approval(page, api)
    page.get_by_role("button", name="Reject document").click()
    expect(page.get_by_label("Rejection reason")).to_have_js_property("validity.valueMissing", True)
    assert not any(path.endswith("/reject") for _, path, _ in api.requests)

    page.get_by_label("Rejection reason").fill("The evidence does not cover all endpoints.")
    page.get_by_role("button", name="Reject document").click()
    expect(page.get_by_role("status").filter(has_text="Backend confirmed REJECTED")).to_be_visible()
    assert ("POST", f"/api/document-workflows/{WORKFLOW_ID}/reject",
        {"comment": "The evidence does not cover all endpoints."}) in api.requests
    expect(page.get_by_label("Last Manager workflow result")).to_contain_text("The evidence does not cover all endpoints.")


def test_rollback_requires_valid_input_and_confirmation(page: Page):
    api = FakeApi(workflow("APPROVED"))
    open_manager_approval(page, api)
    expect(page.get_by_role("heading", name="Rollback approved document")).to_be_visible()
    page.get_by_label("Previous source version number").fill("3")
    page.get_by_label("Rollback reason").fill("Restore the last verified API reference.")
    page.get_by_role("button", name="Request rollback").click()
    expect(page.get_by_label("Previous source version number")).to_have_js_property("validity.rangeOverflow", True)
    assert not any(path.endswith("/rollback") for _, path, _ in api.requests)

    page.get_by_label("Previous source version number").fill("2")
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Request rollback").click()
    expect(page.get_by_role("status").filter(has_text="returned the document to Staff review")).to_be_visible()
    assert ("POST", f"/api/document-workflows/{WORKFLOW_ID}/rollback", {
        "sourceVersion": 2, "reason": "Restore the last verified API reference.",
    }) in api.requests
    expect(page.get_by_label("Last Manager workflow result")).to_contain_text("PENDING_STAFF_REVIEW")


def test_workflow_conflict_and_missing_workflow_are_reported(page: Page):
    api = FakeApi(workflow(), approve_status=409)
    open_manager_approval(page, api)
    page.get_by_role("button", name="Approve document").click()
    expect(page.get_by_role("alert").filter(has_text="workflow or document version changed")).to_be_visible()
    expect(page.get_by_label("Last Manager workflow result")).to_have_count(0)

    missing = FakeApi(workflow(), workflow_status=404)
    page2 = page.context.new_page()
    open_manager_approval(page2, missing)
    expect(page2.get_by_role("alert").filter(has_text="workflow or document was not found")).to_be_visible()
    expect(page2.get_by_role("button", name="Approve document")).to_have_count(0)


def test_backend_forbids_staff_and_user_without_manager_role(page: Page):
    api = FakeApi(user_role="STAFF", user_id=STAFF_ID)
    page.route("**/api/**", api.handle)
    page.goto(FRONTEND_URL)
    page.get_by_role("button", name="Documentation Management").first.click()

    expect(page.get_by_role("heading", name="Manager Approval")).to_have_count(0)
    expect(page.get_by_role("button", name="Open Manager Approval")).to_have_count(0)
    assert not any(path == "/api/document-workflows/manager/queue" for _, path, _ in api.requests)


def test_manager_queue_permission_denial_and_expired_session(page: Page):
    denied = FakeApi(queue_status=403)
    open_manager_approval(page, denied)
    expect(page.get_by_role("alert").filter(has_text="not authorized to view the Manager approval queue")).to_be_visible()
    expect(page.get_by_role("button", name="Approve document")).to_have_count(0)

    expired = FakeApi(queue_status=401)
    page2 = page.context.new_page()
    page2.route("**/api/**", expired.handle)
    page2.goto(FRONTEND_URL)
    page2.get_by_role("button", name="Documentation Management").first.click()
    page2.get_by_role("button", name="Open Manager Approval").click()
    expect(page2.get_by_role("alert").filter(has_text="Your LivingDocs session has expired")).to_be_visible()


def test_server_error_and_ineligible_staff_result_do_not_allow_decision(page: Page):
    server_error = FakeApi(queue_status=500)
    open_manager_approval(page, server_error)
    expect(page.get_by_role("alert").filter(has_text="Approval queue unavailable.")).to_be_visible()
    expect(page.get_by_role("button", name="Retry queue")).to_be_visible()

    ineligible = workflow()
    ineligible["staffReviewResult"] = "CHANGES_REQUESTED"
    invalid_transition = FakeApi(ineligible)
    page2 = page.context.new_page()
    open_manager_approval(page2, invalid_transition)
    expect(page2.get_by_role("alert").filter(has_text="not eligible for a Manager decision")).to_be_visible()
    expect(page2.get_by_role("button", name="Approve document")).to_have_count(0)
    expect(page2.get_by_role("button", name="Reject document")).to_have_count(0)


def test_full_ld310_submit_to_staff_to_manager_approval_history(page: Page):
    api = FakeApi(workflow("PENDING_STAFF_REVIEW"))
    api.item.update(staffReviewResult=None, staffComment=None, reviewerUserId=None, status="PENDING_STAFF_REVIEW")
    api.events = []
    role = {"id": int(STAFF_ID), "role": "STAFF"}

    def full_cycle_route(route):
        request = route.request
        if request.method == "GET" and request.url.endswith("/api/auth/me"):
            return route.fulfill(status=200, json={"id": role["id"], "email": "workflow@example.test", "role": role["role"]})
        if request.method == "POST" and request.url.endswith(f"/api/document-workflows/{WORKFLOW_ID}/claim"):
            api.item.update(status="STAFF_REVIEWING", reviewerUserId=STAFF_ID)
            api.events.append(event("CLAIMED", "PENDING_STAFF_REVIEW", "STAFF_REVIEWING", STAFF_ID, "STAFF", None))
            return route.fulfill(status=200, json=api.item)
        if request.method == "POST" and request.url.endswith(f"/api/document-workflows/{WORKFLOW_ID}/staff-review"):
            body = json.loads(request.post_data)
            api.item.update(status="PENDING_MANAGER_APPROVAL", staffReviewResult=body["result"], staffComment=body.get("comment"))
            api.events.append(event("PASSED", "STAFF_REVIEWING", "PENDING_MANAGER_APPROVAL", STAFF_ID, "STAFF", body.get("comment")))
            return route.fulfill(status=200, json=api.item)
        if request.method == "POST" and request.url.endswith(f"/api/document-workflows/{WORKFLOW_ID}/approve"):
            api.item.update(status="APPROVED", managerDecision="APPROVED", managerUserId=MANAGER_ID)
            api.events.append(event("APPROVED", "PENDING_MANAGER_APPROVAL", "APPROVED", MANAGER_ID, "MANAGER", None))
            return route.fulfill(status=200, json=api.item)
        return api.handle(route)

    page.route("**/api/**", full_cycle_route)
    page.goto(FRONTEND_URL)
    page.get_by_role("button", name="Documentation Management").first.click()
    page.get_by_role("button", name="Open Staff Review Queue").click()
    page.get_by_role("button", name="Claim review").click()
    expect(page.get_by_role("heading", name="Submit Staff review")).to_be_visible()
    page.get_by_label("Decision").select_option("PASSED")
    page.get_by_label("Review comment").fill("Evidence is sufficient for approval.")
    page.get_by_role("button", name="Submit review").click()
    expect(page.get_by_label("Submitted Staff review result")).to_contain_text("PENDING_MANAGER_APPROVAL")

    role.update(id=int(MANAGER_ID), role="MANAGER")
    page.reload()
    page.get_by_role("button", name="Documentation Management").first.click()
    page.get_by_role("button", name="Open Manager Approval").click()
    page.get_by_role("button", name="Approve document").click()
    expect(page.get_by_role("status").filter(has_text="Backend confirmed APPROVED")).to_be_visible()
    expect(page.get_by_label("Approval audit history")).to_contain_text("CLAIMED", timeout=7000)
    expect(page.get_by_label("Approval audit history")).to_contain_text("PASSED")
    expect(page.get_by_label("Approval audit history")).to_contain_text("APPROVED")
    assert [entry["action"] for entry in api.events] == ["CLAIMED", "PASSED", "APPROVED"]
