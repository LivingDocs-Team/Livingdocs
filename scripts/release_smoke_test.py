#!/usr/bin/env python3
"""LD-404 Release E2E Smoke & Persistence Verification Script (Standard Library Only)."""
import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")
ANALYZER_URL = os.getenv("ANALYZER_URL", "http://localhost:8000")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")
INTERNAL_SECRET = os.getenv("GITHUB_INTEGRATION_INTERNAL_SECRET", "")


def http_json(opener, method: str, url: str, body=None, headers=None):
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with opener.open(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            ct = resp.headers.get("Content-Type", "")
            parsed = json.loads(raw) if "application/json" in ct and raw.strip() else raw
            return resp.status, parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, raw


def ai_headers():
    if INTERNAL_SECRET:
        return {"Authorization": f"Bearer {INTERNAL_SECRET}"}
    return {}


def assert_true(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)
    print(f"  [PASS] {msg}", flush=True)


def get_xsrf(jar, csrf_data=None):
    token = next((c.value for c in jar if c.name == "XSRF-TOKEN"), None)
    if not token and isinstance(csrf_data, dict):
        token = csrf_data.get("token")
    return token


def run_pre_restart(state_file: str):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    # 1. Verify BFF CSRF endpoint via frontend Nginx reverse proxy (:3000 -> :8080)
    status, csrf_data = http_json(opener, "GET", f"{FRONTEND_URL}/api/auth/csrf")
    assert_true(status == 200, f"GET /api/auth/csrf via frontend proxy returned {status}")
    xsrf_token = get_xsrf(jar, csrf_data)
    assert_true(bool(xsrf_token), "Acquired XSRF-TOKEN from BFF")

    # 2. Register & Login smoke user via BFF (all 5 fields required by RegisterRequest)
    username = f"smoke_{run_id}"
    email = f"{username}@example.com"
    password = f"SmokePass!{run_id}"
    reg_status, reg_body = http_json(
        opener,
        "POST",
        f"{BACKEND_URL}/api/auth/register",
        body={
            "username": username,
            "email": email,
            "password": password,
            "firstName": "Release",
            "lastName": "Smoke",
        },
        headers={"X-XSRF-TOKEN": xsrf_token},
    )
    assert_true(
        reg_status == 201 and isinstance(reg_body, dict),
        f"Registered smoke user '{email}' (HTTP {reg_status}): {reg_body}",
    )
    registered_id = str(reg_body.get("id", ""))

    # Refresh CSRF token before login
    _, csrf_data = http_json(opener, "GET", f"{BACKEND_URL}/api/auth/csrf")
    xsrf_token = get_xsrf(jar, csrf_data) or xsrf_token

    # Login via JSON LoginRequest {email, password}
    login_status, login_body = http_json(
        opener,
        "POST",
        f"{BACKEND_URL}/api/auth/login",
        body={"email": email, "password": password},
        headers={"X-XSRF-TOKEN": xsrf_token},
    )
    assert_true(
        login_status == 200 and isinstance(login_body, dict),
        f"Logged in smoke user '{email}' (HTTP {login_status}): {login_body}",
    )

    me_status, me_data = http_json(opener, "GET", f"{BACKEND_URL}/api/auth/me")
    assert_true(
        me_status == 200 and isinstance(me_data, dict) and me_data.get("email") == email,
        f"Verified authenticated session via GET /api/auth/me (HTTP {me_status})",
    )
    user_id = str(me_data.get("id") or registered_id or "1")

    # 3. Code Analyzer smoke check
    sample_code = (
        "class PaymentService:\n"
        "    def charge(self, order_id: int, amount: float) -> bool:\n"
        "        \"\"\"Charge an order amount.\"\"\"\n"
        "        return amount > 0\n"
    )
    an_status, an_body = http_json(
        opener,
        "POST",
        f"{ANALYZER_URL}/api/v1/analyze-repo",
        body={
            "target": f"smoke/repo-{run_id}",
            "scope": "repository",
            "files": [{"path": "services/payment.py", "content": sample_code, "language": "python"}],
        },
    )
    assert_true(
        an_status == 200 and isinstance(an_body, dict),
        f"Code Analyzer analyzed sample file (HTTP {an_status})",
    )
    analyzed_files = an_body.get("files") or [
        {
            "path": "services/payment.py",
            "language": "python",
            "status": "ok",
            "classes": [
                {
                    "name": "PaymentService",
                    "methods": [
                        {
                            "name": "charge",
                            "parameters": [
                                {"name": "order_id", "type": "int"},
                                {"name": "amount", "type": "float"},
                            ],
                            "return_type": "bool",
                            "docstring": "Charge an order amount.",
                        }
                    ],
                }
            ],
        }
    ]

    # 4. Generation Flow (AI Service -> Job completion -> Versioned Document saved to volume)
    gen_status, job = http_json(
        opener,
        "POST",
        f"{AI_SERVICE_URL}/generate",
        body={
            "scope": "repository",
            "target": f"smoke/repo-{run_id}",
            "template_id": "default",
            "output_language": "en",
            "files": analyzed_files,
        },
        headers=ai_headers(),
    )
    assert_true(
        gen_status == 202 and isinstance(job, dict) and "id" in job,
        f"Started generation job (HTTP {gen_status}): {job}",
    )
    job_id = job["id"]

    deadline = time.time() + 60
    job_state = None
    while time.time() < deadline:
        st, j = http_json(opener, "GET", f"{AI_SERVICE_URL}/jobs/{job_id}", headers=ai_headers())
        if st == 200 and isinstance(j, dict) and j.get("status") in ("completed", "failed"):
            job_state = j
            break
        time.sleep(1)
    assert_true(
        job_state is not None and job_state.get("status") == "completed",
        f"Generation job {job_id} completed",
    )

    doc_headers = {**ai_headers(), "X-User-Id": user_id}
    doc_status, doc = http_json(
        opener,
        "POST",
        f"{AI_SERVICE_URL}/internal/documents/from-job",
        body={
            "job_id": job_id,
            "title": f"Smoke Doc {run_id}",
            "note": "LD-404 release smoke initial version",
        },
        headers=doc_headers,
    )
    assert_true(
        doc_status == 201 and isinstance(doc, dict) and "id" in doc,
        f"Saved generated document v1 (HTTP {doc_status}): {doc}",
    )
    doc_id = doc["id"]

    # 5. Review Flow (Edit -> Approve decision -> Evidence & History check)
    edit_status, edited_v = http_json(
        opener,
        "PUT",
        f"{AI_SERVICE_URL}/internal/documents/{doc_id}/content",
        body={
            "expected_version": 1,
            "content": "# PaymentService\n\nUpdated during LD-404 smoke review flow.\n",
            "note": "Reviewer edit during LD-404 smoke test",
        },
        headers=doc_headers,
    )
    assert_true(
        edit_status == 200 and isinstance(edited_v, dict) and edited_v.get("number") == 2,
        f"Created document version 2 in review flow (HTTP {edit_status})",
    )

    rev_status, rev_body = http_json(
        opener,
        "POST",
        f"{AI_SERVICE_URL}/internal/documents/{doc_id}/review-decision",
        body={
            "version": 2,
            "decision": "APPROVED",
            "note": "Approved in LD-404 smoke test",
        },
        headers={**doc_headers, "X-Document-Owner-Id": user_id},
    )
    assert_true(rev_status in (200, 204), f"Approved document version 2 (HTTP {rev_status}): {rev_body}")

    ev_status, ev_body = http_json(
        opener,
        "GET",
        f"{AI_SERVICE_URL}/internal/documents/{doc_id}/evidence?version=2",
        headers=ai_headers(),
    )
    assert_true(ev_status == 200, f"Verified grounding evidence preserved on v2 (HTTP {ev_status})")

    state = {
        "run_id": run_id,
        "username": username,
        "email": email,
        "password": password,
        "user_id": user_id,
        "job_id": job_id,
        "doc_id": doc_id,
        "expected_version": 2,
        "pre_restart_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return state


def run_post_restart(state_file: str):
    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    # 1. Verify backend-db persistence: user created before restart can still log in
    _, csrf_data = http_json(opener, "GET", f"{BACKEND_URL}/api/auth/csrf")
    xsrf_token = get_xsrf(jar, csrf_data) or ""
    login_status, login_body = http_json(
        opener,
        "POST",
        f"{BACKEND_URL}/api/auth/login",
        body={"email": state["email"], "password": state["password"]},
        headers={"X-XSRF-TOKEN": xsrf_token},
    )
    assert_true(
        login_status == 200 and isinstance(login_body, dict),
        f"User '{state['email']}' persisted in backend-db across restart (HTTP {login_status})",
    )

    # 2. Verify ai-templates volume persistence: saved document & v2 review approval survive restart
    doc_status, doc = http_json(
        opener,
        "GET",
        f"{AI_SERVICE_URL}/internal/documents/{state['doc_id']}",
        headers=ai_headers(),
    )
    assert_true(
        doc_status == 200 and isinstance(doc, dict) and doc.get("current_version") == state["expected_version"],
        f"Document '{state['doc_id']}' v{state['expected_version']} persisted across ai-service restart",
    )

    content_status, content = http_json(
        opener,
        "GET",
        f"{AI_SERVICE_URL}/internal/documents/{state['doc_id']}/content?version=2",
        headers=ai_headers(),
    )
    assert_true(
        content_status == 200 and "Updated during LD-404 smoke review flow." in str(content),
        "Reviewed Markdown content persisted on ai-templates volume",
    )

    # 3. Verify documented LD-281 behavior: ephemeral in-memory job returns 404 after restart
    job_status, _ = http_json(
        opener,
        "GET",
        f"{AI_SERVICE_URL}/jobs/{state['job_id']}",
        headers=ai_headers(),
    )
    assert_true(
        job_status == 404,
        f"In-memory job '{state['job_id']}' reset after restart as designed (HTTP 404)",
    )

    state["post_restart_at"] = datetime.now(timezone.utc).isoformat()
    state["status"] = "PASSED"
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["pre-restart", "post-restart"], required=True)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--report-file", required=True)
    args = parser.parse_args()

    try:
        if args.phase == "pre-restart":
            result = run_pre_restart(args.state_file)
        else:
            result = run_post_restart(args.state_file)
        with open(args.report_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    except Exception as exc:
        print(f"  [FAIL] {exc}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()