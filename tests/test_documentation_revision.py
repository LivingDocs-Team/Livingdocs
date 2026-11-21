"""LD-249 revision browser tests against the real frontend with intercepted APIs."""

import json

from playwright.sync_api import Page, expect
from rbac_nav import open_screen
from test_staff_review_queue import (
    FakeApi, workflow, USER_ID, WORKFLOW_ID, DOCUMENT_ID, FRONTEND_URL,
)


class RevisionApi(FakeApi):
    def __init__(self, *, save_status=200, submit_status=200):
        super().__init__(workflow("CHANGES_REQUESTED", "81"))
        self.item["ownerUserId"] = USER_ID
        self.item["staffComment"] = "Explain authentication."
        self.version = 2
        self.content = "# API\n\nAuthentication required."
        self.save_status = save_status
        self.submit_status = submit_status
        self.mutations = []
        self.change_requests = [{
            "id": "change-1", "actorUserId": "81", "documentVersion": 2,
            "comment": "Explain authentication.", "relatedComments": [],
        }]
        self.comments = [{
            "id": "comment-1", "actorUserId": "81", "documentVersion": 2,
            "comment": "Which token is needed?",
            "section": {"startOffset": 7, "endOffset": 30, "quote": "Authentication required."},
        }]

    def handle(self, route):
        request = route.request
        path = request.url.split("?", 1)[0].removeprefix(FRONTEND_URL)
        prefix = f"/api/document-workflows/{WORKFLOW_ID}"
        if request.method == "GET" and path == "/api/auth/me":
            return route.fulfill(status=200, json={"id": int(USER_ID), "role": "DEVELOPER"})
        if request.method == "GET" and path == "/api/document-workflows/history-accessible":
            return route.fulfill(status=200, json={
                "content": [self.item], "page": 0, "size": 20, "totalElements": 1,
                "totalPages": 1, "first": True, "last": True,
            })
        if request.method == "GET" and path == f"{prefix}/history":
            return route.fulfill(status=200, json=[{
                "id": "audit-1", "action": "CHANGES_REQUESTED", "comment": "Explain authentication.",
            }])
        if request.method == "GET" and path == f"{prefix}/document":
            return route.fulfill(status=200, json={
                "documentId": DOCUMENT_ID, "version": self.version, "content": self.content,
            })
        if request.method in ("PUT", "POST"):
            body = json.loads(request.post_data or "{}")
            self.mutations.append((request.method, path, body))
            if path == f"{prefix}/document":
                if self.save_status != 200:
                    return route.fulfill(status=self.save_status, json={"message": "Version changed"})
                self.content = body["content"]
                self.version += 1
                return route.fulfill(status=200, json=self.item)
            if path == f"{prefix}/submit":
                if self.submit_status != 200:
                    return route.fulfill(status=self.submit_status, json={"message": "Version changed"})
                self.item.update(status="PENDING_STAFF_REVIEW", submittedDocumentVersion=self.version,
                                 staffComment=None, staffReviewResult=None, reviewerUserId=None)
                return route.fulfill(status=200, json=self.item)
        return super().handle(route)


def open_revision(page: Page, api: RevisionApi):
    page.route("**/api/**", api.handle)
    page.goto(FRONTEND_URL)
    open_screen(page, "Generated Documents")
    expect(page.get_by_label("Revised document Markdown")).to_have_value(api.content)


def test_owner_reads_feedback_saves_new_version_and_resubmits_same_workflow(page: Page):
    api = RevisionApi()
    open_revision(page, api)
    feedback = page.get_by_role("region", name="Revision feedback")
    expect(feedback).to_contain_text("Explain authentication.")
    expect(feedback).to_contain_text("Which token is needed?")
    expect(feedback).to_contain_text("Authentication required.")
    expect(page.get_by_role("button", name="Resubmit for review", exact=True)).to_be_disabled()
    revised = "# API\n\nUse a GitHub access token."
    page.get_by_label("Revised document Markdown").fill(revised)
    page.get_by_label("Revision note").fill("Clarify the required token")
    page.get_by_role("button", name="Save revision", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Revision saved as version 3.")).to_be_visible()
    expect(page.get_by_role("button", name="Resubmit for review", exact=True)).to_be_enabled()
    page.get_by_role("button", name="Resubmit for review", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Version 3 submitted for Staff review.")).to_be_visible()
    assert api.mutations == [
        ("PUT", f"/api/document-workflows/{WORKFLOW_ID}/document",
         {"content": revised, "note": "Clarify the required token", "expectedVersion": 2}),
        ("POST", f"/api/document-workflows/{WORKFLOW_ID}/submit", {"expectedVersion": 3}),
    ]
    assert api.change_requests[0]["documentVersion"] == 2
    expect(page.get_by_role("region", name="Revise requested changes", exact=True)).to_have_count(0)


def test_save_conflict_preserves_local_edits_and_blocks_submission(page: Page):
    api = RevisionApi(save_status=409)
    open_revision(page, api)
    page.get_by_label("Revised document Markdown").fill("Local draft")
    page.get_by_role("button", name="Save revision", exact=True).click()
    expect(page.get_by_role("alert").filter(has_text="Reload the revision")).to_be_visible()
    expect(page.get_by_label("Revised document Markdown")).to_have_value("Local draft")
    expect(page.get_by_role("button", name="Resubmit for review", exact=True)).to_be_disabled()
    assert api.content != "Local draft"


def test_saved_revision_can_be_resumed_but_unsaved_edits_block_submission(page: Page):
    api = RevisionApi()
    api.version = 3
    open_revision(page, api)
    submit = page.get_by_role("button", name="Resubmit for review", exact=True)
    expect(submit).to_be_enabled()
    page.get_by_label("Revised document Markdown").fill("Unsaved edit")
    expect(submit).to_be_disabled()
    assert not api.mutations


def test_submission_conflict_keeps_workflow_in_revision(page: Page):
    api = RevisionApi(submit_status=409)
    api.version = 3
    open_revision(page, api)
    page.get_by_role("button", name="Resubmit for review", exact=True).click()
    expect(page.get_by_role("alert").filter(has_text="Reload the revision")).to_be_visible()
    assert api.item["status"] == "CHANGES_REQUESTED"
