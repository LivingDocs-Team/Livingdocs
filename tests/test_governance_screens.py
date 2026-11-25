"""Manager policies and delegation, and the Technical Lead oversight screens (formerly "Chưa triển khai").

The API is mocked with Playwright route interception, like the other browser tests.
"""
import json
from urllib.parse import urlsplit

from playwright.sync_api import Page, expect

from rbac_nav import FRONTEND, menu_link, open_screen
from test_rbac_screen_flow import Api, ends_with, start
from test_role_screens import REPOSITORY_ID, WORKFLOW_ID, event, page_of, workflow

OTHER_WORKFLOW_ID = "44444444-4444-4444-8444-444444444444"
DOCUMENT_ID = "55555555-5555-4555-8555-555555555555"


class GovernanceApi(Api):
    """Api that also answers writes: writes[(method, path)] = callable(body) -> (status, json)."""

    def __init__(self, role, routes=None, writes=None):
        super().__init__(role, routes)
        self.writes = writes or {}
        self.sent = []

    def handle(self, route):
        request = route.request
        path = urlsplit(request.url).path
        key = (request.method, path)
        if key in self.writes:
            body = json.loads(request.post_data) if request.post_data else None
            self.sent.append((request.method, path, body))
            status, payload = self.writes[key](body)
            return route.fulfill(status=status, json=payload) if payload is not None else route.fulfill(status=status)
        return super().handle(route)


def manager(routes=None, writes=None):
    return GovernanceApi("MANAGER", routes, writes)


def technical_lead(routes=None, writes=None):
    return GovernanceApi("TECHNICAL_LEAD", routes, writes)


# ---------- Approval Policy / Merge Policy ----------

def policy(kind, settings, updated_by=None):
    return {"type": kind, "settings": settings, "updatedBy": updated_by,
            "updatedAt": "2026-11-22T08:00:00Z" if updated_by else None}


def test_approval_policy_is_loaded_edited_and_saved(page: Page):
    saved = {}

    def put(body):
        saved.update(body)
        return 200, policy("APPROVAL", body, "42")

    api = manager({"/api/approval/policies/approval": policy(
        "APPROVAL", {"requireStaffComment": False, "requireManagerComment": False})},
        {("PUT", "/api/approval/policies/approval"): put})
    start(page, api)
    open_screen(page, "Approval Policy")
    expect(page).to_have_url(ends_with("#/policies/approval"))
    expect(page.get_by_role("heading", name="Approval Policy")).to_be_visible()
    expect(page.get_by_text("Using the defaults.")).to_be_visible()
    page.get_by_label("Managers must comment on every approval").check()
    page.get_by_role("button", name="Save policy").click()
    expect(page.get_by_role("status").filter(has_text="Policy saved.")).to_be_visible()
    assert saved == {"requireStaffComment": False, "requireManagerComment": True}
    expect(page.get_by_text("Last changed by 42")).to_be_visible()
    expect(page.get_by_text("Chưa triển khai")).to_have_count(0)


def test_merge_policy_previews_the_commit_message_and_blocks_an_empty_one(page: Page):
    api = manager({"/api/approval/policies/merge": policy(
        "MERGE", {"allowCommitBack": True, "commitMessageTemplate": "Publish LivingDocs document {document} v{version}"})})
    start(page, api)
    open_screen(page, "Merge Policy")
    expect(page.get_by_role("heading", name="Merge Policy")).to_be_visible()
    expect(page.get_by_text("Publish LivingDocs document doc-1234 v3")).to_be_visible()
    page.get_by_label("Commit message").fill("docs: {document} v{version}")
    expect(page.get_by_text("docs: doc-1234 v3")).to_be_visible()
    page.get_by_label("Commit message").fill("")
    expect(page.get_by_role("button", name="Save policy")).to_be_disabled()


def test_policy_save_errors_are_shown_and_not_reported_as_saved(page: Page):
    api = manager({"/api/approval/policies/merge": policy("MERGE", {"allowCommitBack": True, "commitMessageTemplate": "x"})},
                  {("PUT", "/api/approval/policies/merge"): lambda body: (400, {"message": "Unknown field {author}."})})
    start(page, api)
    open_screen(page, "Merge Policy")
    page.get_by_role("button", name="Save policy").click()
    expect(page.get_by_role("alert").filter(has_text="Unknown field {author}.")).to_be_visible()
    expect(page.get_by_text("Policy saved.")).to_have_count(0)


# ---------- Approval Delegation ----------

def delegation(delegation_id, delegator, delegate, state="ACTIVE"):
    return {"id": delegation_id, "delegatorUserId": delegator, "delegateUserId": delegate, "reason": "On leave",
            "startsAt": "2026-11-22T08:00:00Z", "endsAt": "2026-11-29T08:00:00Z", "revokedAt": None,
            "createdAt": "2026-11-22T08:00:00Z", "state": state}


def test_delegation_lists_creates_and_revokes(page: Page):
    data = {"outgoing": [delegation("d1", "42", "77")], "incoming": [delegation("d2", "55", "42")]}

    def create(body):
        data["outgoing"].insert(0, delegation("d3", "42", body["delegateUserId"]))
        return 201, data["outgoing"][0]

    def revoke(body):
        data["outgoing"][:] = [item for item in data["outgoing"] if item["id"] != "d1"]
        return 204, None

    api = manager({"/api/approval/delegations": data},
                  {("POST", "/api/approval/delegations"): create, ("DELETE", "/api/approval/delegations/d1"): revoke})
    start(page, api)
    open_screen(page, "Approval Delegation")
    expect(page).to_have_url(ends_with("#/approval/delegation"))
    expect(page.get_by_role("region", name="Delegated by you")).to_contain_text("To Manager 77")
    expect(page.get_by_role("region", name="Delegated to you")).to_contain_text("From Manager 55")

    page.get_by_label("Manager user ID").fill("88")
    page.get_by_label("Reason (optional)").fill("Conference")
    page.get_by_role("button", name="Delegate approvals").click()
    expect(page.get_by_role("status").filter(has_text="Delegation saved.")).to_be_visible()
    posted = api.sent[0][2]
    assert posted["delegateUserId"] == "88" and posted["reason"] == "Conference" and posted["endsAt"].endswith("Z")
    expect(page.get_by_role("region", name="Delegated by you")).to_contain_text("To Manager 88")

    page.get_by_role("button", name="Revoke delegation to 77").click()
    expect(page.get_by_role("status").filter(has_text="Delegation revoked.")).to_be_visible()
    expect(page.get_by_role("region", name="Delegated by you")).not_to_contain_text("To Manager 77")


def test_delegation_error_is_shown(page: Page):
    api = manager({"/api/approval/delegations": {"outgoing": [], "incoming": []}},
                  {("POST", "/api/approval/delegations"): lambda body: (400, {"message": "Choose a different Manager than yourself."})})
    start(page, api)
    open_screen(page, "Approval Delegation")
    page.get_by_label("Manager user ID").fill("42")
    page.get_by_role("button", name="Delegate approvals").click()
    expect(page.get_by_role("alert").filter(has_text="Choose a different Manager than yourself.")).to_be_visible()


# ---------- Technical Lead: workflows ----------

def workflows_routes():
    return {
        "/api/document-workflows/history-accessible": page_of([
            workflow(WORKFLOW_ID, "Shop guide", "PENDING_STAFF_REVIEW"),
            workflow(OTHER_WORKFLOW_ID, "Billing guide", "APPROVED", managerDecision="APPROVED", managerUserId="9",
                     managerComment="Ship it.")]),
        f"/api/document-workflows/{WORKFLOW_ID}/history": [event("e1", "SUBMITTED", "DRAFT", "PENDING_STAFF_REVIEW")],
        f"/api/document-workflows/{OTHER_WORKFLOW_ID}/history": [event("e2", "APPROVED", "PENDING_MANAGER_APPROVAL", "APPROVED", "Ship it.", "MANAGER")],
    }


def test_workflow_status_shows_every_workflow_with_details_and_history(page: Page):
    start(page, technical_lead(workflows_routes()))
    open_screen(page, "Workflow Status")
    expect(page).to_have_url(ends_with("#/code/workflow-status"))
    expect(page.get_by_role("heading", name="Workflow Status")).to_be_visible()
    expect(page.get_by_role("list", name="Workflows by status")).to_contain_text("1 pending staff review")
    expect(page.get_by_role("list", name="Workflows by status")).to_contain_text("1 approved")
    expect(page.get_by_role("region", name="Workflow details")).to_contain_text("Shop guide")
    expect(page.locator(".changelog-entry")).to_have_count(1)
    page.get_by_label("Document", exact=True).select_option(OTHER_WORKFLOW_ID)
    expect(page.get_by_role("region", name="Workflow details")).to_contain_text("Ship it.")
    expect(page.get_by_role("button", name="Approve document")).to_have_count(0)    # view only


def test_staff_review_and_manager_approval_overviews_filter_by_status(page: Page):
    start(page, technical_lead(workflows_routes()))
    open_screen(page, "Staff Review")
    expect(page.get_by_role("heading", name="Staff Review")).to_be_visible()
    expect(page.get_by_label("Document", exact=True).locator("option")).to_have_text(["Shop guide · pending staff review"])
    expect(page.get_by_role("button", name="Claim review")).to_have_count(0)
    open_screen(page, "Manager Approval")
    expect(page.get_by_role("heading", name="Manager Approval")).to_be_visible()
    expect(page.get_by_label("Document", exact=True).locator("option")).to_have_text(["Billing guide · approved"])


def test_oversight_without_workflows_is_an_empty_state_and_errors_can_be_retried(page: Page):
    api = technical_lead({})
    start(page, api)
    open_screen(page, "Workflow Status")
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    api.routes["/api/document-workflows/history-accessible"] = page_of([])
    page.get_by_role("button", name="Retry").click()
    expect(page.get_by_role("heading", name="Nothing here yet")).to_be_visible()


def test_technical_lead_approval_audit_trail(page: Page):
    start(page, technical_lead(workflows_routes()))
    open_screen(page, "Approval Audit Trail & History")
    expect(page).to_have_url(ends_with("#/oversight/audit"))
    expect(page.get_by_role("heading", name="Approval Audit Trail & History")).to_be_visible()
    expect(page.locator(".changelog-entry")).to_have_count(1)


# ---------- Technical Lead: versions ----------

VERSIONS = [
    {"number": 1, "status": "APPROVED", "origin": "GENERATED", "created_by": "7", "created_at": "2026-11-18T08:00:00Z"},
    {"number": 2, "status": "PENDING", "origin": "ROLLBACK", "restored_from": 1, "note": "Back to v1",
     "created_by": "9", "created_at": "2026-11-21T08:00:00Z"},
]


def version_routes():
    routes = workflows_routes()
    routes[f"/api/document-workflows/{WORKFLOW_ID}/versions"] = VERSIONS
    routes[f"/api/document-workflows/{WORKFLOW_ID}/comparison"] = {
        "from": {"number": 1}, "to": {"number": 2}, "summary": {}, "sections": [], "rows": []}
    routes[f"/api/document-workflows/{WORKFLOW_ID}/history"] = [
        event("e1", "SUBMITTED", "DRAFT", "PENDING_STAFF_REVIEW"),
        event("e2", "ROLLBACK_REQUESTED", "APPROVED", "PENDING_STAFF_REVIEW", "Restore version 1", "MANAGER")]
    return routes


def test_version_history_and_comparison_offer_both_versions(page: Page):
    start(page, technical_lead(version_routes()))
    open_screen(page, "Version History & Comparison")
    expect(page).to_have_url(ends_with("#/versions/history"))
    expect(page.get_by_role("heading", name="Version History & Comparison")).to_be_visible()
    expect(page.get_by_role("heading", name="Compare document versions")).to_be_visible()
    expect(page.get_by_label("Older version")).to_contain_text("Version 1")
    expect(page.get_by_label("Newer version")).to_contain_text("Version 2")


def test_document_rollback_screen_shows_versions_and_rollback_requests_but_no_action(page: Page):
    start(page, technical_lead(version_routes()))
    open_screen(page, "Document Rollback")
    expect(page.get_by_role("heading", name="Document Rollback")).to_be_visible()
    versions = page.get_by_role("list", name="Versions")
    expect(versions.get_by_role("listitem")).to_have_count(2)
    expect(versions.first).to_contain_text("Version 2")
    expect(versions).to_contain_text("restored from 1")
    trail = page.get_by_role("list", name="Audit trail")
    expect(trail.get_by_role("listitem")).to_have_count(1)
    expect(trail).to_contain_text("Restore version 1")
    expect(page.get_by_role("button", name="Request rollback")).to_have_count(0)


# ---------- Technical Lead: repositories ----------

OVERSIGHT_REPOSITORY = {"id": REPOSITORY_ID, "workspaceId": "ws-9", "fullName": "acme/shop", "defaultBranch": "main",
                        "status": "CONNECTED", "lastSyncedAt": "2026-11-20T08:00:00Z"}


def repository_routes():
    base = f"/api/oversight/repositories/{REPOSITORY_ID}"
    return {
        "/api/oversight/repositories": [OVERSIGHT_REPOSITORY],
        f"{base}/pull-requests": [{"number": 8, "title": "Add invoice export", "state": "open", "merged": False,
                                   "authorLogin": "lamhuyy", "headRef": "feature/export", "baseRef": "main",
                                   "htmlUrl": "https://github.com/acme/shop/pull/8", "updatedAt": "2026-11-06T03:00:00Z"}],
        f"{base}/commits": [{"sha": "abcdef1" + "0" * 33, "branch": "main", "message": "Fix invoice totals\n\nRounds.",
                             "authorName": "Hai Dang", "authorLogin": "d3r-bbb", "committedAt": "2026-11-06T03:01:00Z",
                             "htmlUrl": "https://github.com/acme/shop/commit/abcdef1"}],
        f"{base}/drift-policies": [{"scope": "REPOSITORY", "target": "", "onCommit": True, "onPullRequest": True}],
    }


def test_pull_requests_and_commits_of_any_repository(page: Page):
    start(page, technical_lead(repository_routes()))
    open_screen(page, "Pull Requests & Commits")
    expect(page).to_have_url(ends_with("#/code/activity"))
    expect(page.get_by_role("heading", name="Pull Requests & Commits")).to_be_visible()
    expect(page.get_by_role("list", name="Pull requests")).to_contain_text("#8 Add invoice export")
    expect(page.get_by_role("list", name="Commits")).to_contain_text("abcdef1 Fix invoice totals")
    expect(page.get_by_text("Chưa triển khai")).to_have_count(0)


def test_drift_policies_are_edited_through_the_oversight_route(page: Page):
    saved = []

    def put(body):
        saved.append(body)
        return 200, body

    api = technical_lead(repository_routes(),
                         {("PUT", f"/api/oversight/repositories/{REPOSITORY_ID}/drift-policies"): put})
    start(page, api)
    open_screen(page, "Drift Policies & Thresholds")
    expect(page.get_by_role("heading", name="Drift Policies & Thresholds")).to_be_visible()
    expect(page.get_by_role("region", name="Auto-update policies")).to_be_visible()
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("status").filter(has_text="Auto-update policies saved.")).to_be_visible()
    assert saved and saved[0][0]["scope"] == "REPOSITORY"


def test_oversight_repositories_empty_state(page: Page):
    start(page, technical_lead({"/api/oversight/repositories": []}))
    open_screen(page, "Pull Requests & Commits")
    expect(page.get_by_role("heading", name="No repositories yet")).to_be_visible()


# ---------- Technical Lead: documentation ----------

DOCUMENTS = [
    {"id": DOCUMENT_ID, "repositoryId": REPOSITORY_ID, "repositoryName": "acme/shop", "title": "Shop guide",
     "sourceCommit": "abcdef1234", "createdAt": "2026-11-20T08:00:00Z"},
    {"id": "66666666-6666-4666-8666-666666666666", "repositoryId": REPOSITORY_ID, "repositoryName": "acme/billing",
     "title": "Billing guide", "sourceCommit": None, "createdAt": "2026-11-19T08:00:00Z"},
]


def test_documentation_overview_reads_any_document_and_filters(page: Page):
    routes = {"/api/oversight/documentation": DOCUMENTS,
              f"/api/oversight/documentation/{DOCUMENT_ID}": {"id": DOCUMENT_ID, "markdown": "# Shop guide\n\nReviewed.\n"}}
    start(page, technical_lead(routes))
    open_screen(page, "Documentation")
    expect(page).to_have_url(ends_with("#/code/documentation"))
    expect(page.get_by_label("Document (2)")).to_be_visible()
    expect(page.get_by_label("Document content")).to_contain_text("Reviewed.")
    page.get_by_label("Filter by title or repository").fill("billing")
    expect(page.get_by_label("Document (1)").locator("option")).to_have_text(["Billing guide · acme/billing"])
    page.get_by_label("Filter by title or repository").fill("zzz")
    expect(page.get_by_text("No document matches the filter.")).to_be_visible()


# ---------- Technical Lead: health report ----------

HEALTH = {
    "generatedAt": "2026-11-22T08:00:00Z",
    "counts": {"repositories": 2, "documents": 3, "codeEntities": 10, "documentedEntities": 4, "coveragePercent": 40},
    "repositoriesByStatus": {"CONNECTED": 2, "DISCONNECTED": 0},
    "workflowsByStatus": {"PENDING_STAFF_REVIEW": 1, "APPROVED": 2},
    "nodes": [{"id": "doc:a", "kind": "document", "label": "Shop guide"},
              {"id": "doc:b", "kind": "document", "label": "=SUM(1)"},
              {"id": "file:src/Cart.java", "kind": "file", "label": "src/Cart.java"}],
    "edges": [{"from": "doc:a", "to": "file:src/Cart.java", "entities": 3}, {"from": "doc:b", "to": "file:src/Cart.java", "entities": 1}],
    "graphTruncated": False,
}


def test_health_report_shows_metrics_and_the_dependency_graph(page: Page):
    start(page, technical_lead({"/api/oversight/health": HEALTH}))
    open_screen(page, "Health Metrics, Dependency Graph & Reports")
    expect(page).to_have_url(ends_with("#/reports/health"))
    expect(page.get_by_text("40% of code entities documented")).to_be_visible()
    expect(page.get_by_text("4 of 10 code entities have linked documentation.")).to_be_visible()
    expect(page.get_by_role("list", name="Totals")).to_contain_text("2 repositories")
    expect(page.get_by_role("list", name="Workflows by status")).to_contain_text("2 approved")
    graph = page.locator("div[aria-label='Dependency graph']")
    expect(graph).to_contain_text("Shop guide")
    graph.get_by_text("Shop guide").click()
    expect(graph).to_contain_text("src/Cart.java")
    expect(graph).to_contain_text("3 code entities")


def test_health_report_exports_json_and_a_safe_csv(page: Page):
    start(page, technical_lead({"/api/oversight/health": HEALTH}))
    open_screen(page, "Health Metrics, Dependency Graph & Reports")
    with page.expect_download() as download:
        page.get_by_role("button", name="Export JSON").click()
    assert download.value.suggested_filename == "livingdocs-health.json"
    exported = json.loads(open(download.value.path(), encoding="utf-8").read())
    assert exported["counts"]["coveragePercent"] == 40
    with page.expect_download() as download:
        page.get_by_role("button", name="Export CSV").click()
    csv = open(download.value.path(), encoding="utf-8").read()
    assert "counts,coveragePercent,40" in csv
    assert "dependency,'=SUM(1) -> src/Cart.java,1" in csv      # a spreadsheet must not run a cell as a formula
    assert ",=SUM" not in csv


def test_health_report_error_can_be_retried(page: Page):
    api = technical_lead({})
    start(page, api)
    open_screen(page, "Health Metrics, Dependency Graph & Reports")
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    api.routes["/api/oversight/health"] = HEALTH
    page.get_by_role("button", name="Retry").click()
    expect(page.get_by_text("40% of code entities documented")).to_be_visible()


# ---------- the Manager and Technical Lead flows have no unbuilt screen left ----------

def test_manager_and_technical_lead_menus_have_no_placeholder_screens(page: Page):
    for role in ("MANAGER", "TECHNICAL_LEAD"):
        start(page, GovernanceApi(role))
        expect(page.locator("nav[aria-label='Main menu'] a").first).to_be_visible()
        expect(page.locator("nav[aria-label='Main menu'] a[data-status='placeholder']")).to_have_count(0)
        expect(menu_link(page, "Profile & Settings")).to_be_visible()


# ---------- Rollback by Developer and Technical Lead, Change Log filters ----------

RB_WORKFLOW = "55555555-5555-4555-8555-555555555555"
RB_VERSIONS = [
    {"number": 0, "status": "superseded", "origin": "EDIT", "created_at": "2026-11-09T08:00:00Z", "created_by": "42"},
    {"number": 1, "status": "accepted", "origin": "GENERATED", "created_at": "2026-11-10T08:00:00Z", "created_by": "42"},
    {"number": 2, "status": "accepted", "origin": "DRIFT_UPDATE", "created_at": "2026-11-20T08:00:00Z", "created_by": "ai"},
]


def approved_workflow():
    return {"id": RB_WORKFLOW, "documentId": "doc-rb", "documentTitle": "Shop guide", "ownerUserId": "42",
            "status": "APPROVED", "submittedDocumentVersion": 2, "reviewerUserId": None, "staffReviewResult": "PASSED",
            "staffComment": None, "managerUserId": "9", "managerDecision": "APPROVED", "managerComment": None,
            "createdAt": "2026-11-20T08:00:00Z", "updatedAt": "2026-11-20T08:00:00Z", "submittedAt": None,
            "reviewedAt": None, "decidedAt": None, "optimisticVersion": 3}


def rollback_routes():
    return {
        "/api/document-workflows/history-accessible": {"content": [approved_workflow()], "page": 0, "size": 20,
                                                       "totalElements": 1, "totalPages": 1, "first": True, "last": True},
        f"/api/document-workflows/{RB_WORKFLOW}/versions": RB_VERSIONS,
        f"/api/document-workflows/{RB_WORKFLOW}/history": [],
    }


def rollback_write(sent):
    def post(body):
        sent.append(body)
        return 200, {**approved_workflow(), "status": "PENDING_STAFF_REVIEW", "submittedDocumentVersion": 3}
    return {("POST", f"/api/document-workflows/{RB_WORKFLOW}/rollback"): post}


def test_developer_can_roll_back_from_the_change_log_and_it_goes_to_staff_review(page: Page):
    sent = []
    api = GovernanceApi("DEVELOPER", {"/api/workspaces/ws-42/repositories": [], **rollback_routes()}, rollback_write(sent))
    start(page, api)
    open_screen(page, "Change Log")
    expect(page.get_by_role("button", name="Roll back to version 2")).to_have_count(0)  # already approved
    # a version that was superseded before anyone accepted it cannot be restored: no button is offered for it
    expect(page.get_by_role("button", name="Roll back to version 0")).to_have_count(0)
    page.get_by_role("button", name="Roll back to version 1").click()
    page.get_by_label("Why roll back to version 1?").fill("Version 2 documented the wrong endpoint")
    page.get_by_role("button", name="Request rollback").click()
    expect(page.get_by_text("Version 1 was restored as a new proposal and sent to Staff review.")).to_be_visible()
    assert sent == [{"sourceVersion": 1, "reason": "Version 2 documented the wrong endpoint"}]


def test_rollback_needs_a_reason_and_shows_a_backend_refusal(page: Page):
    def refuse(body):
        return 403, {"message": "The authenticated primary role cannot roll back this document."}

    api = GovernanceApi("DEVELOPER", {"/api/workspaces/ws-42/repositories": [], **rollback_routes()},
                        {("POST", f"/api/document-workflows/{RB_WORKFLOW}/rollback"): refuse})
    start(page, api)
    open_screen(page, "Change Log")
    page.get_by_role("button", name="Roll back to version 1").click()
    page.get_by_role("button", name="Request rollback").click()
    expect(page.get_by_role("alert")).to_have_text("A rollback reason is required.")
    page.get_by_label("Why roll back to version 1?").fill("Because")
    page.get_by_role("button", name="Request rollback").click()
    expect(page.get_by_role("alert")).to_contain_text("cannot roll back this document")


def test_technical_lead_can_roll_back_from_the_document_rollback_screen(page: Page):
    sent = []
    api = technical_lead(rollback_routes(), rollback_write(sent))
    start(page, api)
    open_screen(page, "Document Rollback")
    page.get_by_role("button", name="Roll back to version 1").click()
    page.get_by_label("Why roll back to version 1?").fill("Restore the reviewed text")
    page.get_by_role("button", name="Request rollback").click()
    expect(page.get_by_text("sent to Staff review")).to_be_visible()
    assert sent == [{"sourceVersion": 1, "reason": "Restore the reviewed text"}]


def test_staff_never_sees_a_rollback_button(page: Page):
    api = GovernanceApi("STAFF", rollback_routes())
    start(page, api)
    page.goto(f"{FRONTEND}/#/review/queue/review-history")
    expect(page.get_by_role("button", name="Roll back to version 1")).to_have_count(0)


def test_change_log_can_be_filtered_by_source_and_date(page: Page):
    api = GovernanceApi("DEVELOPER", {"/api/workspaces/ws-42/repositories": [], **rollback_routes()})
    start(page, api)
    open_screen(page, "Change Log")
    entries = page.locator(".changelog-entry h3")
    expect(entries).to_have_count(3)
    page.get_by_label("Source").select_option("GENERATED")
    expect(entries).to_have_count(1)
    expect(entries.first).to_contain_text("Version 1")
    page.get_by_label("Source").select_option("")
    page.get_by_label("From").fill("2026-11-15")
    expect(entries).to_have_count(1)
    expect(entries.first).to_contain_text("Version 2")
    page.get_by_label("To").fill("2026-11-16")
    expect(page.get_by_text("No version matches these filters.")).to_be_visible()


def test_delegation_refusal_explains_what_is_checked(page: Page):
    def refuse(body):
        return 400, {"timestamp": "2026-11-24T00:00:00Z", "status": 400, "error": "Bad Request", "path": "/api/approval/delegations"}

    api = manager({"/api/approval/delegations": {"outgoing": [], "incoming": []}},
                  {("POST", "/api/approval/delegations"): refuse})
    start(page, api)
    open_screen(page, "Approval Delegation")
    page.get_by_label("Manager user ID").fill("4")
    page.get_by_role("button", name="Delegate approvals").click()
    expect(page.get_by_role("alert")).to_contain_text("the delegate must be an active Manager")
