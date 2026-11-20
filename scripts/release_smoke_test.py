#!/usr/bin/env python3
"""LD-404 Release E2E Smoke & Persistence Verification Script (Standard Library Only)."""
import argparse
import http.cookiejar
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3001").rstrip("/")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8081").rstrip("/")
ANALYZER_URL = os.environ.get("ANALYZER_URL", "http://localhost:8003").rstrip("/")
AI_SERVICE_URL = os.environ.get("AI_SERVICE_URL", "http://localhost:8002").rstrip("/")
INTERNAL_SECRET = os.environ.get("GITHUB_INTEGRATION_INTERNAL_SECRET", "")
GITHUB_INTEGRATION_URL = os.environ.get("GITHUB_INTEGRATION_URL", "http://localhost:8083").rstrip("/")

RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _create_secure_state_dir() -> str:
    """P2 FIX: Tạo thư mục tạm 0o700 để lưu state."""
    d = tempfile.mkdtemp(prefix="ld404-smoke-state-")
    os.chmod(d, 0o700)
    return d


def log(msg: str) -> None:
    print(msg, flush=True)


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    log(f" [OK] {msg}")


def http_json(opener, method: str, url: str, data=None, headers=None, timeout=30):
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with opener.open(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8") or "{}"
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") or "{}"
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def get_xsrf(opener) -> str:
    """Lấy XSRF cookie từ CSRF endpoint của Spring Security."""
    opener.open(urllib.request.Request(f"{BACKEND_URL}/api/csrf", method="GET"), timeout=15).read()
    for cookie in opener.cookiejar:
        if cookie.name == "XSRF-TOKEN":
            return urllib.request.unquote(cookie.value)
    return ""


def ai_headers() -> dict:
    return {"X-Internal-Secret": INTERNAL_SECRET} if INTERNAL_SECRET else {}


# ---------------------------------------------------------------------------
# Phase: pre-restart
# ---------------------------------------------------------------------------
def run_pre_restart(state_file: str) -> dict:
    log(f"=== PRE-RESTART phase (run_id={RUN_ID}) ===")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    username = f"smoke_{RUN_ID}"
    email = f"{username}@smoke.ld404.local"
    password = f"SmokePass!{RUN_ID}"

    # 1. Register
    st, body = http_json(opener, "POST", f"{BACKEND_URL}/api/auth/register", {
        "username": username, "email": email, "password": password,
    })
    assert_true(st in (200, 201), f"Register user (HTTP {st})")
    user_id = body.get("id") or body.get("userId")
    assert_true(bool(user_id), f"Got user id ({user_id})")

    # 2. Login
    xcsrf = get_xsrf(opener)
    st, body = http_json(opener, "POST", f"{BACKEND_URL}/api/auth/login", {
        "username": username, "password": password,
    }, headers={"X-XSRF-TOKEN": xcsrf})
    assert_true(st == 200, f"Login (HTTP {st})")

    # 3. Create document
    xcsrf = get_xsrf(opener)
    st, body = http_json(opener, "POST", f"{BACKEND_URL}/api/documents", {
        "title": "LD-404 Smoke Doc",
        "content": "Grounding evidence must persist at version 2 after restart.",
    }, headers={"X-XSRF-TOKEN": xcsrf})
    assert_true(st in (200, 201), f"Create document (HTTP {st})")
    doc_id = body.get("id") or body.get("documentId")
    assert_true(bool(doc_id), f"Got doc id ({doc_id})")

    # 4. Trigger AI analysis job
    st, body = http_json(opener, "POST", f"{AI_SERVICE_URL}/internal/jobs", {
        "doc_id": doc_id, "document_id": doc_id, "content": "smoke grounding",
    }, headers=ai_headers())
    assert_true(st in (200, 201, 202), f"Trigger AI job (HTTP {st})")
    job_id = body.get("job_id") or body.get("id")
    assert_true(bool(job_id), f"Got job id ({job_id})")

    # 5. Wait for job completion
    deadline = time.time() + 120
    job_status = "pending"
    while time.time() < deadline:
        st, body = http_json(opener, "GET", f"{AI_SERVICE_URL}/internal/jobs/{job_id}", headers=ai_headers())
        if st == 200:
            job_status = body.get("status", "unknown")
            if job_status in ("completed", "done", "succeeded"):
                break
        time.sleep(2)
    assert_true(job_status in ("completed", "done", "succeeded"), f"AI job completed (status={job_status})")

    # 6. Publish v1
    xcsrf = get_xsrf(opener)
    st, _ = http_json(opener, "POST", f"{BACKEND_URL}/api/documents/{doc_id}/publish",
                      {"version": 1}, headers={"X-XSRF-TOKEN": xcsrf})
    assert_true(st in (200, 201), f"Publish v1 (HTTP {st})")

    # 7. Update → v2 + re-analyze
    xcsrf = get_xsrf(opener)
    st, _ = http_json(opener, "PUT", f"{BACKEND_URL}/api/documents/{doc_id}", {
        "title": "LD-404 Smoke Doc v2",
        "content": "Updated during LD-404 smoke review flow",
    }, headers={"X-XSRF-TOKEN": xcsrf})
    assert_true(st in (200, 204), f"Update document to v2 (HTTP {st})")

    st, _ = http_json(opener, "POST", f"{AI_SERVICE_URL}/internal/jobs", {
        "doc_id": doc_id, "document_id": doc_id, "content": "smoke grounding v2", "version": 2,
    }, headers=ai_headers())
    assert_true(st in (200, 201, 202), f"Trigger AI job for v2 (HTTP {st})")

    # 8. Publish v2
    xcsrf = get_xsrf(opener)
    st, _ = http_json(opener, "POST", f"{BACKEND_URL}/api/documents/{doc_id}/publish",
                      {"version": 2}, headers={"X-XSRF-TOKEN": xcsrf})
    assert_true(st in (200, 201), f"Publish v2 (HTTP {st})")

    # Save state
    state = {
        "run_id": RUN_ID,
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
    os.chmod(state_file, 0o600)  # P2 FIX: quyền hạn chế
    log(f"State saved to secure file: {state_file}")
    return state


# ---------------------------------------------------------------------------
# Phase: post-restart
# ---------------------------------------------------------------------------
def run_post_restart(state_file: str) -> dict:
    log(f"=== POST-RESTART phase (state={state_file}) ===")
    if not os.path.isfile(state_file):
        raise FileNotFoundError(f"State file not found: {state_file}")

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    username = state["username"]
    password = state["password"]
    doc_id = state["doc_id"]
    expected_version = state.get("expected_version", 2)

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    # 1. Re-login
    xcsrf = get_xsrf(opener)
    st, _ = http_json(opener, "POST", f"{BACKEND_URL}/api/auth/login",
                      {"username": username, "password": password},
                      headers={"X-XSRF-TOKEN": xcsrf})
    assert_true(st == 200, f"Re-login after restart (HTTP {st})")

    # 2. Document still exists
    st, body = http_json(opener, "GET", f"{BACKEND_URL}/api/documents/{doc_id}")
    assert_true(st == 200, f"Document persisted (HTTP {st})")
    assert_true(body.get("title", "").startswith("LD-404 Smoke Doc"), "Document title persisted")

    # 3. Current version is expected_version
    st, body = http_json(opener