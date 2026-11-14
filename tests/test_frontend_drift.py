"""LD-160 Test drift severity assessment in the frontend (LD-159 Display Drift Severity).

Runs against the built frontend on http://localhost:3000 with every /api call mocked, like
test_frontend_templates.py. The drift report below has the shape the AI service returns through
GitHub Integration (findings with severity, severity_assessment and evidence).
"""
import json

from playwright.sync_api import Page, expect

REPOSITORY_ID = "11111111-1111-1111-1111-111111111111"
WORKSPACE_ID = "ws-42"
BASE = f"/api/repositories/{REPOSITORY_ID}/drift"


def finding(fid, severity, score, type_, kind, entity, base, adjustments, breaking=True, evidence=None):
    return {
        "id": fid, "type": type_, "kind": kind, "breaking": breaking, "severity": severity,
        "confidence": 0.85, "confidence_level": "high", "entity": entity, "change": "x",
        "file": "shop/cart.py", "message": f"Message of {entity}.", "suggestion": f"Fix {entity}.",
        "document": {"source": "repository", "path": "README.md", "matches": []},
        "severity_assessment": {
            "level": severity, "score": score, "base_rule": base[0], "base_level": base[1],
            "base_label": base[2], "base_reason": base[3], "base_evidence": ["X1", "D1"],
            "adjustments": adjustments, "capped_at": None, "summary": ""},
        "evidence": evidence or [
            {"id": "X1", "kind": "code_diff", "path": "shop/cart.py", "line_start": 9,
             "excerpt": "-@app.get(\"/carts/{id}\")\n+@app.get(\"/api/carts/{id}\")"},
            {"id": "D1", "kind": "documentation", "path": "README.md", "line_start": 3,
             "excerpt": "Read a total with `GET /carts/:id`."},
            {"id": "C1", "kind": "commit", "commit_sha": "9f2c1e7aa", "excerpt": "PR #42: Cart currency",
             "url": "https://github.com/acme/shop/pull/42"},
            {"id": "T1", "kind": "ticket", "ticket": "LD-146"}],
    }


REPORT = {
    "id": "report-1", "status": "drift_detected", "repository": "acme/shop",
    "pull_request": {"number": 42, "title": "LD-146 Cart currency"},
    "tickets": ["LD-146"],
    "summary": {"findings": 3, "breaking": 2, "affected_documents": 2, "highest_severity": "critical",
                "severity_score": 94, "recommendation": "Fix the documentation before merging the Pull Request.",
                "by_severity": {"low": 1, "medium": 0, "high": 1, "critical": 1},
                "by_type": {"referential": 1, "signature": 1, "semantic": 1}},
    "affected_documents": [
        {"source": "repository", "path": "README.md", "severity": "critical", "findings": 2, "matches": []},
        {"source": "document", "path": "shop/cart.py", "document_id": "doc-1", "version": 1,
         "severity": "low", "findings": 1, "matches": []}],
    "findings": [
        finding("F1", "critical", 94, "referential", "endpoint_moved", "GET /api/carts/{id}",
                ("endpoint_gone", "critical", "documented endpoint removed or moved",
                 "An HTTP endpoint the documentation describes no longer exists."), []),
        finding("F2", "high", 70, "signature", "parameter_removed", "get_cart_total",
                ("breaking_signature", "medium", "breaking change", "Documented usage stops working."),
                [{"rule": "doc_states_old_detail", "delta": 1,
                  "label": "documentation still states the old detail",
                  "reason": "The documentation still shows the removed parameter.", "evidence": ["D2"]}],
                evidence=[{"id": "X1", "kind": "code_diff", "path": "shop/cart.py", "line_start": 10,
                           "excerpt": "-def get_cart_total(cart_id, discount)\n+def get_cart_total(cart_id, currency)"},
                          {"id": "D2", "kind": "documentation", "path": "README.md", "line_start": 7,
                           "excerpt": "| `discount` | float |"}]),
        finding("F3", "low", 12, "semantic", "implementation_changed", "Cart.add",
                ("behaviour_changed", "low", "behaviour change", "Same signature, different behaviour."),
                [], breaking=False),
    ],
    "warnings": ["web/app.js: language not analysed; only file-level changes are checked."],
}
LEVELS = {"levels": [
    {"level": "critical", "min_score": 75, "max_score": 100, "label": "Critical",
     "meaning": "The documented API no longer exists or works.", "action": "Fix before merging."},
    {"level": "high", "min_score": 50, "max_score": 74, "label": "High", "meaning": "Breaking change.",
     "action": "Update in this PR."},
    {"level": "medium", "min_score": 25, "max_score": 49, "label": "Medium", "meaning": "Partly wrong.",
     "action": "Update before release."},
    {"level": "low", "min_score": 0, "max_score": 24, "label": "Low", "meaning": "Incomplete.",
     "action": "Review when convenient."}], "rules": []}
MARKDOWN = "## Documentation drift — PR #42\n\n**Overall severity:** Critical\n"


def install_api(page: Page, state: dict):
    state.setdefault("analyze_bodies", [])
    state.setdefault("markdown_queries", [])
    state.setdefault("reports", [])

    def handle(route):
        request = route.request
        url = request.url.replace("http://localhost:3000", "")
        path, _, query = url.partition("?")
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
        if path == f"/api/workspaces/{WORKSPACE_ID}/repositories":
            return route.fulfill(status=200, json=[{
                "id": REPOSITORY_ID, "githubRepoId": 4242, "workspaceId": WORKSPACE_ID, "fullName": "acme/shop",
                "defaultBranch": "main", "privateRepo": False, "status": "CONNECTED"}])
        if path == "/api/documentation/drift/severity-rules":
            return route.fulfill(status=200, json=LEVELS)
        if path == f"{BASE}/analyze" and method == "POST":
            state["analyze_bodies"].append(body)
            if body["pullRequestNumber"] == 404:
                return route.fulfill(status=404, json={"code": "PULL_REQUEST_NOT_FOUND",
                                                       "message": "Pull request #404 was not found."})
            if body["pullRequestNumber"] == 7:
                clean = {**REPORT, "id": "report-clean", "status": "no_drift", "findings": [],
                         "affected_documents": [], "warnings": [],
                         "summary": {"findings": 0, "breaking": 0, "affected_documents": 0,
                                     "highest_severity": None, "by_severity": {}}}
                return route.fulfill(status=201, json=clean)
            state["reports"].append(REPORT)
            return route.fulfill(status=201, json=REPORT)
        if path == f"{BASE}/reports":
            return route.fulfill(status=200, json=[{
                "id": r["id"], "status": r["status"], "repository": "acme/shop",
                "pull_request_number": r["pull_request"]["number"], "pull_request_title": r["pull_request"]["title"],
                "summary": r["summary"]} for r in state["reports"]])
        if path == f"{BASE}/reports/report-1":
            return route.fulfill(status=200, json=REPORT)
        if path == f"{BASE}/reports/report-1/markdown":
            state["markdown_queries"].append(query)
            return route.fulfill(status=200, content_type="text/markdown", body=MARKDOWN)
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {method} {path}"})

    page.route("**/api/**", handle)


def open_drift(page: Page):
    page.goto("http://localhost:3000/")
    page.get_by_label("Email").fill("user@example.test")
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("status").filter(has_text="Signed in successfully")).to_be_visible()
    page.get_by_role("button", name="Documentation Drift").first.click()
    expect(page.get_by_role("heading", name="Documentation Drift")).to_be_visible()
    expect(page.get_by_label("Repository", exact=True)).to_have_value(REPOSITORY_ID)


def run_check(page: Page, number="42"):
    page.get_by_label("Pull request number").fill(number)
    page.get_by_role("button", name="Check drift").click()


def test_severity_level_is_shown_for_the_report_and_every_finding(page: Page):
    state = {}
    install_api(page, state)
    open_drift(page)
    run_check(page)

    overall = page.locator(".drift-overall")
    expect(overall.locator(".severity-badge")).to_have_attribute("data-severity", "critical")
    assert state["analyze_bodies"] == [{"pullRequestNumber": 42, "includeRepositoryDocs": True}]
    expect(overall).to_contain_text("Critical · 94")
    expect(overall).to_contain_text("Fix the documentation before merging the Pull Request.")
    expect(overall).to_contain_text("3 finding(s) · 2 breaking · 2 document(s)")

    cards = page.locator(".drift-finding")
    expect(cards).to_have_count(3)
    assert [cards.nth(i).locator(".drift-finding-heading .severity-badge").get_attribute("data-severity")
            for i in range(3)] == ["critical", "high", "low"]
    expect(cards.nth(0)).to_contain_text("Referential · endpoint_moved")
    expect(cards.nth(0).locator(".drift-breaking")).to_have_text("Breaking")
    expect(cards.nth(2).locator(".drift-breaking")).to_have_count(0)

    documents = page.get_by_label("Affected documentation")
    expect(documents).to_contain_text("README.md")
    expect(documents.locator(".severity-badge").first).to_have_attribute("data-severity", "critical")
    expect(page.get_by_label("Warnings")).to_contain_text("language not analysed")

    page.get_by_text("Severity levels").click()
    expect(page.locator(".drift-legend")).to_contain_text("75-100")
    expect(page.locator(".drift-legend")).to_contain_text("Fix before merging.")


def test_finding_shows_why_it_has_its_severity_with_evidence(page: Page):
    install_api(page, {})
    open_drift(page)
    run_check(page)

    card = page.locator('[data-finding="F2"]')
    card.get_by_role("button", name="Why this severity? Show evidence").click()
    why = card.get_by_label("Why this severity")
    expect(why).to_contain_text("Why High")
    expect(why).to_contain_text("breaking change: starts at Medium [X1, D1]")
    expect(why).to_contain_text("documentation still states the old detail: +1 level [D2]")
    expect(card.locator("#evidence-D2")).to_contain_text("README.md:7")
    expect(card.locator("#evidence-D2")).to_contain_text("| `discount` | float |")
    expect(card.locator("#evidence-X1 pre")).to_contain_text("+def get_cart_total(cart_id, currency)")
    card.get_by_role("button", name="Hide severity reasons and evidence").click()
    expect(card.get_by_label("Why this severity")).to_have_count(0)


def test_filter_by_severity_and_copy_markdown(page: Page):
    state = {}
    install_api(page, state)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    open_drift(page)
    run_check(page)

    filters = page.get_by_role("group", name="Filter by severity")
    expect(filters.locator('[data-level="medium"]')).to_be_disabled()      # no medium finding
    filters.locator('[data-level="high"]').click()
    expect(page.locator(".drift-finding")).to_have_count(2)
    expect(page.get_by_text("Showing High and above: 2 of 3.")).to_be_visible()
    filters.get_by_role("button", name="All (3)").click()
    expect(page.locator(".drift-finding")).to_have_count(3)

    filters.locator('[data-level="critical"]').click()
    filters.get_by_role("button", name="Copy as PR comment").click()
    expect(page.get_by_role("status").filter(has_text="Markdown copied")).to_be_visible()
    assert state["markdown_queries"] == ["minSeverity=critical"]
    assert page.evaluate("navigator.clipboard.readText()") == MARKDOWN


def test_previous_checks_can_be_reopened(page: Page):
    state = {}
    install_api(page, state)
    open_drift(page)
    run_check(page)
    history = page.locator(".drift-history")
    expect(history).to_contain_text("PR #42 · LD-146 Cart currency")
    expect(history.locator(".severity-badge")).to_have_attribute("data-severity", "critical")

    run_check(page, "7")
    expect(page.get_by_text("No documentation drift: the checked documentation matches the code.")).to_be_visible()
    history.get_by_role("button", name="PR #42 · LD-146 Cart currency").click()
    expect(page.locator(".drift-finding")).to_have_count(3)


def test_invalid_number_and_unknown_pull_request(page: Page):
    state = {}
    install_api(page, state)
    open_drift(page)
    page.get_by_role("button", name="Check drift").click()
    expect(page.get_by_role("alert")).to_have_text("Enter a pull request number (1 or more).")
    assert state["analyze_bodies"] == []

    page.get_by_role("checkbox", name="Also check README and Markdown files of the repository").uncheck()
    run_check(page, "404")
    expect(page.get_by_role("alert")).to_have_text(
        "The pull request was not found in this repository. Check the number and try again.")
    assert state["analyze_bodies"] == [{"pullRequestNumber": 404, "includeRepositoryDocs": False}]



