"""LD-390: integration tests for the AI service.

The analyzer output (real LD-328 output, see conftest.py) goes through the public HTTP API exactly
as the pipeline sends it: POST /generate -> GET /jobs/{id} -> /result -> /report.
The generator runs offline or with a fake model; no network is used.
"""
import pytest
from fastapi.testclient import TestClient

from conftest import PromptDrivenModel
from main import app

client = TestClient(app)

OK_FILES = {"shop/cart_service.py", "shop/routes.py", "shop/OrderController.java"}
SKIPPED = {"shop/broken.py": "SyntaxError", "shop/empty.py": "rỗng", "shop/widget.js": ".js"}


def run(body, expect=202):
    """Submit a job and return the finished job (BackgroundTasks run inside TestClient)."""
    r = client.post("/generate", json=body)
    assert r.status_code == expect, r.text
    if expect != 202:
        return r
    job = client.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] in ("completed", "failed"), job
    return job


def result(job):
    r = client.get(f"/jobs/{job['id']}/result")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    return r.text


def report(job):
    r = client.get(f"/jobs/{job['id']}/report")
    assert r.status_code == 200, r.text
    return r.json()


def entity(rep, path, name):
    f = next(f for f in rep["files"] if f["path"] == path)
    return next(e for e in f["entities"] if e["name"] == name)


# ---------- 1. analyzer output is accepted as-is ----------

def test_analyzer_response_is_accepted_unchanged(analysis):
    job = run(analysis)
    assert job["status"] == "completed"
    assert job["target"] == "acme/shop" and job["files_total"] == 6 and job["files_done"] == 6
    assert job["progress"] == 1.0


def test_file_statuses_follow_analyzer_statuses(analysis):
    job = run(analysis)
    statuses = {fr["path"]: fr["status"] for fr in job["file_results"]}
    assert {p for p, s in statuses.items() if s == "offline"} == OK_FILES
    assert {p for p, s in statuses.items() if s == "skipped"} == set(SKIPPED)
    for path, reason in SKIPPED.items():
        msg = next(fr["message"] for fr in job["file_results"] if fr["path"] == path)
        assert reason in msg                                # analyzer error is passed through
        assert any(w.startswith(path) for w in job["warnings"])


def test_markdown_covers_every_analyzed_entity(analysis):
    md = result(run(analysis))
    for f in analysis["files"]:
        if f["status"] != "ok":
            assert f"`{f['path']}`" in md.split("---")[0]  # listed under skipped files
            continue
        assert f"# {f['path']}" in md
        for c in f["classes"]:
            assert f"`{c['name']}`" in md
            for m in c["methods"]:
                assert f"`{m['name']}`" in md
        for fn in f["functions"]:
            assert f"`{fn['name']}`" in md
        for e in f["endpoints"]:
            assert f"`{e['http_method']} {e['path']}`" in md


def test_analyzer_line_numbers_become_evidence_locations(analysis):
    """The analyzer sends lineno/end_lineno; evidence must point at file:start-end."""
    job = run(analysis)
    rep = report(job)
    m = analysis["files"][0]["classes"][1]["methods"][2]          # CartService.total
    ev = entity(rep, "shop/cart_service.py", "CartService.total")["evidence"][0]
    assert ev["kind"] == "source"
    assert (ev["line_start"], ev["line_end"]) == (m["lineno"], m["end_lineno"])
    assert f"`shop/cart_service.py:{m['lineno']}-{m['end_lineno']}`" in result(job)


def test_report_matches_job_and_lists_every_entity(analysis):
    job = run(analysis)
    rep = report(job)
    assert rep["job_id"] == job["id"] and rep["confidence"] == job["confidence"]
    by_path = {f["path"]: f for f in rep["files"]}
    assert set(by_path) == {f["path"] for f in analysis["files"]}
    routes = by_path["shop/routes.py"]
    names = {e["name"] for e in routes["entities"]}
    assert names == {"get_cart_total", "add_cart_item",
                     "GET /carts/{cart_id}/total", "POST /carts/{cart_id}/items"}
    for f in rep["files"]:
        for e in f["entities"]:
            assert 0 <= e["confidence"] <= 1 and e["level"] in ("high", "medium", "low")
    fr_conf = {fr["path"]: fr["confidence"] for fr in job["file_results"]}
    assert all(fr_conf[p] == by_path[p]["confidence"] for p in OK_FILES)


def test_offline_confidence_is_capped(analysis):
    rep = report(run(analysis))
    assert rep["confidence"] <= 0.6
    assert all(e["confidence"] <= 0.6 for f in rep["files"] for e in f["entities"])


# ---------- 2. AI mode end to end (fake model) ----------

def test_ai_mode_end_to_end_with_context(analysis, shop_readme, use_model):
    model = use_model(PromptDrivenModel())
    job = run({**analysis, "context": [shop_readme]})
    assert job["status"] == "completed"
    assert {fr["path"] for fr in job["file_results"] if fr["status"] == "generated"} == OK_FILES
    assert len(model.prompts) == len(OK_FILES)            # skipped files never reach the model
    assert job["confidence_level"] == "high"

    rep = report(job)
    tot = entity(rep, "shop/cart_service.py", "CartService.total")
    assert tot["evidence"][0]["kind"] == "source" and tot["evidence"][0]["line_start"] == 27
    assert tot["factors"]["grounding"] == 1.0 and tot["confidence"] >= 0.75

    md = result(job)
    assert "Mô tả CartService.total." in md and "Độ tin cậy chung" in md
    # routes.py imports CartService: retrieval must give the model related code + the README
    routes_prompt = next(p for p in model.prompts if "file 'shop/routes.py'" in p)
    assert "Related code from other files" in routes_prompt and "CartService" in routes_prompt
    assert "Existing documentation" in routes_prompt and "VAT" in routes_prompt
    assert "## Nguồn tham chiếu" in md


def test_api_errors_fall_back_per_file_without_failing_job(analysis, use_model):
    use_model(PromptDrivenModel(fail_paths={"shop/routes.py"},
                                garbage_paths={"shop/OrderController.java"}))
    job = run(analysis)
    st = {fr["path"]: fr["status"] for fr in job["file_results"]}
    assert st["shop/cart_service.py"] == "generated"
    assert st["shop/routes.py"] == "fallback" and st["shop/OrderController.java"] == "fallback"
    assert job["status"] == "completed"
    assert any("timeout" in w for w in job["warnings"])
    assert any("invalid AI output" in w for w in job["warnings"])
    md = result(job)
    assert "`get_cart_total`" in md and "`countOrders`" in md   # still documented from analysis


def test_english_output(analysis, use_model):
    model = use_model(PromptDrivenModel())
    job = run({**analysis, "output_language": "en"})
    assert all("Language for all descriptions: English" in p for p in model.prompts)
    md = result(job)
    assert "## Overview" in md and "Overall confidence" in md


# ---------- 3. templates through the API ----------

def test_custom_template_controls_sections(analysis):
    r = client.post("/templates", json={"name": "API only", "sections": ["API Endpoints", "Overview"],
                                        "instructions": "Short."})
    assert r.status_code == 201
    tpl = r.json()["id"]
    try:
        md = result(run({**analysis, "template_id": tpl}))
        routes = md[md.index("# shop/routes.py"):]
        assert routes.index("## API Endpoints") < routes.index("## Tổng quan")
        assert "## Các hàm" not in md and "## Các lớp" not in md
    finally:
        assert client.delete(f"/templates/{tpl}").status_code == 204
    run({**analysis, "template_id": tpl}, expect=404)


# ---------- 4. job lifecycle and errors ----------

def test_job_fails_when_no_file_can_be_documented(analysis):
    bad = {**analysis, "files": [f for f in analysis["files"] if f["status"] != "ok"]}
    job = run(bad)
    assert job["status"] == "failed" and "No documentation" in job["error"]
    assert len(job["file_results"]) == 3
    assert client.get(f"/jobs/{job['id']}/result").status_code == 409
    assert client.get(f"/jobs/{job['id']}/report").status_code == 409


def test_single_file_scope_returns_only_that_file(analysis):
    f = analysis["files"][1]
    md = result(run({"scope": "file", "target": f["path"], "files": [f]}))
    assert md.startswith("# shop/routes.py") and "Danh sách file" not in md


@pytest.mark.parametrize("change, field", [
    ({"files": []}, "files"),
    ({"scope": "galaxy"}, "scope"),
    ({"output_language": "fr"}, "output_language"),
])
def test_invalid_requests_are_rejected(analysis, change, field):
    r = run({**analysis, **change}, expect=422)
    assert field in r.text


def test_duplicate_paths_rejected(analysis):
    files = analysis["files"]
    assert run({**analysis, "files": files + files[:1]}, expect=422).status_code == 422


def test_unknown_job_is_404():
    for suffix in ("", "/result", "/report"):
        assert client.get(f"/jobs/does-not-exist{suffix}").status_code == 404


def test_jobs_are_isolated_and_listed(analysis):
    a = run(analysis)
    b = run({**analysis, "target": "acme/other", "files": analysis["files"][:1]})
    assert a["id"] != b["id"] and b["files_total"] == 1
    ids = [j["id"] for j in client.get("/jobs").json()]
    assert ids.index(b["id"]) < ids.index(a["id"])               # newest first
    assert "acme/other" in result(b) and "routes.py" not in result(b)


def test_health_reports_generator_mode():
    assert client.get("/health").json() == {"status": "ok", "generator": "offline"}
