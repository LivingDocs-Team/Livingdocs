"""Documentation templates: choose, apply, manage, persist and follow the selected template."""
import json
import os
import re
import uuid

os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.generator import DocGenerator  # noqa: E402
from app.jobs import jobs, run_job  # noqa: E402
from app.models import GenerateRequest, TemplateIn  # noqa: E402
from app.templates import BUILT_IN, TemplateStore  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)
LABELS_VI = {"Overview": "Tổng quan", "Classes": "Các lớp", "Functions": "Các hàm",
             "API Endpoints": "API Endpoints"}

FILE = {
    "path": "shop/api.py", "language": "python",
    "classes": [{"name": "CartService", "docstring": "Cart rules.", "line_start": 3, "line_end": 9,
                 "methods": [{"name": "total", "signature": "def total(self, cart_id: int) -> float",
                              "parameters": [{"name": "cart_id", "type": "int"}],
                              "return_type": "float", "line_start": 5, "line_end": 7}]}],
    "functions": [{"name": "get_total", "parameters": [{"name": "cart_id", "type": "int"}],
                   "return_type": "float", "line_start": 12, "line_end": 13}],
    "endpoints": [{"http_method": "GET", "path": "/carts/{cart_id}/total", "handler": "get_total",
                   "line_start": 11}],
}


def name(prefix="Mẫu"):
    return f"{prefix} {uuid.uuid4().hex[:6]}"


def new_template(**over):
    body = {"name": name(), "description": "d", "instructions": "Viết ngắn gọn.",
            "sections": ["Overview", "Functions"], **over}
    r = client.post("/templates", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def generate(template_id, scope="file", files=(FILE,)):
    r = client.post("/generate", json={"scope": scope, "target": "shop", "template_id": template_id,
                                       "files": list(files)})
    assert r.status_code == 202, r.text
    job = client.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] == "completed", job
    return job, client.get(f"/jobs/{job['id']}/result").text


def headings(md):
    return re.findall(r"^## (.+)$", md, re.M)


# ---------- view available templates ----------

def test_list_shows_built_in_first_then_custom_by_name():
    b = new_template(name="zz " + name())
    a = new_template(name="aa " + name())
    ids = [t["id"] for t in client.get("/templates").json()]
    assert ids[:3] == ["default", "api-reference", "brief"]
    assert ids.index(a["id"]) < ids.index(b["id"])
    one = client.get(f"/templates/{a['id']}").json()
    assert one["name"] == a["name"] and one["built_in"] is False and one["created_at"]


def test_sections_endpoint_lists_allowed_sections():
    data = client.get("/templates/sections").json()
    assert data["sections"] == ["Overview", "Classes", "Functions", "API Endpoints"]
    assert data["documents"]["Classes"] == ["class", "method"]


# ---------- validation of managed templates ----------

@pytest.mark.parametrize("change, words", [
    ({"sections": ["Overview", "Changelog"]}, "unknown section"),
    ({"sections": ["Functions", "functions"]}, "duplicate section"),
    ({"sections": []}, "sections"),
    ({"name": "   "}, "blank"),
    ({"instructions": ""}, "instructions"),
    ({"name": "x" * 81}, "name"),
])
def test_invalid_templates_rejected(change, words):
    body = {"name": name(), "instructions": "x", "sections": ["Overview"], **change}
    r = client.post("/templates", json=body)
    assert r.status_code == 422 and words in r.text


def test_section_names_are_normalised():
    t = new_template(sections=[" api endpoints", "OVERVIEW"])
    assert t["sections"] == ["API Endpoints", "Overview"]


def test_names_are_unique_case_insensitive():
    t = new_template()
    assert client.post("/templates", json={"name": t["name"].upper(), "instructions": "x",
                                           "sections": ["Overview"]}).status_code == 409
    other = new_template()
    r = client.put(f"/templates/{other['id']}", json={**other, "name": t["name"]})
    assert r.status_code == 409
    assert client.post("/templates", json={"name": "standard TECHNICAL docs", "instructions": "x",
                                           "sections": ["Overview"]}).status_code == 409


def test_update_and_delete_custom_template():
    t = new_template()
    r = client.put(f"/templates/{t['id']}", json={"name": t["name"], "instructions": "Mới.",
                                                  "sections": ["Classes"]})
    assert r.status_code == 200
    u = r.json()
    assert u["sections"] == ["Classes"] and u["created_at"] == t["created_at"]
    assert u["updated_at"] >= t["updated_at"]
    assert client.delete(f"/templates/{t['id']}").status_code == 204
    assert client.get(f"/templates/{t['id']}").status_code == 404
    assert client.put(f"/templates/{t['id']}", json=u).status_code == 404
    assert client.delete(f"/templates/{t['id']}").status_code == 404


def test_built_in_templates_are_read_only():
    body = {"name": "x", "instructions": "x", "sections": ["Overview"]}
    for tid in ("default", "api-reference", "brief"):
        assert client.put(f"/templates/{tid}", json=body).status_code == 403
        assert client.delete(f"/templates/{tid}").status_code == 403


# ---------- persistence ----------

def test_custom_templates_survive_restart(tmp_path):
    path = tmp_path / "templates.json"
    store = TemplateStore(str(path))
    t = store.create(TemplateIn(name="Onboarding", instructions="x", sections=["Overview"]))
    gone = store.create(TemplateIn(name="Temp", instructions="x", sections=["Classes"]))
    store.delete(gone.id)
    assert json.loads(path.read_text(encoding="utf-8"))["templates"][0]["name"] == "Onboarding"

    again = TemplateStore(str(path))                       # "restart"
    assert again.get(t.id).name == "Onboarding" and again.get(gone.id) is None
    assert [x.id for x in again.list()][:3] == [b.id for b in BUILT_IN]


def test_file_cannot_override_built_in_templates(tmp_path):
    path = tmp_path / "templates.json"
    path.write_text(json.dumps({"templates": [{"id": "default", "name": "Hacked", "instructions": "x",
                                               "sections": ["Overview"]}]}), encoding="utf-8")
    assert TemplateStore(str(path)).get("default").name == BUILT_IN[0].name


def test_corrupt_file_is_kept_aside_and_store_starts_clean(tmp_path):
    path = tmp_path / "templates.json"
    path.write_text("{not json", encoding="utf-8")
    store = TemplateStore(str(path))
    assert [t.id for t in store.list()] == [b.id for b in BUILT_IN]
    assert not path.exists() and list(tmp_path.glob("templates.corrupt-*.json"))


def test_memory_only_store_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    TemplateStore(None).create(TemplateIn(name="x", instructions="x", sections=["Overview"]))
    assert list(tmp_path.iterdir()) == []


# ---------- generated documentation follows the selected template ----------

@pytest.mark.parametrize("tid", ["default", "api-reference", "brief"])
def test_built_in_templates_produce_exactly_their_sections(tid):
    tpl = client.get(f"/templates/{tid}").json()
    job, md = generate(tid)
    assert headings(md) == [LABELS_VI[s] for s in tpl["sections"]]
    assert job["template_id"] == tid and job["template_name"] == tpl["name"]
    assert job["template_sections"] == tpl["sections"]


def test_custom_template_order_is_followed():
    t = new_template(sections=["API Endpoints", "Functions", "Overview"])
    _, md = generate(t["id"])
    assert headings(md) == ["API Endpoints", "Các hàm", "Tổng quan"]
    assert "CartService" not in md                         # Classes not in the template


def test_report_only_scores_entities_the_template_documents():
    job, _ = generate("api-reference")
    rep = client.get(f"/jobs/{job['id']}/report").json()
    assert rep["template_id"] == "api-reference" and rep["template_name"] == "API reference"
    assert {e["kind"] for f in rep["files"] for e in f["entities"]} == {"endpoint"}


def test_repository_overview_names_the_template():
    second = {**FILE, "path": "shop/other.py"}
    _, md = generate("brief", scope="repository", files=(FILE, second))
    assert "Mẫu tài liệu: **Brief summary**" in md.split("---")[0]


class EndpointsOnlyModel:
    """Answers like a model that respected the template: only endpoints are described."""

    def __init__(self):
        self.prompts = []

    def complete(self, system, messages):
        self.prompts.append(messages[0]["content"])
        return json.dumps({"overview": "API giỏ hàng.", "overview_evidence": [],
                           "endpoints": [{"method": "GET", "path": "/carts/{cart_id}/total",
                                          "summary": "Tổng tiền.", "evidence": ["E4"],
                                          "confidence": 0.9}]})


def test_prompt_scopes_model_to_template_and_no_spurious_warnings():
    model = EndpointsOnlyModel()
    req = GenerateRequest.model_validate({"scope": "file", "target": "f", "files": [FILE],
                                          "template_id": "api-reference"})
    job = jobs.create(req)
    run_job(job.id, req, generator=DocGenerator(model, backoff_seconds=0))
    done = jobs.get(job.id)
    assert done.status.value == "completed" and done.template_name == "API reference"
    prompt = model.prompts[0]
    assert "sections, in order: Overview, API Endpoints" in prompt
    assert "Leave these empty (they are not part of the template): classes, functions" in prompt
    assert not [w for w in done.warnings if "no description" in w]   # classes are out of scope
    assert done.file_results[0].status.value == "generated"


def test_job_keeps_template_snapshot_after_template_changes():
    t = new_template(sections=["Functions"])
    snapshot = client.get(f"/templates/{t['id']}").json()
    req = GenerateRequest.model_validate({"scope": "file", "target": "f", "files": [FILE],
                                          "template_id": t["id"]})
    from app.models import Template
    tpl = Template.model_validate(snapshot)
    job = jobs.create(req, tpl)
    client.delete(f"/templates/{t['id']}")                  # deleted while the job is queued
    run_job(job.id, req, template=tpl)
    done = jobs.get(job.id)
    assert done.status.value == "completed" and headings(done.result) == ["Các hàm"]
