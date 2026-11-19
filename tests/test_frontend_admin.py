"""LD-316 Administration & dashboard interface (LD-317 .. LD-321).

Runs against the built frontend on http://localhost:3000 with every /api call mocked, like
test_frontend_drift.py.
"""
import json
from urllib.parse import parse_qs

from playwright.sync_api import Page, expect

ADMIN = {"message": "Login successful", "id": 1, "email": "admin@example.test", "username": "admin",
         "firstName": "Ada", "lastName": "Admin", "role": "ADMINISTRATOR"}
DEVELOPER = {**ADMIN, "id": 2, "email": "dev@example.test", "username": "dev", "firstName": "Dev",
             "lastName": "User", "role": "DEVELOPER"}
WORKSPACE_ID = "workspace-6f1c2f0e-1111-4222-8333-444455556666"
REPOSITORY_ID = "11111111-1111-1111-1111-111111111111"
WORKFLOW_ID = "22222222-2222-2222-2222-222222222222""""LD-316 Administration & dashboard interface (LD-317 .. LD-321).

Runs against the built frontend on http://localhost:3000 with every /api call mocked.
"""
import json
from urllib.parse import parse_qs

from playwright.sync_api import Page, expect

ADMIN = {"message": "Login successful", "id": 1, "email": "admin@example.test", "username": "admin",
         "firstName": "Ada", "lastName": "Admin", "role": "ADMINISTRATOR"}
DEVELOPER = {**ADMIN, "id": 2, "email": "dev@example.test", "username": "dev", "firstName": "Dev",
             "lastName": "User", "role": "DEVELOPER"}
WORKSPACE_ID = "workspace-6f1c2f0e-1111-4222-8333-444455556666"
REPOSITORY_ID = "11111111-1111-1111-1111-111111111111"
PERMISSIONS = [{"code": "DOCUMENT_VIEW", "description": "View documents"},
               {"code": "DOCUMENT_APPROVE", "description": "Approve documents"},
               {"code": "USER_VIEW", "description": "View users"}]


def user_row(account, active=True):
    return {key: account[key] for key in ("id", "email", "username", "firstName", "lastName", "role")} | {
        "active": active, "createdAt": "2026-10-01T09:00:00"}


def install_api(page: Page, account=ADMIN, **options):
    state = {
        "calls": [],
        "users": [user_row(ADMIN), user_row(DEVELOPER)],
        "signed_in": False,
        "health_status": 200,
        "health_payload": {
            "status": "UP",
            "checkedAt": "2026-11-19T02:00:00Z",
            "services": [
                {"id": "backend", "name": "Backend API", "status": "UP", "httpStatus": 200, "latencyMs": 2, "detail": "Reachable"},
                {"id": "database", "name": "Backend Database", "status": "UP", "httpStatus": 200, "latencyMs": 4, "detail": "PostgreSQL reachable"},
                {"id": "github-integration", "name": "GitHub Integration Service", "status": "UP", "httpStatus": 200, "latencyMs": 11, "detail": "UP"},
            ],
        },
        "audit_status": 200,
        "audit_entries": [{
            "id": 101, "actorId": 1, "targetId": 2, "action": "USER_ROLE_CHANGED",
            "previousValue": "DEVELOPER", "newValue": "STAFF",
            "occurredAt": "2026-11-13T10:00:00Z", "targetRole": None, "targetEvent": None,
        }],
        "policies": [{
            "event": "AI_JOB_FAILED",
            "recipients": ["ops@example.test"],
            "enabled": True,
            "updatedAt": "2026-11-13T10:00:00Z",
        }],
        "retention_days": 30,
        "members": [{"userId": 2, "username": "dev", "displayName": "Dev User"}],
        **options,
    }
    roles = {"DEVELOPER": ["DOCUMENT_VIEW"], "ADMINISTRATOR": ["USER_VIEW"]}

    def handle(route):
        request = route.request
        path, _, query = request.url.replace("http://localhost:3000", "").partition("?")
        params = {key: values[0] for key, values in parse_qs(query).items()}
        method = request.method
        body = json.loads(request.post_data) if request.post_data else None
        state["calls"].append((method, path, body))
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            assert request.headers.get("x-xsrf-token") == "csrf-test-token"

        if path == "/api/auth/csrf":
            return route.fulfill(status=200, json={"token": "csrf-test-token"})
        if path == "/api/auth/login":
            state["signed_in"] = True
            return route.fulfill(status=200, json=account)
        if path == "/api/auth/me":
            return route.fulfill(status=200 if state["signed_in"] else 401, json=account)
        if path == "/api/admin/users" and method == "GET":
            rows = [row for row in state["users"]
                    if (not params.get("search") or params["search"] in row["email"])
                    and (not params.get("role") or params["role"] == row["role"])
                    and (not params.get("active") or params["active"] == str(row["active"]).lower())]
            size = int(params.get("size", 20))
            return route.fulfill(status=200, json={
                "content": rows[:size], "page": 0, "size": size, "totalElements": len(rows),
                "totalPages": 1, "first": True, "last": True})
        if path.startswith("/api/admin/users/") and path != "/api/admin/users/audit" and method == "PATCH":
            _, _, _, _, user_id, field = path.split("/")
            row = next(item for item in state["users"] if item["id"] == int(user_id))
            row.update({"role": body["role"]} if field == "role" else {"active": body["active"]})
            return route.fulfill(status=200, json=row)
        if path == "/api/admin/roles":
            return route.fulfill(status=200, json=[
                {"name": name, "description": f"{name.title()} role", "permissions": codes}
                for name, codes in roles.items()])
        if path == "/api/admin/permissions":
            return route.fulfill(status=200, json=PERMISSIONS)
        if path == "/api/admin/roles/DEVELOPER/permissions" and method == "PUT":
            roles["DEVELOPER"] = sorted(body["permissionCodes"])
            return route.fulfill(status=200, json={"name": "DEVELOPER", "permissions": roles["DEVELOPER"]})
        if path == "/api/admin/workspaces" and method == "GET":
            return route.fulfill(status=200, json=[{
                "id": WORKSPACE_ID, "name": "Platform team", "description": "Shared services",
                "ownerId": 2, "ownerEmail": "dev@example.test", "ownerUsername": "dev",
                "memberCount": len(state["members"]), "createdAt": "2026-11-01T08:00:00Z"}])
        if path == f"/api/admin/workspaces/{WORKSPACE_ID}/members" and method == "GET":
            return route.fulfill(status=200, json=state["members"])
        if path == f"/api/workspaces/{WORKSPACE_ID}/repositories":
            return route.fulfill(status=200, json=[{
                "id": REPOSITORY_ID, "fullName": "acme/shop", "defaultBranch": "main", "privateRepo": True,
                "status": "CONNECTED", "lastSyncedAt": None}])
        if path == f"/api/repositories/{REPOSITORY_ID}/sync" and method == "POST":
            return route.fulfill(status=200, json={"syncedAt": "2026-11-14T08:00:00Z"})
        if path == "/api/admin/system-config":
            if method == "PATCH":
                state["retention_days"] = body["auditRetentionDays"]
            return route.fulfill(status=200, json={
                "audit": {"retentionDays": state["retention_days"], "purgeSchedule": "0 0 0 * * * UTC"},
                "security": {"frontendUrl": "http://localhost:3000", "sessionCookieSecure": False,
                             "sessionCookieSameSite": "Lax", "githubOAuthConfigured": True},
                "integration": {"githubIntegrationBaseUrl": "http://github-integration:8082",
                                "internalSecretConfigured": True, "connectTimeoutSeconds": 5,
                                "readTimeoutSeconds": 150},
            })
        if path == "/api/documentation/drift/severity-rules":
            return route.fulfill(status=200, json={
                "levels": [{"level": "critical", "min_score": 75, "max_score": 100,
                            "meaning": "Breaking removal", "action": "Fix before merge"}]})
        if path == "/api/admin/health":
            return route.fulfill(status=state["health_status"], json=state["health_payload"])
        if path == "/api/admin/system-analytics":
            return route.fulfill(status=200, json={
                "from": params["from"], "to": params["to"],
                "repositoriesCreated": 4, "documentsCreated": 9,
                "aiJobs": {"completed": 12, "failed": 1, "observedSince": "2026-11-18T00:00:00Z",
                           "scope": "CURRENT_AI_PROCESS"},
                "audit": {"administration": 5, "documentWorkflow": 14, "documentVersion": 8},
            })
        if path == "/api/admin/users/audit":
            if state["audit_status"] != 200:
                return route.fulfill(status=state["audit_status"], json={})
            return route.fulfill(status=200, json={
                "content": state["audit_entries"], "page": 0, "size": 20,
                "totalElements": len(state["audit_entries"]), "totalPages": 1})
        if path == "/api/admin/notification-policies" and method == "GET":
            return route.fulfill(status=200, json={
                "supportedEvents": ["REPOSITORY_CONNECTED", "AI_JOB_FAILED"],
                "policies": state["policies"],
            })
        if path.startswith("/api/admin/notification-policies/") and method == "PUT":
            event = path.rsplit("/", 1)[-1]
            saved = {"event": event, "recipients": body["recipients"], "enabled": body["enabled"],
                     "updatedAt": "2026-11-19T02:10:00Z"}
            state["policies"] = [p for p in state["policies"] if p["event"] != event] + [saved]
            return route.fulfill(status=200, json=saved)
        if path.startswith("/api/admin/notification-policies/") and method == "DELETE":
            event = path.rsplit("/", 1)[-1]
            state["policies"] = [p for p in state["policies"] if p["event"] != event]
            return route.fulfill(status=204, body="")
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {method} {path}"})

    page.route("**/api/**", handle)
    return state


def sign_in(page: Page, account):
    page.goto("http://localhost:3000/")
    page.get_by_label("Email").fill(account["email"])
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Signed in successfully")).to_be_visible()


def open_admin(page: Page, tab=None):
    sign_in(page, ADMIN)
    page.get_by_role("button", name="Administration").first.click()
    expect(page.get_by_role("heading", name="Administration")).to_be_visible()
    if tab:
        page.get_by_role("tab", name=tab).click()


def test_only_administrators_see_the_administration_entry_points(page: Page):
    install_api(page, account=DEVELOPER)
    sign_in(page, DEVELOPER)
    expect(page.get_by_role("button", name="Administration")).to_have_count(0)
    page.get_by_role("button", name="GitHub Connection").first.click()
    expect(page.get_by_role("navigation").get_by_role("button", name="Administration")).to_have_count(0)


def test_admin_filters_users_changes_roles_and_disables_accounts(page: Page):
    state = install_api(page)
    open_admin(page)

    expect(page.get_by_role("row")).to_have_count(3)
    expect(page.get_by_label("Role for admin@example.test")).to_be_disabled()
    expect(page.get_by_role("row", name="dev@example.test").get_by_role("button")).to_be_enabled()

    page.get_by_label("Role for dev@example.test").select_option("STAFF")
    expect(page.get_by_text("Role of dev@example.test changed to STAFF.")).to_be_visible()
    assert ("PATCH", "/api/admin/users/2/role", {"role": "STAFF"}) in state["calls"]

    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("row", name="dev@example.test").get_by_role("button", name="Disable").click()
    expect(page.get_by_role("row", name="dev@example.test").get_by_role("button", name="Enable")).to_be_visible()
    assert ("PATCH", "/api/admin/users/2/status", {"active": False}) in state["calls"]


def test_admin_edits_role_permissions(page: Page):
    state = install_api(page)
    open_admin(page)

    role = page.locator("details.admin-role", has_text="DEVELOPER")
    role.locator("summary").click()
    expect(role.get_by_label("DOCUMENT_VIEW")).to_be_checked()
    role.get_by_label("DOCUMENT_APPROVE").check()
    role.get_by_role("button", name="Save permissions").click()

    expect(role.get_by_text("Permissions saved.")).to_be_visible()
    assert ("PUT", "/api/admin/roles/DEVELOPER/permissions",
            {"permissionCodes": ["DOCUMENT_VIEW", "DOCUMENT_APPROVE"]}) in state["calls"]


def test_admin_reviews_system_workspaces_and_syncs_a_repository(page: Page):
    state = install_api(page)
    open_admin(page, "Workspaces & repositories")

    expect(page.get_by_role("row", name="acme/shop")).to_contain_text("Private")
    expect(page.get_by_text("Dev User")).to_be_visible()

    page.get_by_role("button", name="Sync").click()
    expect(page.get_by_text("acme/shop synchronized.")).to_be_visible()
    assert ("POST", f"/api/repositories/{REPOSITORY_ID}/sync", {}) in state["calls"]


def test_admin_health_distinguishes_auth_errors_payload_failures_and_up(page: Page):
    state = install_api(
        page,
        health_status=403,
        health_payload={"message": "Forbidden"},
    )
    open_admin(page, "Health & monitoring")
    expect(page.get_by_role("alert")).to_contain_text("Administrator access is required")
    expect(page.get_by_role("row", name="Administration Health BFF")).to_contain_text("Auth error")

    state["health_status"] = 200
    state["health_payload"] = {
        "status": "DEGRADED",
        "services": [
            {"id": "backend", "name": "Backend API", "status": "UP", "httpStatus": 200, "latencyMs": 3, "detail": "Reachable"},
            {"id": "github-integration", "name": "GitHub Integration Service", "status": "DOWN", "httpStatus": 503, "latencyMs": 15, "detail": "HTTP 503"},
        ],
    }
    page.get_by_role("button", name="Check again").click()
    expect(page.get_by_role("row", name="Backend API")).to_contain_text("Up")
    expect(page.get_by_role("row", name="GitHub Integration Service")).to_contain_text("Down")


def test_admin_config_analytics_audit_and_notification_policies(page: Page):
    state = install_api(page)
    open_admin(page, "System configuration")

    page.get_by_label("Audit retention days").fill("60")
    page.get_by_role("button", name="Save configuration").click()
    expect(page.get_by_text("System configuration saved.")).to_be_visible()
    assert ("PATCH", "/api/admin/system-config", {"auditRetentionDays": 60}) in state["calls"]
    expect(page.get_by_text("Fix before merge")).to_be_visible()

    page.get_by_role("tab", name="Audit & analytics").click()
    expect(page.locator(".admin-stat", has_text="Repositories connected").locator("strong")).to_have_text("4")
    expect(page.locator(".admin-stat", has_text="AI jobs completed").locator("strong")).to_have_text("12")
    expect(page.get_by_role("heading", name="Administrative audit log (1)")).to_be_visible()
    expect(page.get_by_text("USER_ROLE_CHANGED")).to_be_visible()

    page.get_by_role("tab", name="Notifications").click()
    expect(page.get_by_label("Recipients for AI_JOB_FAILED")).to_have_value("ops@example.test")
    page.get_by_label("Recipients for AI_JOB_FAILED").fill("ops@example.test, admin@example.test")
    page.get_by_role("button", name="Save policy").nth(1).click()
    expect(page.get_by_text("Policy for AI_JOB_FAILED saved.")).to_be_visible()
PERMISSIONS = [{"code": "DOCUMENT_VIEW", "description": "View documents"},
               {"code": "DOCUMENT_APPROVE", "description": "Approve documents"},
               {"code": "USER_VIEW", "description": "View users"}]


def user_row(account, active=True):
    return {key: account[key] for key in ("id", "email", "username", "firstName", "lastName", "role")} | {
        "active": active, "createdAt": "2026-10-01T09:00:00"}


def install_api(page: Page, account=ADMIN, **options):
    state = {"calls": [], "users": [user_row(ADMIN), user_row(DEVELOPER)],
             "github_status": 200, "workflows_status": 200, "signed_in": False,
             "preferences": {"emailUpdates": True, "documentChanges": True, "reviewRequests": False,
                             "systemNotifications": True}, **options}
    roles = {"DEVELOPER": ["DOCUMENT_VIEW"], "ADMINISTRATOR": ["USER_VIEW"]}

    def handle(route):
        request = route.request
        path, _, query = request.url.replace("http://localhost:3000", "").partition("?")
        params = {key: values[0] for key, values in parse_qs(query).items()}
        method = request.method
        body = json.loads(request.post_data) if request.post_data else None
        state["calls"].append((method, path, body))
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            assert request.headers.get("x-xsrf-token") == "csrf-test-token"

        if path == "/api/auth/csrf":
            return route.fulfill(status=200, json={"token": "csrf-test-token"})
        if path == "/api/auth/login":
            state["signed_in"] = True
            return route.fulfill(status=200, json=account)
        if path == "/api/auth/me":
            return route.fulfill(status=200 if state["signed_in"] else 401, json=account)
        if path == "/api/admin/users" and method == "GET":
            rows = [row for row in state["users"]
                    if (not params.get("search") or params["search"] in row["email"])
                    and (not params.get("role") or params["role"] == row["role"])
                    and (not params.get("active") or params["active"] == str(row["active"]).lower())]
            size = int(params.get("size", 20))
            return route.fulfill(status=200, json={
                "content": rows[:size], "page": 0, "size": size, "totalElements": len(rows),
                "totalPages": 1, "first": True, "last": True})
        if path.startswith("/api/admin/users/") and method == "PATCH":
            _, _, _, _, user_id, field = path.split("/")
            row = next(item for item in state["users"] if item["id"] == int(user_id))
            row.update({"role": body["role"]} if field == "role" else {"active": body["active"]})
            return route.fulfill(status=200, json=row)
        if path == "/api/admin/roles":
            return route.fulfill(status=200, json=[
                {"name": name, "description": f"{name.title()} role", "permissions": codes}
                for name, codes in roles.items()])
        if path == "/api/admin/permissions":
            return route.fulfill(status=200, json=PERMISSIONS)
        if path == "/api/admin/roles/DEVELOPER/permissions" and method == "PUT":
            roles["DEVELOPER"] = sorted(body["permissionCodes"])
            return route.fulfill(status=200, json={"name": "DEVELOPER", "permissions": roles["DEVELOPER"]})
        if path == "/api/managed-workspaces":
            return route.fulfill(status=200, json=[{
                "id": WORKSPACE_ID, "name": "Platform team", "description": "Shared services", "ownerId": 1,
                "accessRole": "OWNER"}])
        if path == f"/api/managed-workspaces/{WORKSPACE_ID}/members":
            return route.fulfill(status=200, json=[{"userId": 2, "username": "dev", "displayName": "Dev User"}])
        if path == f"/api/workspaces/{WORKSPACE_ID}/repositories":
            return route.fulfill(status=200, json=[{
                "id": REPOSITORY_ID, "fullName": "acme/shop", "defaultBranch": "main", "privateRepo": True,
                "status": "CONNECTED", "lastSyncedAt": None}])
        if path.startswith("/api/workspaces/ws-") and path.endswith("/repositories"):
            return route.fulfill(status=200, json=[])
        if path == f"/api/repositories/{REPOSITORY_ID}/sync" and method == "POST":
            return route.fulfill(status=200, json={"syncedAt": "2026-11-14T08:00:00Z"})
        if path == "/api/documentation/drift/severity-rules":
            return route.fulfill(status=200, json={"levels": [{"level": "critical", "min_score": 75}]})
        if path == "/api/github/connection":
            return route.fulfill(status=state["github_status"], json={"connected": True})
        if path == "/api/document-workflows/history-accessible":
            if state["workflows_status"] != 200:
                return route.fulfill(status=state["workflows_status"], json={})
            return route.fulfill(status=200, json={
                "content": [{"id": WORKFLOW_ID, "documentId": "doc-1", "documentTitle": "Shop API",
                             "ownerUserId": "2", "status": "PENDING_MANAGER_APPROVAL",
                             "updatedAt": "2026-11-13T10:00:00Z"}],
                "page": 0, "size": 10, "totalElements": 1, "totalPages": 1, "first": True, "last": True})
        if path == f"/api/document-workflows/{WORKFLOW_ID}/history":
            return route.fulfill(status=200, json=[{
                "id": "a1", "actorUserId": "3", "actorRole": "STAFF", "action": "STAFF_REVIEW",
                "previousStatus": "STAFF_REVIEWING", "newStatus": "PENDING_MANAGER_APPROVAL",
                "comment": "Looks good", "createdAt": "2026-11-13T10:00:00Z"}])
        if path == "/api/profile/notification-preferences":       # LD-51: Notifications tab (LD-321)
            if method == "PUT":
                state["preferences"] = body
            return route.fulfill(status=200, json=state["preferences"])
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {method} {path}"})

    page.route("**/api/**", handle)
    return state


def sign_in(page: Page, account):
    page.goto("http://localhost:3000/")
    page.get_by_label("Email").fill(account["email"])
    page.get_by_label("Password").fill("test-only-password")
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Signed in successfully")).to_be_visible()


def open_admin(page: Page, tab=None):
    sign_in(page, ADMIN)
    page.get_by_role("button", name="Administration").first.click()
    expect(page.get_by_role("heading", name="Administration")).to_be_visible()
    if tab:
        page.get_by_role("tab", name=tab).click()


def test_only_administrators_see_the_administration_entry_points(page: Page):
    install_api(page, account=DEVELOPER)
    sign_in(page, DEVELOPER)
    expect(page.get_by_role("button", name="Administration")).to_have_count(0)
    page.get_by_role("button", name="GitHub Connection").first.click()
    expect(page.get_by_role("navigation").get_by_role("button", name="Administration")).to_have_count(0)


def test_admin_filters_users_changes_roles_and_disables_accounts(page: Page):
    state = install_api(page)
    open_admin(page)

    expect(page.get_by_role("row")).to_have_count(3)                       # header + two users
    expect(page.get_by_label("Role for admin@example.test")).to_be_disabled()   # no self-service changes
    expect(page.get_by_role("row", name="dev@example.test").get_by_role("button")).to_be_enabled()

    page.get_by_label("Role for dev@example.test").select_option("STAFF")
    expect(page.get_by_text("Role of dev@example.test changed to STAFF.")).to_be_visible()
    assert ("PATCH", "/api/admin/users/2/role", {"role": "STAFF"}) in state["calls"]

    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("row", name="dev@example.test").get_by_role("button", name="Disable").click()
    expect(page.get_by_role("row", name="dev@example.test").get_by_role("button", name="Enable")).to_be_visible()
    assert ("PATCH", "/api/admin/users/2/status", {"active": False}) in state["calls"]

    page.get_by_label("Search users").fill("dev@")
    page.get_by_role("button", name="Search", exact=True).click()
    expect(page.get_by_role("row")).to_have_count(2)
    expect(page.get_by_role("row", name="admin@example.test")).to_have_count(0)


def test_admin_edits_role_permissions(page: Page):
    state = install_api(page)
    open_admin(page)

    role = page.locator("details.admin-role", has_text="DEVELOPER")
    role.locator("summary").click()
    expect(role.get_by_label("DOCUMENT_VIEW")).to_be_checked()
    role.get_by_label("DOCUMENT_APPROVE").check()
    role.get_by_role("button", name="Save permissions").click()

    expect(role.get_by_text("Permissions saved.")).to_be_visible()
    assert ("PUT", "/api/admin/roles/DEVELOPER/permissions",
            {"permissionCodes": ["DOCUMENT_VIEW", "DOCUMENT_APPROVE"]}) in state["calls"]


def test_admin_reviews_workspaces_and_syncs_a_repository(page: Page):
    state = install_api(page)
    open_admin(page, "Workspaces & repositories")

    page.get_by_label("Workspace").select_option(label="Platform team (OWNER)")
    expect(page.get_by_role("row", name="acme/shop")).to_contain_text("Private")
    expect(page.get_by_text("Dev User")).to_be_visible()                  # workspace members

    page.get_by_role("button", name="Sync").click()
    expect(page.get_by_text("acme/shop synchronized.")).to_be_visible()
    assert ("POST", f"/api/repositories/{REPOSITORY_ID}/sync", {}) in state["calls"]


def test_admin_sees_configuration_health_analytics_audit_and_notifications(page: Page):
    state = install_api(page, github_status=503, workflows_status=403)
    open_admin(page, "System configuration")
    expect(page.get_by_text('"min_score": 75')).to_be_visible()

    page.get_by_role("tab", name="Health & monitoring").click()
    expect(page.get_by_role("row", name="Backend API")).to_contain_text("Up")
    expect(page.get_by_role("row", name="GitHub Integration Service")).to_contain_text("Down")
    state["github_status"] = 200
    page.get_by_role("button", name="Check again").click()
    expect(page.get_by_role("row", name="GitHub Integration Service")).to_contain_text("Up")

    page.get_by_role("tab", name="Audit & analytics").click()
    expect(page.locator(".admin-stat", has_text="Total users").locator("strong")).to_have_text("2")
    expect(page.locator(".admin-stat", has_text="Disabled").locator("strong")).to_have_text("0")
    expect(page.get_by_role("alert")).to_have_text("You do not have access to this item.")

    state["workflows_status"] = 200
    page.get_by_role("tab", name="Users & roles").click()
    page.get_by_role("tab", name="Audit & analytics").click()
    expect(page.get_by_role("heading", name="Audit log (1)")).to_be_visible()
    page.get_by_role("button", name="History").click()
    expect(page.get_by_text("STAFF_REVIEW")).to_be_visible()
    expect(page.get_by_text("Looks good")).to_be_visible()

    page.get_by_role("tab", name="Notifications").click()
    expect(page.get_by_label("Email updates")).to_be_checked()
    expect(page.get_by_label("Document changes")).to_be_checked()
    expect(page.get_by_label("Review requests")).not_to_be_checked()



