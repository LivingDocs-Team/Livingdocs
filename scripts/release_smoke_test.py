#!/usr/bin/env python3
"""LD-404 Release E2E Smoke & Persistence Verification Script (Standard Library Only).

Flow khớp với ai-service (document API thật ở đây, không phải backend Spring):
    POST /generate                              → tạo job sinh tài liệu
    POST /internal/documents/from-job            → tạo document v1
    PUT  /internal/documents/{id}/content        → tạo v2 (evidence inherit v1)
    GET  /internal/documents/{id}/evidence?version=N
    GET  /internal/documents/{id}/review-evidence?version=N
"""
import argparse
import http.cookiejar
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def _env_url(name: str, default: str) -> str:
    return os.environ.get(name, default).rstrip("/")


FRONTEND_URL   = _env_url("FRONTEND_URL",            "http://localhost:3001")
BACKEND_URL    = _env_url("BACKEND_URL",             "http://localhost:8080")
ANALYZER_URL   = _env_url("ANALYZER_URL",            "http://localhost:8003")
AI_SERVICE_URL = _env_url("AI_SERVICE_URL",          "http://localhost:8002")
GITHUB_INTEGRATION_URL = _env_url("GITHUB_INTEGRATION_URL", "http://localhost:8083")

# ai-service dùng Authorization: Bearer <INTERNAL_API_SECRET>.
# Fallback qua GITHUB_INTEGRATION_INTERNAL_SECRET để 1 secret dùng chung cho smoke.
AI_SERVICE_SECRET = (
    os.environ.get("AI_SERVICE_INTERNAL_SECRET")
    or os.environ.get("INTERNAL_API_SECRET")
    or os.environ.get("GITHUB_INTEGRATION_INTERNAL_SECRET", "")
)

RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _create_secure_state_dir() -> str:
    d = tempfile.mkdtemp(prefix="ld404-smoke-state-")
    os.chmod(d, 0o700)
    return d


def _write_state_secure(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def log(msg: str) -> None:
    print(msg, flush=True)


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    log(f" [OK] {msg}")


def log_endpoints() -> None:
    log(f" Endpoints: backend={BACKEND_URL}  frontend={FRONTEND_URL}  "
        f"ai={AI_SERVICE_URL}  analyzer={ANALYZER_URL}  github-int={GITHUB_INTEGRATION_URL}")
    if AI_SERVICE_SECRET:
        log(f" ai-service auth: Bearer <secret len={len(AI_SERVICE_SECRET)}>")
    else:
        log(" ai-service auth: (none) — set AI_SERVICE_INTERNAL_SECRET or GITHUB_INTEGRATION_INTERNAL_SECRET")


def http_json(opener, method: str, url: str, data=None, headers=None, timeout=30):
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    # Chỉ gắn Origin/Referer cho backend/frontend (Spring CORS).
    # ai-service (FastAPI) không cần — và gắn bừa có thể bị reject.
    if url.startswith(BACKEND_URL) or url.startswith(FRONTEND_URL):
        if "Origin" not in (headers or {}):
            req.add_header("Origin", FRONTEND_URL)
        if "Referer" not in (headers or {}):
            req.add_header("Referer", FRONTEND_URL + "/")

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


def get_xsrf(opener, jar: http.cookiejar.CookieJar) -> str:
    """Lấy XSRF cookie từ /api/auth/csrf (Spring Security)."""
    try:
        opener.open(
            urllib.request.Request(f"{BACKEND_URL}/api/auth/csrf", method="GET"),
            timeout=15,
        ).read()
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        log(f" [WARN] /api/auth/csrf failed: {e}")

    for cookie in jar:
        if cookie.name == "XSRF-TOKEN":
            return urllib.parse.unquote(cookie.value)
    return ""


def ai_headers(user_id=None, extra=None) -> dict:
    """Header cho ai-service: Authorization Bearer + X-User-Id (bắt buộc cho endpoint mutate)."""
    h = {}
    if AI_SERVICE_SECRET:
        h["Authorization"] = f"Bearer {AI_SERVICE_SECRET}"
    if user_id is not None:
        h["X-User-Id"] = str(user_id)
    if extra:
        h.update(extra)
    return h


# ---------------------------------------------------------------------------
# Phase: pre-restart
# ---------------------------------------------------------------------------
def run_pre_restart(state_file: str) -> dict:
    log(f"=== PRE-RESTART phase (run_id={RUN_ID}) ===")
    log_endpoints()

    # Backend: session dùng cookie, cần jar riêng
    jar = http.cookiejar.CookieJar()
    backend_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    # Ai-service: không dùng cookie, chỉ header
    ai_client = urllib.request.build_opener()

    username   = f"smoke_{RUN_ID}"
    email      = f"{username}@example.com"
    password   = f"SmokePass!{RUN_ID}"
    first_name = "Smoke"
    last_name  = f"Test{RUN_ID[-6:]}"

    # 1. Register (backend) — yêu cầu firstName/lastName
    xcsrf = get_xsrf(backend_opener, jar)
    st, body = http_json(backend_opener, "POST", f"{BACKEND_URL}/api/auth/register", {
        "username": username, "email": email, "password": password,
        "firstName": first_name, "lastName": last_name,
    }, headers={"X-XSRF-TOKEN": xcsrf})
    if st not in (200, 201):
        log(f" [DEBUG] Register failed: HTTP {st} body={body}")
    assert_true(st in (200, 201), f"Register user (HTTP {st})")
    user_id = (body.get("id") or body.get("userId")) if isinstance(body, dict) else None
    assert_true(bool(user_id), f"Got user id ({user_id})")

    # 2. Login (backend) — LoginRequest chỉ có email/password
    xcsrf = get_xsrf(backend_opener, jar)
    st, body = http_json(backend_opener, "POST", f"{BACKEND_URL}/api/auth/login",
                         {"email": email, "password": password},
                         headers={"X-XSRF-TOKEN": xcsrf})
    if st != 200:
        log(f" [DEBUG] Login failed: HTTP {st} body={body}")
    assert_true(st == 200, f"Login (HTTP {st})")

    # 3. /generate (ai-service) — body khớp với test_evidence_persistence.py
    st, body = http_json(ai_client, "POST", f"{AI_SERVICE_URL}/generate", {
        "scope": "file",
        "target": "smoke.py",
        "files": [{
            "path": "smoke.py",
            "language": "python",
            "status": "ok",
            "functions": [{
                "name": "smoke_fn",
                "parameters": [],
                "source": "def smoke_fn():\n    return 42",
            }],
        }],
    }, headers=ai_headers(user_id), timeout=120)
    if st not in (200, 201, 202):
        log(f" [DEBUG] /generate failed: HTTP {st} body={body}")
    assert_true(st in (200, 201, 202), f"POST /generate (HTTP {st})")
    job_id = (body.get("id") or body.get("job_id")) if isinstance(body, dict) else None
    assert_true(bool(job_id), f"Got job id ({job_id})")

    # 4. Best-effort wait: offline mode (no ANTHROPIC_API_KEY) thường sync;
    #    nếu async, chờ tối đa 60s. Dù fail thì vẫn thử from-job (test reference không poll).
    deadline = time.time() + 60
    job_status = "unknown"
    while time.time() < deadline:
        st_j, jb = http_json(ai_client, "GET", f"{AI_SERVICE_URL}/jobs/{job_id}",
                             headers=ai_headers(user_id))
        if st_j == 200 and isinstance(jb, dict):
            job_status = (jb.get("status") or "").lower()
            if job_status in ("completed", "done", "succeeded", "success"):
                break
        time.sleep(1)
    log(f" [INFO] job status after wait: {job_status}")

    # 5. Create v1 from job (ai-service)
    st, body = http_json(ai_client, "POST",
                         f"{AI_SERVICE_URL}/internal/documents/from-job",
                         {"job_id": job_id},
                         headers=ai_headers(user_id))
    if st not in (200, 201):
        log(f" [DEBUG] from-job failed: HTTP {st} body={body}")
    assert_true(st in (200, 201), f"Create document from job (HTTP {st})")
    doc_id = (body.get("id") or body.get("documentId") or body.get("document_id")) \
             if isinstance(body, dict) else None
    assert_true(bool(doc_id), f"Got doc id ({doc_id})")

    # 6. Create v2 via /internal/documents/{id}/content
    st, body = http_json(ai_client, "PUT",
                         f"{AI_SERVICE_URL}/internal/documents/{doc_id}/content",
                         {
                             "expected_version": 1,
                             "content": "# Smoke v2\n\nUpdated during LD-404 smoke review flow",
                         },
                         headers=ai_headers(user_id))
    if st != 200:
        log(f" [DEBUG] PUT content failed: HTTP {st} body={body}")
    assert_true(st == 200, f"Edit document → v2 (HTTP {st})")
    ev_from = body.get("evidence_from_version") if isinstance(body, dict) else None
    assert_true(ev_from == 1, f"v2 evidence inherits v1 (evidence_from_version={ev_from})")

    # Save state
    state = {
        "run_id": RUN_ID,
        "username": username,
        "email": email,
        "password": password,
        "firstName": first_name,
        "lastName": last_name,
        "user_id": user_id,
        "job_id": job_id,
        "doc_id": doc_id,
        "expected_version": 2,
        "pre_restart_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_state_secure(state_file, state)
    log(f"State saved to secure file: {state_file}")
    return state


# ---------------------------------------------------------------------------
# Phase: post-restart
# ---------------------------------------------------------------------------
def run_post_restart(state_file: str) -> dict:
    log(f"=== POST-RESTART phase (state={state_file}) ===")
    log_endpoints()
    if not os.path.isfile(state_file):
        raise FileNotFoundError(f"State file not found: {state_file}")

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    email    = state["email"]
    password = state["password"]
    user_id  = state["user_id"]
    doc_id   = state["doc_id"]
    job_id   = state["job_id"]
    expected_version = state.get("expected_version", 2)

    jar = http.cookiejar.CookieJar()
    backend_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    ai_client = urllib.request.build_opener()

    # 1. Re-login (backend) — user phải tồn tại qua restart
    xcsrf = get_xsrf(backend_opener, jar)
    st, body = http_json(backend_opener, "POST", f"{BACKEND_URL}/api/auth/login",
                         {"email": email, "password": password},
                         headers={"X-XSRF-TOKEN": xcsrf})
    if st != 200:
        log(f" [DEBUG] Re-login failed: HTTP {st} body={body}")
    assert_true(st == 200, f"Re-login after restart (HTTP {st})")

    # 2. Session + identity
    st, me = http_json(backend_opener, "GET", f"{BACKEND_URL}/api/auth/me")
    assert_true(st == 200, f"Current user endpoint (HTTP {st})")
    assert_true(me.get("email") == email, "User email persisted")

    # 3. Document persisted
    st, doc = http_json(ai_client, "GET",
                        f"{AI_SERVICE_URL}/internal/documents/{doc_id}",
                        headers=ai_headers(user_id))
    assert_true(st == 200, f"Document persisted (HTTP {st})")

    # 4. Evidence v1 & v2 — kiểm tra NỘI DUNG thực sự, không chỉ HTTP 200 (P2)
    for ver in (1, expected_version):
        st, ev = http_json(ai_client, "GET",
                           f"{AI_SERVICE_URL}/internal/documents/{doc_id}/evidence?version={ver}",
                           headers=ai_headers(user_id))
        assert_true(st == 200, f"Evidence for v{ver} (HTTP {st})")
        assert_true(isinstance(ev, dict), f"Evidence v{ver} is JSON object")
        # P2: evidence phải giữ đúng job gốc — chứng minh grounding thực sự persist
        ev_job = ev.get("job_id")
        assert_true(ev_job == job_id,
                    f"Evidence v{ver} references originating job {job_id} (got: {ev_job!r})")
        # P2: evidence phải có nội dung (không phải stub rỗng)
        ev_len = len(json.dumps(ev))
        assert_true(ev_len > 50, f"Evidence v{ver} has substantive body (len={ev_len})")

    # 5. Review-evidence cho v2 (đảm bảo endpoint phục vụ được sau restart)
    st, rev = http_json(ai_client, "GET",
                        f"{AI_SERVICE_URL}/internal/documents/{doc_id}/review-evidence?version={expected_version}",
                        headers=ai_headers(user_id))
    assert_true(st == 200, f"Review-evidence v{expected_version} (HTTP {st})")
    assert_true(isinstance(rev, dict), "Review-evidence is JSON object")

    log("All post-restart checks passed")
    return {
        "phase": "post-restart",
        "status": "ok",
        "doc_id": doc_id,
        "job_id": job_id,
        "expected_version": expected_version,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="LD-404 Release Smoke Test")
    parser.add_argument("--phase", choices=["pre-restart", "post-restart"], required=True)
    parser.add_argument("--state-file", default=None,
                        help="Đường dẫn state. Mặc định: thư mục tạm 0o700.")
    parser.add_argument("--report-file", default=None)
    args = parser.parse_args()

    if not args.state_file:
        args.state_file = os.path.join(_create_secure_state_dir(), "smoke-state.json")

    state_dir = os.path.dirname(os.path.abspath(args.state_file)) or "."
    parts = state_dir.replace("\\", "/").split("/")
    if "artifacts" in parts:
        raise SystemExit(
            f"ERROR: state file must NOT live in artifacts/ "
            f"(would be committed to git). Got: {args.state_file}"
        )

    try:
        if args.phase == "pre-restart":
            result = run_pre_restart(args.state_file)
        else:
            result = run_post_restart(args.state_file)

        if args.report_file:
            os.makedirs(os.path.dirname(os.path.abspath(args.report_file)), exist_ok=True)
            with open(args.report_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
    except Exception as exc:
        print(f" [FAIL] {exc}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()