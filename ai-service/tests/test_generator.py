"""Tests for LD-340: structured AI output, prompt, validation and error handling."""
import json
import os

os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.doc_schema import InvalidAIOutput, parse_file_doc  # noqa: E402
from app.generator import DocGenerator  # noqa: E402
from app.jobs import jobs, run_job  # noqa: E402
from app.models import FileAnalysis, FileResultStatus, GenerateRequest  # noqa: E402
from app.prompts import MAX_SOURCE_CHARS, build_file_prompt  # noqa: E402
from app.templates import templates  # noqa: E402
from main import app  # noqa: E402

TPL = templates.get("default")

FILE = FileAnalysis.model_validate({
    "path": "src/cart.py", "language": "python",
    "classes": [{"name": "Cart", "methods": [{
        "name": "add_item",
        "parameters": [{"name": "product_id", "type": "int"}, {"name": "qty", "type": "int"}],
        "return_type": "None"}]}],
    "functions": [{"name": "apply_discount", "parameters": [{"name": "amount", "type": "float"}],
                   "return_type": "float", "docstring": "Apply a discount."}],
    "endpoints": [{"http_method": "get", "path": "/cart", "handler": "get_cart"}],
})

GOOD = {
    "overview": "Quản lý giỏ hàng.",
    "classes": [{"name": "Cart", "summary": "Giỏ hàng của người dùng.", "methods": [{
        "name": "add_item", "summary": "Thêm sản phẩm vào giỏ.",
        "parameters": [{"name": "product_id", "description": "Mã sản phẩm."},
                       {"name": "qty", "description": "Số lượng."}],
        "returns": "Không trả về giá trị."}]}],
    "functions": [{"name": "apply_discount", "summary": "Tính giá sau giảm.",
                   "parameters": [{"name": "amount", "description": "Số tiền gốc."}],
                   "returns": "Số tiền sau giảm."}],
    "endpoints": [{"method": "GET", "path": "/cart", "summary": "Lấy giỏ hàng."}],
}


class FakeClient:
    """Returns queued responses; an Exception instance in the queue is raised."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, system, messages):
        self.calls.append(messages)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def gen(*responses, attempts=3):
    client = FakeClient(*responses)
    return DocGenerator(client, max_attempts=attempts, backoff_seconds=0), client


# ---------- parsing / validation ----------

def test_parse_accepts_code_fences_and_surrounding_text():
    doc = parse_file_doc("Here it is:\n```json\n" + json.dumps(GOOD) + "\n```")
    assert doc.classes[0].name == "Cart"


@pytest.mark.parametrize("bad", ["", "   ", "not json", "[1, 2]", '{"classes": "oops"}',
                                 '{"overview": "x",'])
def test_parse_rejects_invalid_output(bad):
    with pytest.raises(InvalidAIOutput):
        parse_file_doc(bad)


# ---------- prompt ----------

def test_prompt_contains_analysis_language_and_schema():
    p = build_file_prompt(FILE, TPL, "vi")
    assert "Vietnamese" in p and '"overview"' in p and "apply_discount" in p
    assert TPL.instructions in p


def test_prompt_truncates_long_source():
    f = FileAnalysis.model_validate({"path": "a.py", "functions": [
        {"name": "big", "source": "x = 1\n" * 2000}]})
    p = build_file_prompt(f, TPL, "en")
    assert "(truncated)" in p and len(p) < MAX_SOURCE_CHARS + 5000


# ---------- success ----------

def test_ai_output_is_rendered_with_fixed_structure():
    g, _ = gen(json.dumps(GOOD))
    r = g.document_file(FILE, TPL, "vi")
    assert r.status == FileResultStatus.generated and r.warnings == []
    md = r.markdown
    order = [md.index(h) for h in ["## Tổng quan", "## Các lớp", "## Các hàm", "## API Endpoints"]]
    assert order == sorted(order)
    for text in ["Giỏ hàng của người dùng.", "Mã sản phẩm.", "Số tiền sau giảm.",
                 "### `GET /cart`", "Lấy giỏ hàng."]:
        assert text in md


def test_same_structure_for_ai_and_fallback():
    g_ai, _ = gen(json.dumps(GOOD))
    g_bad, _ = gen("x", "x", "x")
    heads = lambda md: [ln for ln in md.splitlines() if ln.startswith("#")]  # noqa: E731
    assert heads(g_ai.document_file(FILE, TPL, "vi").markdown) == \
        heads(g_bad.document_file(FILE, TPL, "vi").markdown)


def test_invented_entities_are_ignored_and_missing_ones_reported():
    data = json.loads(json.dumps(GOOD))
    data["functions"] = [{"name": "made_up", "summary": "Không tồn tại."}]
    g, _ = gen(json.dumps(data))
    r = g.document_file(FILE, TPL, "vi")
    assert "made_up" not in r.markdown
    assert "Apply a discount." in r.markdown   # falls back to docstring
    assert any("made_up" in w for w in r.warnings)
    assert any("apply_discount" in w for w in r.warnings)


# ---------- error handling ----------

def test_invalid_json_is_retried_with_repair_prompt():
    g, client = gen("sorry, I cannot", json.dumps(GOOD))
    r = g.document_file(FILE, TPL, "vi")
    assert r.status == FileResultStatus.generated
    assert len(client.calls) == 2
    assert "could not be used" in client.calls[1][-1]["content"]


def test_api_error_is_retried():
    g, client = gen(TimeoutError("timeout"), json.dumps(GOOD))
    r = g.document_file(FILE, TPL, "vi")
    assert r.status == FileResultStatus.generated and len(client.calls) == 2
    assert any("timeout" in w for w in r.warnings)


def test_fallback_after_all_attempts_fail():
    g, client = gen(RuntimeError("500"), "bad", '{"classes": 1}')
    r = g.document_file(FILE, TPL, "vi")
    assert r.status == FileResultStatus.fallback and len(client.calls) == 3
    assert "Apply a discount." in r.markdown and "add_item" in r.markdown
    assert any("analysis data only" in w for w in r.warnings)


def test_file_without_entities_does_not_call_ai():
    g, client = gen()
    r = g.document_file(FileAnalysis(path="empty_module.py"), TPL, "en")
    assert client.calls == [] and "No classes, functions or endpoints" in r.markdown


# ---------- job level ----------

def _run(payload, generator):
    req = GenerateRequest.model_validate(payload)
    job = jobs.create(req)
    run_job(job.id, req, generator=generator)
    return jobs.get(job.id)


def test_job_skips_files_the_analyzer_could_not_process():
    g, _ = gen(json.dumps(GOOD))
    job = _run({"scope": "repository", "target": "demo", "files": [
        FILE.model_dump(),
        {"path": "bad.py", "status": "invalid", "error": "SyntaxError line 3"},
        {"path": "x.rb", "status": "unsupported"},
    ]}, g)
    assert job.status.value == "completed"
    assert [r.status.value for r in job.file_results] == ["generated", "skipped", "skipped"]
    assert "SyntaxError line 3" in job.result
    assert len(job.warnings) == 2


def test_job_fails_when_no_file_can_be_documented():
    job = _run({"scope": "repository", "target": "demo",
                "files": [{"path": "a.py", "status": "empty"}]}, DocGenerator(None))
    assert job.status.value == "failed" and "No documentation" in job.error


def test_one_crashing_file_does_not_stop_the_job():
    class Boom(DocGenerator):
        def document_file(self, f, tpl, lang, retrieved=None):
            if f.path == "crash.py":
                raise KeyError("boom")
            return super().document_file(f, tpl, lang, retrieved)

    job = _run({"scope": "module", "target": "m", "files": [
        {"path": "crash.py"}, FILE.model_dump()]}, Boom(None))
    assert job.status.value == "completed"
    assert [r.status.value for r in job.file_results] == ["failed", "offline"]


# ---------- input validation (API) ----------

client = TestClient(app)


@pytest.mark.parametrize("payload", [
    {"scope": "file", "target": "x", "files": []},
    {"scope": "file", "target": "x", "files": [{"path": ""}]},
    {"scope": "file", "target": "x", "files": [{"path": "a.py", "functions": [{"name": ""}]}]},
    {"scope": "file", "target": "x", "files": [{"path": "a.py", "endpoints": [
        {"http_method": "FETCH", "path": "/a"}]}]},
    {"scope": "file", "target": "x", "output_language": "fr", "files": [{"path": "a.py"}]},
    {"scope": "module", "target": "x", "files": [{"path": "a.py"}, {"path": "a.py"}]},
    {"scope": "file", "target": "x"},
])
def test_invalid_input_returns_422(payload):
    assert client.post("/generate", json=payload).status_code == 422
