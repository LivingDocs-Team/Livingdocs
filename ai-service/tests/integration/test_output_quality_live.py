"""Output quality: real Code Analyzer (LD-328) -> AI Service, checked against the source files.

Runs in CI job `ai-service-integration` (both services started) or locally:
    ANALYZER_URL=http://localhost:8000 AI_SERVICE_URL=http://localhost:8001 \
        python -m pytest -m live -v tests/integration/test_output_quality_live.py

Tests marked `xfail` record analyzer gaps found during the check (ids A1..A11 in
`tests/integration/QUALITY.md`). They do not fail the build; when the analyzer is fixed they
start passing (shown as XPASS) and the marker can be removed.
"""
import ast
import pathlib
import re
import time

import httpx
import pytest

from conftest import FIXTURES, live_url

ANALYZER = live_url("ANALYZER_URL")
AI = live_url("AI_SERVICE_URL")
Q = FIXTURES / "quality"
FILES = ["shop_api.py", "models_ext.py", "bom.py", "OrderApi.java", "OrderDto.java"]
LANG = {".py": "python", ".java": "java"}

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not (ANALYZER and AI), reason="set ANALYZER_URL and AI_SERVICE_URL")]


def src(name: str) -> str:
    return (Q / name).read_text(encoding="utf-8")


def analyze(files, lang_override=None):
    body = {"scope": "repository", "target": "acme/quality", "files": [
        {"path": f"quality/{n}", "content": c,
         "language": lang_override or LANG[pathlib.Path(n).suffix]} for n, c in files]}
    r = httpx.post(f"{ANALYZER}/api/v1/analyze-repo", json=body, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def analysis():
    return analyze([(n, src(n)) for n in FILES])


def file_of(analysis, name):
    return next(f for f in analysis["files"] if f["path"] == f"quality/{name}")


def endpoints(f):
    return {(e["http_method"], e["path"]) for e in f["endpoints"]}


# ---------- what must stay correct ----------

def test_python_entities_and_lines_match_source(analysis):
    f = file_of(analysis, "shop_api.py")
    tree = ast.parse(src("shop_api.py"))
    lines = src("shop_api.py").splitlines()
    want_funcs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    want_classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert [fn["name"] for fn in f["functions"]] == want_funcs
    assert [c["name"] for c in f["classes"]] == want_classes
    for fn in f["functions"] + [m for c in f["classes"] for m in c["methods"]]:
        assert re.match(rf"\s*(async\s+)?def {fn['name']}\b", lines[fn["lineno"] - 1]), fn["name"]
        assert fn["end_lineno"] >= fn["lineno"] and fn["source"]
    assert f["functions"][-1]["parameters"] == [
        {"name": "price", "type": "float", "default": None, "description": None},
        {"name": "rate", "type": "float", "default": "0.1", "description": None}]


def test_fastapi_endpoint_found(analysis):
    # the path may carry the router prefix once A3 is fixed
    found = endpoints(file_of(analysis, "shop_api.py"))
    assert any(m == "GET" and p.endswith("/items/{name}") for m, p in found)


def test_java_methods_and_lines_match_source(analysis):
    f = file_of(analysis, "OrderApi.java")
    assert f["status"] == "ok"
    lines = src("OrderApi.java").splitlines()
    api = next(c for c in f["classes"] if c["name"] == "OrderApi")
    assert [m["name"] for m in api["methods"]] == ["get", "get", "create"]
    for m in api["methods"]:
        assert f" {m['name']}(" in lines[m["lineno"] - 1]


# ---------- analyzer gaps (LD-328, see QUALITY.md) ----------

gap = lambda code, why: pytest.mark.xfail(reason=f"{code}: {why}", strict=False)  # noqa: E731


@gap("A1", "javalang only parses Java 8: records / text blocks are 'invalid' with an empty message")
def test_java_record_is_parsed(analysis):
    f = file_of(analysis, "OrderDto.java")
    assert f["status"] == "ok" and f["classes"][0]["name"] == "OrderDto"


@gap("A2", "Spring @GetMapping/@PostMapping/@RequestMapping are not extracted as endpoints")
def test_spring_endpoints(analysis):
    assert endpoints(file_of(analysis, "OrderApi.java")) == {("GET", "/orders/{id}"), ("POST", "/orders")}


@gap("A3", "Flask @app.route without methods (default GET), path= keyword and APIRouter prefix")
def test_python_route_variants(analysis):
    assert endpoints(file_of(analysis, "shop_api.py")) == {
        ("GET", "/ping"), ("GET", "/api/v1/items/{name}"), ("POST", "/api/v1/items")}


@gap("A4", "interfaces, enums and constructors are not extracted")
def test_java_interface_enum_constructor(analysis):
    f = file_of(analysis, "OrderApi.java")
    names = {c["name"] for c in f["classes"]}
    assert {"OrderService", "OrderStatus"} <= names
    api = next(c for c in f["classes"] if c["name"] == "OrderApi")
    assert "OrderApi" in [m["name"] for m in api["methods"]]


@gap("A5", "Javadoc is not read into docstring")
def test_javadoc(analysis):
    f = file_of(analysis, "OrderApi.java")
    api = next(c for c in f["classes"] if c["name"] == "OrderApi")
    assert api["docstring"] and api["methods"][0]["docstring"]


@gap("A6", "class line_start/line_end (lineno/end_lineno) not sent -> evidence points only to the file")
def test_class_lines(analysis):
    for c in file_of(analysis, "shop_api.py")["classes"]:
        assert c.get("lineno") or c.get("line_start")


@gap("A7", "bases written as attributes (models.Model, typing.Generic[T]) are dropped")
def test_attribute_bases(analysis):
    classes = {c["name"]: c["bases"] for c in file_of(analysis, "models_ext.py")["classes"]}
    assert classes == {"Order": ["models.Model"], "Box": ["typing.Generic[T]"]}


@gap("A8", "class fields (pydantic / dataclass / record components) are not extracted")
def test_class_fields(analysis):
    item = next(c for c in file_of(analysis, "shop_api.py")["classes"] if c["name"] == "Item")
    assert [x["name"] for x in item.get("fields", [])] == ["name", "price"]


@gap("A9", "module is never filled in")
def test_module(analysis):
    assert file_of(analysis, "shop_api.py")["module"] == "quality.shop_api"


@gap("A10", "a UTF-8 BOM (files saved on Windows) makes the file 'invalid'")
def test_bom(analysis):
    f = file_of(analysis, "bom.py")
    assert f["status"] == "ok" and f["functions"][0]["name"] == "saved_on_windows"


@gap("A11", "language is case sensitive: 'Python' -> unsupported")
def test_language_case():
    f = analyze([("shop_api.py", src("shop_api.py"))], lang_override="Python")["files"][0]
    assert f["status"] == "ok"


@gap("A12", "duplicate paths are passed through; ai-service then rejects the whole request (422)")
def test_duplicate_paths():
    files = analyze([("bom.py", "x = 1\n"), ("bom.py", "y = 2\n")])["files"]
    assert len(files) == 1 or files[1].get("status") == "invalid"


# ---------- end to end: analyzer output -> documentation ----------

def wait_for(job_id, timeout=60):
    deadline = time.monotonic() + timeout
    while True:
        job = httpx.get(f"{AI}/jobs/{job_id}", timeout=10).json()
        if job["status"] in ("completed", "failed") or time.monotonic() > deadline:
            return job
        time.sleep(0.2)


@pytest.fixture(scope="module")
def generated(analysis):
    g = httpx.post(f"{AI}/generate", json={**analysis, "output_language": "en"}, timeout=30)
    assert g.status_code == 202, g.text
    job = wait_for(g.json()["id"])
    md = httpx.get(f"{AI}/jobs/{job['id']}/result", timeout=10).text
    rep = httpx.get(f"{AI}/jobs/{job['id']}/report", timeout=10).json()
    return job, md, rep


def test_every_entity_is_documented(analysis, generated):
    job, md, _ = generated
    assert job["status"] == "completed"
    for f in analysis["files"]:
        if f["status"] != "ok":
            continue
        for c in f["classes"]:
            assert f"`{c['name']}`" in md
            for m in c["methods"]:
                assert f"`{m['name']}" in md, f"{f['path']}: {c['name']}.{m['name']}"
        for fn in f["functions"]:
            assert f"`{fn['name']}`" in md
        for e in f["endpoints"]:
            assert f"`{e['http_method']} {e['path']}`" in md


def test_skipped_files_have_a_reason(analysis, generated):
    job, md, _ = generated
    for fr in job["file_results"]:
        if fr["status"] == "skipped":
            reason = fr["message"] or ""
            assert reason.strip(" :") and not reason.endswith(": "), fr
            assert fr["path"] in md


def test_evidence_points_at_the_entity(generated):
    _, _, rep = generated
    for fr in rep["files"]:
        ids = []
        for e in fr["entities"]:
            own = [ev for ev in e["evidence"] if ev["kind"] == "source"]
            assert own, e["name"]
            ids.append(own[0]["id"])
            ev = own[0]
            if ev.get("line_start") and e["kind"] in ("method", "function"):
                lines = src(fr["path"].split("/", 1)[1]).splitlines()
                assert 1 <= ev["line_start"] <= (ev.get("line_end") or ev["line_start"]) <= len(lines)
                code = "\n".join(lines[ev["line_start"] - 1:ev.get("line_end") or ev["line_start"]])
                bare = e["name"].split(".")[-1].split("(")[0].split("#")[0]
                assert bare in code, f"{fr['path']}: {e['name']} -> {ev}"
        assert len(ids) == len(set(ids)), f"{fr['path']}: two entities share one evidence id"


def test_offline_doc_uses_docstrings(generated):
    _, md, _ = generated
    assert "| `name` | str | - | Item name. |" in md                   # Args section of get_item
    assert "The stored item." in md                                     # Returns section
    assert "Args:" not in md
