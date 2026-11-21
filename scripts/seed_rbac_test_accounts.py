"""Create the five RBAC test accounts (one per role) through the existing backend API.

    python scripts/seed_rbac_test_accounts.py [--base-url http://localhost:3000]
                                              [--accounts scripts/rbac-test-accounts.example.json]

1. Every account is registered with POST /api/auth/register (the backend always creates DEVELOPER).
2. The Administrator account then signs in and assigns the other roles with
   PATCH /api/admin/users/{id}/role.

The backend has no seeded administrator, so the Administrator account must be promoted once by hand
before step 2 (see Docs/rbac-screen-flow.md, "Tài khoản test"). Registering an account that already
exists is not an error. Only the standard library is used.
"""
import argparse
import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ACCOUNTS = Path(__file__).with_name("rbac-test-accounts.example.json")


class Client:
    """One cookie session. The CSRF token is fetched once and again after sign-in (Spring rotates it)
    or after a 403."""

    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf_token = None

    def call(self, method, path, body=None):
        if method == "GET":
            return self._send(method, path, body, {})
        if self.csrf_token is None:
            self.csrf_token = self._send("GET", "/api/auth/csrf", None, {})[1]["token"]
        status, payload = self._send(method, path, body, {"X-XSRF-TOKEN": self.csrf_token})
        if status == 403:          # stale token: refresh once
            self.csrf_token = self._send("GET", "/api/auth/csrf", None, {})[1]["token"]
            status, payload = self._send(method, path, body, {"X-XSRF-TOKEN": self.csrf_token})
        if path == "/api/auth/login":
            self.csrf_token = None
        return status, payload

    def _send(self, method, path, body, extra_headers):
        headers = {"Accept": "application/json", **extra_headers}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=20) as response:
                text = response.read().decode("utf-8")
                return response.status, json.loads(text) if text else {}
        except urllib.error.HTTPError as error:
            text = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(text)
            except ValueError:
                return error.code, {"message": text[:200]}


def register(client, account):
    status, body = client.call("POST", "/api/auth/register", {
        key: account[key] for key in ("username", "email", "password", "firstName", "lastName")})
    if status == 201:
        return "registered"
    if status == 409:
        return "already exists"
    raise SystemExit(f"Could not register {account['email']}: HTTP {status} {body.get('message', '')}")


def find_user(admin, email):
    # Searching by email returns just this user instead of paging through all of them.
    status, body = admin.call("GET", "/api/admin/users?" + urllib.parse.urlencode({"search": email, "size": 20}))
    if status != 200:
        raise SystemExit(f"Could not list users as the Administrator: HTTP {status} {body.get('message', '')}")
    matches = [user for user in body.get("content", []) if user.get("email", "").lower() == email.lower()]
    if not matches:
        raise SystemExit(f"User {email} was not found.")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--accounts", type=Path, default=DEFAULT_ACCOUNTS)
    args = parser.parse_args()

    accounts = json.loads(args.accounts.read_text(encoding="utf-8"))["accounts"]
    admins = [account for account in accounts if account["role"] == "ADMINISTRATOR"]
    if len(admins) != 1:
        raise SystemExit("The accounts file needs exactly one ADMINISTRATOR account.")
    admin_account = admins[0]

    registrar = Client(args.base_url)
    for account in accounts:
        print(f"{account['email']:<36} {register(registrar, account)}")

    admin = Client(args.base_url)
    status, body = admin.call("POST", "/api/auth/login",
                              {"email": admin_account["email"], "password": admin_account["password"]})
    if status != 200 or body.get("role") not in ("ADMINISTRATOR", "ADMIN"):
        raise SystemExit(
            f"Sign-in as {admin_account['email']} did not give an Administrator session "
            f"(HTTP {status}, role {body.get('role')}). Promote this account once as described in "
            "Docs/rbac-screen-flow.md, then run the script again.")

    for account in accounts:
        if account is admin_account:
            continue
        user = find_user(admin, account["email"])
        user_id, current_role = user["id"], user.get("role")
        if current_role == account["role"]:
            print(f"{account['email']:<36} role {current_role} (unchanged)")
            continue
        status, body = admin.call("PATCH", f"/api/admin/users/{user_id}/role", {"role": account["role"]})
        if status != 200:
            raise SystemExit(f"Could not assign {account['role']} to {account['email']}: "
                             f"HTTP {status} {body.get('message', '')}")
        print(f"{account['email']:<36} role {current_role} -> {account['role']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
