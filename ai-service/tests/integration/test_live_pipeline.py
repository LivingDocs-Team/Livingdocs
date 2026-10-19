"""LD-390: tests against running services. Skipped unless the URLs / key are set.

Cross-service pipeline (CI job `ai-service-integration`, or locally):
    ANALYZER_URL=http://localhost:8000 AI_SERVICE_URL=http://localhost:8001 \
        python -m pytest -m live -v

Real Claude API (costs a few requests, run by hand):
    RUN_LLM_TESTS=1 ANTHROPIC_API_KEY=... python -m pytest -m llm -v
"""
import os
import pathlib
import time

import httpx
import pytest

from conftest import FIXTURES, live_url

ANALYZER = live_url("ANALYZER_URL")
AI = live_url("AI_SERVICE_URL")
API_KEY = os.getenv("ANTHROPIC_API_KEY")  # read now: other test modules drop it at import
FILES = ["cart_service.py", "routes.py", "OrderController.java", "broken.py", "empty.py", "widget.js"]

live = pytest.mark.skipif(not (ANALYZER and AI), reason="set ANALYZER_URL and AI_SERVICE_URL")


LANG = {".py": "python", ".java": "java"}


def analyzer_body():
    """The body github-integration sends (AnalysisInput: scope, target, files with content, see
    repository-sync-contract.md §5) plus `file_paths` so the older LD-328 analyzer, which reads
    from disk relative to its working directory (= fixtures/), gets the same files."""
    paths = [f"shop/{n}" for n in FILES]
    files = [{"path": p, "content": (FIXTURES / p).read_text(encoding="utf-8")} for p in paths]
    for f in files:
        lang = LANG.get(pathlib.Path(f["path"]).suffix)
        if lang:
            f["language"] = lang
    return {"scope": "repository", "target": "acme/shop", "files": files, "file_paths": paths}


def wait_for(job_id, timeout=60):
    deadline = time.monotonic() + timeout
    while True:
        job = httpx.get(f"{AI}/jobs/{job_id}", timeout=10).json()
        if job["status"] in ("completed", "failed") or time.monotonic() > deadline:
            return job
        time.sleep(0.2)


@pytest.mark.live
@live
def test_services_are_up():
    assert httpx.get(f"{AI}/health", timeout=10).json()["status"] == "ok"
    assert httpx.get(f"{ANALYZER}/openapi.json", timeout=10).status_code == 200


@pytest.mark.live
@live
def test_analyzer_to_ai_service_pipeline():
    a = httpx.post(f"{ANALYZER}/api/v1/analyze-repo", json=analyzer_body(), timeout=30)
    assert a.status_code == 200, a.text
    analysis = a.json()
    assert {f["path"] for f in analysis["files"]} == {f"shop/{n}" for n in FILES}
    assert analysis["target"] == "acme/shop", "analyzer must keep the repository name"

    g = httpx.post(f"{AI}/generate", json=analysis, timeout=30)      # forwarded unchanged
    assert g.status_code == 202, g.text
    job = wait_for(g.json()["id"])
    assert job["status"] == "completed", job
    st = {fr["path"]: fr["status"] for fr in job["file_results"]}
    assert st["shop/broken.py"] == st["shop/empty.py"] == st["shop/widget.js"] == "skipped"
    assert {st[f"shop/{n}"] for n in FILES[:3]} <= {"generated", "offline", "fallback"}

    md = httpx.get(f"{AI}/jobs/{job['id']}/result", timeout=10).text
    for name in ("CartService", "get_cart_total", "GET /carts/{cart_id}/total", "OrderController"):
        assert name in md
    rep = httpx.get(f"{AI}/jobs/{job['id']}/report", timeout=10).json()
    cart = next(f for f in rep["files"] if f["path"] == "shop/cart_service.py")
    total = next(e for e in cart["entities"] if e["name"] == "CartService.total")
    assert total["evidence"][0]["line_start"] is not None, "line numbers lost between services"


@pytest.mark.llm
@pytest.mark.skipif(not (os.getenv("RUN_LLM_TESTS") == "1" and API_KEY),
                    reason="set RUN_LLM_TESTS=1 and ANTHROPIC_API_KEY")
def test_real_claude_output_is_valid_and_grounded(analysis, shop_readme, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)

    client = TestClient(app)
    files = [f for f in analysis["files"] if f["path"] in ("shop/cart_service.py", "shop/routes.py")]
    r = client.post("/generate", json={"scope": "module", "target": "shop", "files": files,
                                       "context": [shop_readme]})
    job = client.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] == "completed", job
    assert all(fr["status"] == "generated" for fr in job["file_results"]), job["warnings"]
    assert not [w for w in job["warnings"] if "invalid AI output" in w or "citations" in w]
    rep = client.get(f"/jobs/{job['id']}/report").json()
    ents = [e for f in rep["files"] for e in f["entities"]]
    assert ents and all(e["factors"].get("ai_described") == 1.0 for e in ents)
    assert sum(e["factors"]["grounding"] > 0 for e in ents) >= len(ents) * 0.8
    assert job["confidence"] >= 0.5
