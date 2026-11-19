"""LD-403 browser regression for the staff-to-manager document workflow.

The real built frontend runs against a *stateful* fake backend that enforces the same rules as
DocumentWorkflowService (roles, statuses, 400/403/409/404 answers) and records an audit trail.
Most scenarios start from a workflow that is already PENDING_STAFF_REVIEW. The scenarios named
test_ui_* start earlier: they generate the documentation and use the "Submit for review" button,
which saves the document, creates the workflow and submits it (the Submit step of LD-403).
"""

import json
import os
from urllib.parse import urlsplit

from playwright.sync_api import Page, expect

from rbac_nav import open_screen

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
WORKFLOW_ID = "33333333-3333-4333-8333-333333333333"
REPOSITORY_ID = "11111111-1111-4111-8111-111111111111"

USERS = {
    "developer": {"id": 7, "role": "DEVELOPER"},
    "staff": {"id": 42, "role": "STAFF"},
    "manager": {"id": 84, "role": "MANAGER"},
}
STATUS_FOR_ROLE_ERROR = "The authenticated primary role cannot perform this workflow action."


class StatefulBackend:
    """Minimal in-memory model of the workflow API used by the frontend."""

    def __init__(self, seed=True):
        self.current = "staff"
        self.minute = 0
        self.requests = []
        self.forced = {}          # "approve" -> status code returned once
        self.race_claim = False   # another staff member claims right before our claim request
        self.item = None
        self.events = []
        self.comments = []
        self.document_version = 2
        self.document_content = "# Shop guide\n\nReviewed.\n"
        if seed:
            self.item = self._new_item("PENDING_STAFF_REVIEW")
            self.events = [self._event("7", "DEVELOPER", "SUBMITTED", "DRAFT", "PENDING_STAFF_REVIEW", None)]

    @staticmethod
    def _new_item(status):
        return {
            "id": WORKFLOW_ID, "documentId": DOCUMENT_ID, "documentTitle": "Shop API Guide",
            "ownerUserId": "7", "status": status, "submittedDocumentVersion": 2,
            "reviewerUserId": None, "staffReviewResult": None, "staffComment": None,
            "managerUserId": None, "managerDecision": None, "managerComment": None,
            "createdAt": "2026-11-09T08:00:00Z", "updatedAt": "2026-11-10T10:00:00Z",
            "submittedAt": "2026-11-10T09:00:00Z" if status != "DRAFT" else None,
            "reviewedAt": None, "decidedAt": None, "optimisticVersion": 1,
        }

    # ---------- helpers ----------

    @property
    def user(self):
        return USERS[self.current]

    @property
    def user_id(self):
        return str(self.user["id"])

    def login_as(self, who):
        self.current = who

    def mutating_posts(self):
        return [path.rsplit("/", 1)[-1] for method, path, _ in self.requests if method == "POST"]

    def _event(self, actor, role, action, previous, new, comment):
        self.minute += 1
        return {"id": f"audit-{self.minute}", "actorUserId": actor, "actorRole": role, "action": action,
                "previousStatus": previous, "newStatus": new, "previousReviewerUserId": None,
                "newReviewerUserId": None, "comment": comment,
                "documentVersion": self.item["submittedDocumentVersion"] if self.item else None,
                "createdAt": f"2026-11-10T10:{self.minute:02d}:00Z"}

    def _record(self, action, previous, comment=None):
        self.events.append(self._event(self.user_id, self.user["role"], action, previous,
                                       self.item["status"], comment))

    def _visible(self):
        if self.item is None:
            return False
        role, status, item = self.user["role"], self.item["status"], self.item
        if role == "DEVELOPER":
            return item["ownerUserId"] == self.user_id
        if role == "STAFF":
            open_for_staff = status in ("PENDING_STAFF_REVIEW", "STAFF_REVIEWING") and \
                item["reviewerUserId"] in (None, self.user_id)
            return open_for_staff or item["reviewerUserId"] == self.user_id
        if role == "MANAGER":
            return status in ("PENDING_MANAGER_APPROVAL", "APPROVED", "REJECTED")
        return False

    @staticmethod
    def _page(items):
        return {"content": items, "page": 0, "size": 20, "totalElements": len(items),
                "totalPages": 1 if items else 0, "first": True, "last": True}

    # ---------- request router ----------

    def handle(self, route):
        request = route.request
        parsed = urlsplit(request.url)
        path = parsed.path
        body = json.loads(request.post_data) if request.post_data else None
        self.requests.append((request.method, path, body))
        send = lambda status, payload=None: route.fulfill(status=status, json=payload if payload is not None else {})
        deny = lambda: send(403, {"message": STATUS_FOR_ROLE_ERROR})
        method = request.method
        base = "/api/document-workflows"
        # Same as the real stack: the Backend forwards a body-less POST as form-urlencoded and the endpoints
        # whose @RequestBody is optional answer HTTP 415 (found on the real stack during LD-403).
        optional_body = (method == "POST" and body is None and (
            path.endswith("/approve") or path.endswith("/reject")
            or (path.startswith("/api/documentation/jobs/") and path.endswith("/document"))))
        if optional_body:
            return send(415, {"status": 415, "code": "UNSUPPORTED_MEDIA_TYPE", "message": "Request failed (HTTP 415)."})

        if (method, path) == ("GET", "/api/auth/me"):
            return send(200, {"id": self.user["id"], "email": f"{self.current}@example.test", "role": self.user["role"]})
        if (method, path) == ("GET", "/api/auth/csrf"):
            return send(200, {"token": "csrf-ld403"})
        if (method, path) == ("GET", "/api/github/connection"):
            return send(200, {"connected": True})
        if (method, path) == ("GET", "/api/documentation/templates"):
            return send(200, [])
        if method == "GET" and path.startswith("/api/workspaces/") and path.endswith("/repositories"):
            return send(200, [{"id": REPOSITORY_ID, "fullName": "acme/shop", "status": "CONNECTED"}])
        if (method, path) == ("GET", f"/api/repositories/{REPOSITORY_ID}/documentation"):
            return send(200, [])

        if (method, path) == ("GET", f"{base}/history-accessible"):
            return send(200, self._page([self.item] if self._visible() else []))
        if (method, path) == ("GET", f"{base}/staff/queue"):
            if self.user["role"] != "STAFF":
                return deny()
            queued = self.item is not None and (
                self.item["status"] == "PENDING_STAFF_REVIEW"
                or (self.item["status"] == "STAFF_REVIEWING" and self.item["reviewerUserId"] == self.user_id))
            return send(200, self._page([self.item] if queued else []))
        if (method, path) == ("GET", f"{base}/manager/queue"):
            if self.user["role"] != "MANAGER":
                return deny()
            queued = self.item is not None and self.item["status"] == "PENDING_MANAGER_APPROVAL"
            return send(200, self._page([self.item] if queued else []))

        if (method, path) == ("POST", f"/api/repositories/{REPOSITORY_ID}/documentation/generate"):
            return send(202, {"id": "job-1", "status": "completed", "progress": 1, "message": "Completed",
                              "template_name": "Standard technical docs"})
        if (method, path) == ("GET", "/api/documentation/jobs/job-1/result"):
            return route.fulfill(status=200, body="# Shop guide\n\nGenerated.\n", content_type="text/markdown")
        if (method, path) == ("GET", "/api/documentation/jobs/job-1/report"):
            return send(200, {"files": []})
        if (method, path) == ("POST", "/api/documentation/jobs/job-1/document"):
            if "document" in self.forced:
                return send(self.forced.pop("document"), {"message": "Forced test failure."})
            if self.user["role"] != "DEVELOPER":
                return deny()
            return send(201, {"id": DOCUMENT_ID, "title": "Shop API Guide", "owner_user_id": self.user_id})
        if (method, path) == ("POST", base):
            if "document-workflows" in self.forced:
                return send(self.forced.pop("document-workflows"), {"message": "Forced test failure."})
            if self.user["role"] != "DEVELOPER":
                return deny()
            if self.item is not None:
                return send(409, {"message": "This document already has a review workflow."})
            self.item = self._new_item("DRAFT")
            self.item["ownerUserId"] = self.user_id
            self.events = []
            self._record("CREATED", None)
            return send(201, self.item)

        if method == "GET" and path.startswith(f"{base}/{WORKFLOW_ID}"):
            suffix = path.removeprefix(f"{base}/{WORKFLOW_ID}")
            if not self._visible():
                return send(404, {"message": "Document workflow not found."})
            if suffix == "":
                return send(200, self.item)
            if suffix == "/document":
                return send(200, {"documentId": DOCUMENT_ID, "version": self.document_version,
                                  "content": self.document_content})
            if suffix == "/comments":
                return send(200, self.comments)
            if suffix == "/change-requests":
                return send(200, [
                    dict(event, relatedComments=[comment for comment in self.comments
                         if comment["documentVersion"] == event["documentVersion"]])
                    for event in self.events if event["action"] == "CHANGES_REQUESTED"
                ])
            if suffix == "/history":
                return send(200, self.events)
            if suffix in ("/review-comparison", "/review-evidence"):
                assigned = self.item["status"] == "STAFF_REVIEWING" and self.item["reviewerUserId"] == self.user_id
                if self.user["role"] != "STAFF" or not assigned:
                    return deny()
                if suffix == "/review-comparison":
                    return send(200, {"approved_version": {"number": 1, "content": "# Old\n"},
                                      "pending_version": {"number": 2, "content": "# Shop guide\n"},
                                      "diff": "-Old\n+Shop guide\n"})
                return send(200, {"files": [], "source_snapshot": {"repository_full_name": "acme/shop",
                                  "branch": "main", "commit_sha": "abcdef1234567890"}})
            if suffix == "/evidence":
                if self.user["role"] != "MANAGER" or self.item["staffReviewResult"] != "PASSED":
                    return deny()
                return send(200, {"files": [], "source_snapshot": {"repository_full_name": "acme/shop",
                                  "branch": "main", "commit_sha": "abcdef1234567890"}})

        if method == "PUT" and path == f"{base}/{WORKFLOW_ID}/document":
            if self.item is None or self.user_id != self.item["ownerUserId"]:
                return send(404, {"message": "Document workflow not found."})
            if self.user["role"] != "DEVELOPER":
                return deny()
            if self.item["status"] != "CHANGES_REQUESTED" or body.get("expectedVersion") != self.document_version:
                return send(409, {"message": "Document version changed."})
            self.document_version += 1
            self.document_content = body["content"]
            self._record("DOCUMENT_EDITED", self.item["status"], body.get("note"))
            return send(200, self.item)

        if method == "POST" and path.startswith(f"{base}/{WORKFLOW_ID}/"):
            action = path.rsplit("/", 1)[-1]
            if action in self.forced:
                return send(self.forced.pop(action), {"message": "Forced test failure."})
            if self.item is None:
                return send(404, {"message": "Document workflow not found."})
            previous = self.item["status"]
            if action == "submit":
                if self.user["role"] != "DEVELOPER" or self.item["ownerUserId"] != self.user_id:
                    return send(404, {"message": "Document workflow not found."})
                if previous not in ("DRAFT", "CHANGES_REQUESTED"):
                    return send(409, {"message": "Only a draft or a changes-requested workflow can be submitted."})
                if (body or {}).get("expectedVersion", self.document_version) != self.document_version:
                    return send(409, {"message": "Document version changed."})
                if previous == "CHANGES_REQUESTED" and self.document_version <= self.item["submittedDocumentVersion"]:
                    return send(409, {"message": "Update the document version before resubmitting."})
                self.item.update(status="PENDING_STAFF_REVIEW", reviewerUserId=None, staffReviewResult=None,
                                 staffComment=None, submittedAt="2026-11-10T09:00:00Z",
                                 submittedDocumentVersion=self.document_version)
                self._record("SUBMITTED", previous)
                return send(200, self.item)
            if action == "claim":
                if self.user["role"] != "STAFF":
                    return deny()
                if self.race_claim:
                    self.race_claim = False
                    self.item.update(status="STAFF_REVIEWING", reviewerUserId="43")
                if previous != "PENDING_STAFF_REVIEW" or self.item["reviewerUserId"] not in (None, self.user_id):
                    return send(409, {"message": "Only a document pending staff review can be claimed."})
                self.item.update(status="STAFF_REVIEWING", reviewerUserId=self.user_id)
                self._record("CLAIMED", previous)
                return send(200, self.item)
            if action == "comments":
                if self.user["role"] != "STAFF" or previous != "STAFF_REVIEWING" or \
                        self.item["reviewerUserId"] != self.user_id:
                    return deny()
                if body.get("documentVersion") != self.item["submittedDocumentVersion"]:
                    return send(409, {"message": "Document version changed."})
                self._record("REVIEW_COMMENT", previous, body["comment"])
                comment = dict(body, id=self.events[-1]["id"], workflowId=WORKFLOW_ID,
                               actorUserId=self.user_id, createdAt=self.events[-1]["createdAt"])
                self.comments.append(comment)
                return send(201, comment)
            if action == "staff-review":
                if self.user["role"] != "STAFF" or previous != "STAFF_REVIEWING" or \
                        self.item["reviewerUserId"] != self.user_id:
                    return deny()
                result, comment = body["result"], (body.get("comment") or "").strip() or None
                if result == "CHANGES_REQUESTED" and not comment:
                    return send(400, {"message": "A comment is required when requesting changes."})
                self.item.update(staffReviewResult=result, staffComment=comment,
                                 status="PENDING_MANAGER_APPROVAL" if result == "PASSED" else "CHANGES_REQUESTED")
                self._record(result, previous, comment)
                return send(200, self.item)
            if action in ("approve", "reject"):
                if self.user["role"] != "MANAGER":
                    return deny()
                if previous != "PENDING_MANAGER_APPROVAL" or self.item["staffReviewResult"] != "PASSED":
                    return send(409, {"message": "Manager decisions require a successful staff review."})
                if self.item["reviewerUserId"] == self.user_id:
                    return deny()
                comment = ((body or {}).get("comment") or "").strip() or None
                if action == "reject" and not comment:
                    return send(400, {"message": "A rejection reason is required."})
                decision = "APPROVED" if action == "approve" else "REJECTED"
                self.item.update(status=decision, managerDecision=decision, managerUserId=self.user_id,
                                 managerComment=comment, decidedAt="2026-11-10T11:00:00Z")
                self._record(decision, previous, comment)
                return send(200, self.item)

        return send(404, {"message": f"Unexpected request: {method} {path}"})


# Each role works from its own screen of the role-based menu (frontend/src/rbac/flows).
ROLE_SCREEN = {
    "developer": ("Generated Documents", "Documentation Management"),
    "staff": ("Review Queue", "Staff Review Queue"),
    "manager": ("Approval Queue", "Manager Approval"),
}


def open_role_screen(page: Page, backend: StatefulBackend):
    label, heading = ROLE_SCREEN[backend.current]
    open_screen(page, label)
    expect(page.get_by_role("heading", name=heading)).to_be_visible()


def open_documentation(page: Page, backend: StatefulBackend):
    page.route("**/api/**", backend.handle)
    page.goto(FRONTEND_URL)
    open_role_screen(page, backend)


def switch_user(page: Page, backend: StatefulBackend, who: str):
    backend.login_as(who)
    page.reload()
    open_role_screen(page, backend)


def actions_in(locator):
    return [text.strip() for text in locator.locator("li strong").all_inner_texts()]


# ---------- end-to-end flows ----------

def test_section_feedback_revision_resubmission_and_final_approval(page: Page):
    backend = StatefulBackend()
    open_documentation(page, backend)
    page.get_by_role("button", name="Open Staff Review Queue").click()
    page.get_by_role("button", name="Claim review").click()
    content = page.locator("pre.staff-review-content")
    expect(content).to_contain_text("Reviewed.")
    content.evaluate("""element => {
        const range = document.createRange();
        const start = element.firstChild.textContent.indexOf('Reviewed.');
        range.setStart(element.firstChild, start);
        range.setEnd(element.firstChild, start + 'Reviewed.'.length);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    }""")
    page.get_by_label("Add review comment", exact=True).fill("Explain the authentication token.")
    page.get_by_role("button", name="Add comment", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Comment added.")).to_be_visible()
    comment_id = backend.comments[0]["id"]
    page.get_by_label("Decision").select_option("CHANGES_REQUESTED")
    page.get_by_label("Review comment", exact=True).fill("Clarify authentication before approval.")
    page.get_by_role("button", name="Submit review").click()
    expect(page.get_by_label("Submitted Staff review result")).to_contain_text("CHANGES_REQUESTED")

    switch_user(page, backend, "developer")
    feedback = page.get_by_role("region", name="Revision feedback")
    expect(feedback).to_contain_text("Clarify authentication before approval.")
    expect(feedback).to_contain_text("Explain the authentication token.")
    expect(feedback).to_contain_text("Reviewed.")
    page.get_by_label("Revised document Markdown").fill("# Shop guide\n\nUse a GitHub access token.")
    page.get_by_role("button", name="Save revision", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Revision saved as version 3.")).to_be_visible()
    page.get_by_role("button", name="Resubmit for review", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Version 3 submitted for Staff review.")).to_be_visible()

    switch_user(page, backend, "staff")
    page.get_by_role("button", name="Open Staff Review Queue").click()
    page.get_by_role("button", name="Claim review").click()
    expect(page.get_by_label("Referenced passage", exact=True)).to_have_text("Reviewed.")
    page.get_by_label("Decision").select_option("PASSED")
    page.get_by_label("Review comment", exact=True).fill("Authentication is now clear.")
    page.get_by_role("button", name="Submit review").click()
    expect(page.get_by_label("Submitted Staff review result")).to_contain_text("PENDING_MANAGER_APPROVAL")
    switch_user(page, backend, "manager")
    page.get_by_role("button", name="Open Manager Approval").click()
    page.get_by_role("button", name="Approve document").click()
    expect(page.get_by_role("status").filter(has_text="Backend confirmed APPROVED")).to_be_visible()
    switch_user(page, backend, "developer")
    history = page.get_by_role("region", name="Approval History")
    expect(history).to_contain_text("Clarify authentication before approval.")
    expect(history).to_contain_text("APPROVED")
    assert backend.item["id"] == WORKFLOW_ID
    assert backend.item["submittedDocumentVersion"] == 3
    assert backend.comments[0]["id"] == comment_id
    assert backend.comments[0]["documentVersion"] == 2
    assert backend.comments[0]["section"]["quote"] == "Reviewed."
    assert [event["action"] for event in backend.events] == [
        "SUBMITTED", "CLAIMED", "REVIEW_COMMENT", "CHANGES_REQUESTED", "DOCUMENT_EDITED",
        "SUBMITTED", "CLAIMED", "PASSED", "APPROVED",
    ]


def test_claim_staff_review_manager_approval_and_history_timeline(page: Page):
    backend = StatefulBackend()
    open_documentation(page, backend)

    page.get_by_role("button", name="Open Staff Review Queue").click()
    expect(page.get_by_role("button", name="Claim review")).to_be_visible()
    expect(page.get_by_role("heading", name="Submit Staff review")).to_have_count(0)
    page.get_by_role("button", name="Claim review").click()
    expect(page.get_by_role("status").filter(has_text="Workflow claimed.")).to_be_visible()
    expect(page.get_by_role("heading", name="Submit Staff review")).to_be_visible()

    page.get_by_label("Decision").select_option("PASSED")
    page.get_by_label("Review comment", exact=True).fill("Endpoints match the source code.")
    page.get_by_role("button", name="Submit review").click()
    expect(page.get_by_label("Submitted Staff review result")).to_contain_text("PENDING_MANAGER_APPROVAL")
    expect(page.get_by_role("button", name="Open Manager Approval")).to_have_count(0)

    switch_user(page, backend, "manager")
    page.get_by_role("button", name="Open Manager Approval").click()
    expect(page.get_by_role("button", name="Approve document")).to_be_visible()
    page.get_by_role("button", name="Approve document").click()
    expect(page.get_by_role("status").filter(has_text="Backend confirmed APPROVED")).to_be_visible()
    expect(page.get_by_role("button", name="Approve document")).to_have_count(0)

    manager_history = page.get_by_label("Approval audit history")
    expect(manager_history).to_contain_text("APPROVED", timeout=7000)
    assert actions_in(manager_history) == ["SUBMITTED", "CLAIMED", "PASSED", "APPROVED"]

    # The owner reads the Approval History panel of Documentation Management (Generated Documents).
    switch_user(page, backend, "developer")
    approval_history = page.get_by_role("region", name="Approval History")
    expect(approval_history).to_contain_text("Document ID")
    expect(approval_history.locator("li strong").first).to_be_visible()
    assert actions_in(approval_history) == ["SUBMITTED", "CLAIMED", "PASSED", "APPROVED"]
    expect(approval_history).to_contain_text("Actor role: MANAGER")
    expect(approval_history).to_contain_text("Previous status: PENDING_MANAGER_APPROVAL")

    assert backend.item["status"] == "APPROVED"
    assert backend.mutating_posts() == ["claim", "staff-review", "approve"]
    assert [event["action"] for event in backend.events] == ["SUBMITTED", "CLAIMED", "PASSED", "APPROVED"]


def test_manager_rejection_requires_reason_and_is_recorded_in_history(page: Page):
    backend = StatefulBackend()
    open_documentation(page, backend)
    page.get_by_role("button", name="Open Staff Review Queue").click()
    page.get_by_role("button", name="Claim review").click()
    page.get_by_label("Decision").select_option("PASSED")
    page.get_by_label("Review comment", exact=True).fill("Evidence is complete.")
    page.get_by_role("button", name="Submit review").click()
    expect(page.get_by_label("Submitted Staff review result")).to_contain_text("PENDING_MANAGER_APPROVAL")

    switch_user(page, backend, "manager")
    page.get_by_role("button", name="Open Manager Approval").click()
    page.get_by_role("button", name="Reject document").click()
    expect(page.get_by_label("Rejection reason")).to_have_js_property("validity.valueMissing", True)
    assert "reject" not in backend.mutating_posts()

    page.get_by_label("Rejection reason").fill("The guide omits the new endpoints.")
    page.get_by_role("button", name="Reject document").click()
    expect(page.get_by_role("status").filter(has_text="Backend confirmed REJECTED")).to_be_visible()
    expect(page.get_by_label("Last Manager workflow result")).to_contain_text("The guide omits the new endpoints.")
    expect(page.get_by_role("button", name="Approve document")).to_have_count(0)
    expect(page.get_by_role("button", name="Reject document")).to_have_count(0)

    manager_history = page.get_by_label("Approval audit history")
    expect(manager_history).to_contain_text("REJECTED", timeout=7000)
    assert actions_in(manager_history)[-1] == "REJECTED"
    expect(manager_history).to_contain_text("Comment: The guide omits the new endpoints.")
    switch_user(page, backend, "developer")
    approval_history = page.get_by_role("region", name="Approval History")
    expect(approval_history).to_contain_text("Comment / reason: The guide omits the new endpoints.")
    assert actions_in(approval_history)[-1] == "REJECTED"
    assert backend.item["status"] == "REJECTED"
    assert backend.mutating_posts() == ["claim", "staff-review", "reject"]


def test_staff_changes_requested_needs_a_comment_and_leaves_manager_queue_empty(page: Page):
    backend = StatefulBackend()
    open_documentation(page, backend)
    page.get_by_role("button", name="Open Staff Review Queue").click()
    page.get_by_role("button", name="Claim review").click()
    page.get_by_label("Decision").select_option("CHANGES_REQUESTED")
    page.get_by_role("button", name="Submit review").click()
    expect(page.get_by_label("Review comment", exact=True)).to_have_js_property("validity.valueMissing", True)
    assert "staff-review" not in backend.mutating_posts()

    page.get_by_label("Review comment", exact=True).fill("Explain the setup steps.")
    page.get_by_role("button", name="Submit review").click()
    expect(page.get_by_label("Submitted Staff review result")).to_contain_text("CHANGES_REQUESTED")
    assert backend.item["status"] == "CHANGES_REQUESTED"

    switch_user(page, backend, "manager")
    page.get_by_role("button", name="Open Manager Approval").click()
    expect(page.get_by_text("No documents are waiting for Manager approval.")).to_be_visible()
    expect(page.get_by_role("button", name="Approve document")).to_have_count(0)


# ---------- access control ----------

def test_staff_never_sees_manager_decision_actions(page: Page):
    backend = StatefulBackend()
    backend.item.update(status="PENDING_MANAGER_APPROVAL", reviewerUserId="42", staffReviewResult="PASSED",
                        staffComment="Checks passed")
    open_documentation(page, backend)

    expect(page.get_by_role("heading", name="Manager Approval")).to_have_count(0)
    expect(page.get_by_role("button", name="Open Manager Approval")).to_have_count(0)
    page.get_by_role("button", name="Open Staff Review Queue").click()
    expect(page.get_by_text("No workflows are currently available in your Staff review queue.")).to_be_visible()
    for name in ("Approve document", "Reject document", "Request rollback"):
        expect(page.get_by_role("button", name=name)).to_have_count(0)
    assert not any(path.endswith("/manager/queue") for _, path, _ in backend.requests)

    # While reviewing, staff has review controls but still no decision actions.
    backend.item.update(status="STAFF_REVIEWING", staffReviewResult=None, staffComment=None)
    page.get_by_role("button", name="Refresh queue").click()
    expect(page.get_by_role("heading", name="Submit Staff review")).to_be_visible()
    expect(page.get_by_role("button", name="Approve document")).to_have_count(0)
    expect(page.get_by_role("button", name="Reject document")).to_have_count(0)


def test_developer_role_gets_no_workflow_actions(page: Page):
    backend = StatefulBackend()
    backend.login_as("developer")
    open_documentation(page, backend)

    # Matrix row #10: a Developer only reads review feedback, so neither queue panel is offered
    # (the backend would answer 403 for the Staff queue).
    expect(page.get_by_role("button", name="Open Manager Approval")).to_have_count(0)
    expect(page.get_by_role("button", name="Open Staff Review Queue")).to_have_count(0)
    assert not any(path.endswith("/staff/queue") for _, path, _ in backend.requests)
    for name in ("Claim review", "Release claim", "Submit review", "Approve document", "Reject document"):
        expect(page.get_by_role("button", name=name)).to_have_count(0)
    assert backend.mutating_posts() == []


# ---------- error handling ----------

def test_claim_conflict_409_shows_error_and_keeps_the_workflow_unclaimed_in_the_ui(page: Page):
    backend = StatefulBackend()
    backend.race_claim = True      # another staff member claims it right before this request
    open_documentation(page, backend)
    page.get_by_role("button", name="Open Staff Review Queue").click()
    page.get_by_role("button", name="Claim review").click()

    expect(page.get_by_role("alert").filter(has_text="claimed by another Staff member")).to_be_visible()
    expect(page.get_by_role("heading", name="Submit Staff review")).to_have_count(0)
    expect(page.get_by_role("status").filter(has_text="Workflow claimed.")).to_have_count(0)
    assert backend.item["reviewerUserId"] == "43"

    page.get_by_role("button", name="Refresh queue").click()
    expect(page.get_by_text("No workflows are currently available in your Staff review queue.")).to_be_visible()
    assert backend.mutating_posts() == ["claim"]


def test_manager_decision_403_and_409_do_not_corrupt_the_ui_state(page: Page):
    backend = StatefulBackend()
    backend.item.update(status="PENDING_MANAGER_APPROVAL", reviewerUserId="42", staffReviewResult="PASSED",
                        staffComment="Checks passed")
    backend.login_as("manager")
    open_documentation(page, backend)
    page.get_by_role("button", name="Open Manager Approval").click()
    approve = page.get_by_role("button", name="Approve document")
    expect(approve).to_be_visible()

    backend.forced["approve"] = 403
    approve.click()
    expect(page.get_by_role("alert").filter(has_text="You are not authorized to submit approved decision.")).to_be_visible()
    expect(page.get_by_label("Last Manager workflow result")).to_have_count(0)
    expect(approve).to_be_enabled()

    backend.forced["approve"] = 409
    approve.click()
    expect(page.get_by_role("alert").filter(has_text="workflow or document version changed")).to_be_visible()
    expect(page.get_by_label("Last Manager workflow result")).to_have_count(0)
    expect(approve).to_be_enabled()
    assert backend.item["status"] == "PENDING_MANAGER_APPROVAL"

    approve.click()          # the next, unforced request succeeds
    expect(page.get_by_role("status").filter(has_text="Backend confirmed APPROVED")).to_be_visible()
    assert backend.item["status"] == "APPROVED"


def test_expired_session_during_claim_returns_to_login(page: Page):
    backend = StatefulBackend()
    open_documentation(page, backend)
    page.get_by_role("button", name="Open Staff Review Queue").click()
    backend.forced["claim"] = 401
    page.get_by_role("button", name="Claim review").click()
    expect(page.get_by_text("Your LivingDocs session has expired. Please sign in again.")).to_be_visible()
    assert backend.item["status"] == "PENDING_STAFF_REVIEW"


# ---------- the Submit step through the UI (generate -> Submit for review) ----------

def generate_documentation(page: Page):
    expect(page.get_by_role("button", name="Generate documentation")).to_be_enabled()
    page.get_by_role("button", name="Generate documentation").click()
    expect(page.get_by_text("Generation completed")).to_be_visible()
    expect(page.get_by_role("heading", name="Submit for review")).to_be_visible()


def test_ui_submit_then_claim_review_approve_and_full_history(page: Page):
    backend = StatefulBackend(seed=False)
    backend.login_as("developer")
    open_documentation(page, backend)

    # Nothing exists until the owner submits.
    assert backend.item is None
    generate_documentation(page)
    page.get_by_role("button", name="Submit for review").click()
    expect(page.get_by_role("status").filter(has_text="Submitted for Staff review")).to_be_visible()
    expect(page.get_by_role("button", name="Submitted for review")).to_be_disabled()

    approval_history = page.get_by_role("region", name="Approval History")
    expect(approval_history).to_contain_text("Document ID")
    assert actions_in(approval_history) == ["CREATED", "SUBMITTED"]
    assert backend.mutating_posts() == ["generate", "document", "document-workflows", "submit"]
    assert backend.item["status"] == "PENDING_STAFF_REVIEW"
    # the save step sends an empty JSON body (a body-less POST is answered with 415 on the real stack)
    assert ("POST", "/api/documentation/jobs/job-1/document", {}) in backend.requests

    switch_user(page, backend, "staff")
    page.get_by_role("button", name="Open Staff Review Queue").click()
    page.get_by_role("button", name="Claim review").click()
    page.get_by_label("Decision").select_option("PASSED")
    page.get_by_label("Review comment", exact=True).fill("Matches the code.")
    page.get_by_role("button", name="Submit review").click()
    expect(page.get_by_label("Submitted Staff review result")).to_contain_text("PENDING_MANAGER_APPROVAL")

    switch_user(page, backend, "manager")
    page.get_by_role("button", name="Open Manager Approval").click()
    page.get_by_role("button", name="Approve document").click()
    expect(page.get_by_role("status").filter(has_text="Backend confirmed APPROVED")).to_be_visible()

    switch_user(page, backend, "developer")
    full = page.get_by_role("region", name="Approval History")
    expect(full.locator("li strong").first).to_be_visible()
    assert actions_in(full) == ["CREATED", "SUBMITTED", "CLAIMED", "PASSED", "APPROVED"]
    assert backend.item["status"] == "APPROVED"


def test_ui_submit_is_blocked_while_local_edits_are_not_part_of_the_submission(page: Page):
    backend = StatefulBackend(seed=False)
    backend.login_as("developer")
    open_documentation(page, backend)
    generate_documentation(page)

    submit = page.get_by_role("button", name="Submit for review")
    expect(submit).to_be_enabled()
    page.get_by_label("Markdown content").fill("# My own edit\n")
    expect(submit).to_be_disabled()
    expect(page.get_by_text("Local edits are not part of the submission")).to_be_visible()

    page.get_by_role("button", name="Restore original").click()
    expect(submit).to_be_enabled()
    assert backend.mutating_posts() == ["generate"]
    assert backend.item is None


def test_ui_submit_retry_continues_from_the_failed_step_without_duplicates(page: Page):
    backend = StatefulBackend(seed=False)
    backend.login_as("developer")
    open_documentation(page, backend)
    generate_documentation(page)

    backend.forced["submit"] = 500
    page.get_by_role("button", name="Submit for review").click()
    expect(page.get_by_role("alert").filter(has_text="Forced test failure.")).to_be_visible()
    expect(page.get_by_role("button", name="Submit for review")).to_be_enabled()
    assert backend.item["status"] == "DRAFT"      # saved and created, not yet submitted

    page.get_by_role("button", name="Submit for review").click()
    expect(page.get_by_role("status").filter(has_text="Submitted for Staff review")).to_be_visible()
    expect(page.get_by_role("alert").filter(has_text="Forced test failure.")).to_have_count(0)
    # The document and the workflow are created once; only the failed step is repeated.
    assert backend.mutating_posts() == ["generate", "document", "document-workflows", "submit", "submit"]
    assert backend.item["status"] == "PENDING_STAFF_REVIEW"


def test_ui_submit_shows_403_when_the_backend_refuses_to_save_the_document(page: Page):
    backend = StatefulBackend(seed=False)
    backend.login_as("developer")
    open_documentation(page, backend)
    generate_documentation(page)

    backend.forced["document"] = 403
    page.get_by_role("button", name="Submit for review").click()
    expect(page.get_by_role("alert").filter(has_text="You are not allowed to save the generated document")).to_be_visible()
    expect(page.get_by_role("button", name="Submit for review")).to_be_enabled()
    assert backend.item is None
    assert backend.mutating_posts() == ["generate", "document"]


def test_ui_submit_explains_an_expired_generation_job(page: Page):
    backend = StatefulBackend(seed=False)
    backend.login_as("developer")
    open_documentation(page, backend)
    generate_documentation(page)

    backend.forced["document"] = 404
    page.get_by_role("button", name="Submit for review").click()
    expect(page.get_by_role("alert").filter(has_text="generation job was not found")).to_be_visible()
    assert backend.item is None
