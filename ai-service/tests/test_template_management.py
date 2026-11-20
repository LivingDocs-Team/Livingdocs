"""LD-228: test documentation template management (LD-224 – LD-227) end to end.

Each test is one case TM-xx of Docs/Linh/LD-228-Kiem-thu-quan-ly-mau.md. They complement
test_templates.py (LD-97 – LD-100) and test_template_versions.py (LD-227) with boundary values,
whole life cycles, restarts and concurrent edits.
"""
import itertools
import os
import threading
import uuid

os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.models import SECTION_NAMES, TemplateIn  # noqa: E402
from app.templates import TemplateNameTaken, TemplateStore  # noqa: E402
from main import app  # noqa: E402
from test_templates import FILE, LABELS_VI, headings  # noqa: E402

client = TestClient(app)


def body(**over):
    return {"name": f"TM {uuid.uuid4().hex[:8]}", "description": "", "instructions": "Ngắn gọn.",
            "sections": ["Overview"], **over}


def create(**over):
    r = client.post("/templates", json=body(**over))
    assert r.status_code == 201, r.text
    return r.json()


def put(tid, **fields):
    r = client.put(f"/templates/{tid}", json=fields)
    assert r.status_code == 200, r.text
    return r.json()


def generate_with(tid, version=None):
    req = {"scope": "file", "target": "shop", "template_id": tid, "files": [FILE]}
    if version is not None:
        req["template_version"] = version
    r = client.post("/generate", json=req)
    assert r.status_code == 202, r.text
    job = client.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] == "completed", job
    return job, headings(client.get(f"/jobs/{job['id']}/result").text)


# ---------- TM-01 .. TM-03: list, create / edit, structure (LD-224 – LD-226) ----------

def test_tm01_list_has_every_field_a_screen_needs():
    t = create(description="Mô tả")
    listed = next(x for x in client.get("/templates").json() if x["id"] == t["id"])
    assert set(listed) >= {"id", "name", "description", "instructions", "sections", "built_in",
                           "version", "created_at", "updated_at"}
    assert listed["built_in"] is False and listed["version"] == 1
    assert [x["id"] for x in client.get("/templates").json()[:3]] == ["default", "api-reference", "brief"]


@pytest.mark.parametrize("field, ok, too_long", [
    ("name", 80, 81), ("description", 300, 301), ("instructions", 4000, 4001)])
def test_tm02_length_limits_are_exact(field, ok, too_long):
    assert client.post("/templates", json=body(**{field: "a" * ok})).status_code == 201
    r = client.post("/templates", json=body(**{field: "a" * too_long}))
    assert r.status_code == 422 and field in r.text


def test_tm02b_edit_is_validated_like_create_and_trims_text():
    t = create()
    assert client.put(f"/templates/{t['id']}", json=body(sections=["Nope"])).status_code == 422
    got = put(t["id"], **body(name="  Tên có khoảng trắng  ", description="  mô tả  ",
                              instructions="  Viết.  "))
    assert (got["name"], got["description"], got["instructions"]) == ("Tên có khoảng trắng", "mô tả", "Viết.")
    assert client.put("/templates/nope", json=body()).status_code == 404


@pytest.mark.parametrize("sections", [list(p) for n in (1, 2, 4)
                                      for p in itertools.islice(itertools.permutations(SECTION_NAMES, n), 3)])
def test_tm03_any_order_of_any_sections_is_the_document_structure(sections):
    t = create(sections=sections)
    _, got = generate_with(t["id"])
    assert got == [LABELS_VI[s] for s in sections]


# ---------- TM-04 .. TM-06: versions in a whole life cycle (LD-227) ----------

def test_tm04_life_cycle_create_edit_generate_restore():
    t = create(sections=["Overview", "Classes", "Functions"])
    job1, h1 = generate_with(t["id"])
    put(t["id"], **body(name=t["name"], sections=["Functions"]))
    job2, h2 = generate_with(t["id"])
    restored = client.post(f"/templates/{t['id']}/versions/1/restore").json()
    job3, h3 = generate_with(t["id"])
    assert [j["template_version"] for j in (job1, job2, job3)] == [1, 2, 3]
    assert h1 == h3 == [LABELS_VI[s] for s in ("Overview", "Classes", "Functions")]
    assert h2 == [LABELS_VI["Functions"]]
    assert restored["version"] == 3
    history = client.get(f"/templates/{t['id']}/versions").json()
    assert [(v["version"], v["restored_from"]) for v in history] == [(3, 1), (2, None), (1, None)]
    _, old = generate_with(t["id"], version=2)                  # an older version is still usable
    assert old == [LABELS_VI["Functions"]]


def test_tm05_concurrent_edits_get_distinct_consecutive_versions(tmp_path):
    store = TemplateStore(str(tmp_path / "t.json"))
    t = store.create(TemplateIn(name="Concurrent", instructions="v0", sections=["Overview"]))

    def edit(i):
        store.update(t.id, TemplateIn(name="Concurrent", instructions=f"v{i}", sections=["Overview"]))
    threads = [threading.Thread(target=edit, args=(i,)) for i in range(1, 21)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    numbers = [v.version for v in store.versions(t.id)]
    assert numbers == list(range(21, 0, -1))                   # 21 versions, no gap, no duplicate
    assert store.get(t.id).version == 21
    assert TemplateStore(str(tmp_path / "t.json")).get(t.id).version == 21


def test_tm06_restore_after_restart_and_names_stay_unique(tmp_path):
    path = str(tmp_path / "t.json")
    store = TemplateStore(path)
    a = store.create(TemplateIn(name="Alpha", instructions="x", sections=["Overview"]))
    store.update(a.id, TemplateIn(name="Beta", instructions="x", sections=["Overview"]))
    again = TemplateStore(path)                                  # restart
    restored = again.restore(a.id, 1)
    assert (restored.name, restored.version) == ("Alpha", 3)
    again.update(a.id, TemplateIn(name="Gamma", instructions="x", sections=["Overview"]))
    again.create(TemplateIn(name="Alpha", instructions="x", sections=["Overview"]))
    with pytest.raises(TemplateNameTaken):
        again.restore(a.id, 1)                                   # "Alpha" is now another template
    assert [v.version for v in TemplateStore(path).versions(a.id)] == [4, 3, 2, 1]


# ---------- TM-07 .. TM-08: snapshots and read-only templates ----------

def test_tm07_running_job_keeps_the_version_it_started_with(monkeypatch):
    t = create(sections=["Overview", "Functions"])
    from app import jobs as jobs_module
    from app.models import GenerateRequest
    req = GenerateRequest.model_validate({"scope": "file", "target": "shop", "template_id": t["id"],
                                          "files": [FILE]})
    snap = jobs_module.templates.at_version(t["id"], None)
    job = jobs_module.jobs.create(req, snap)
    put(t["id"], **body(name=t["name"], sections=["Classes"]))   # edited before the job runs
    from app.generator import DocGenerator
    jobs_module.run_job(job.id, req, DocGenerator(None), snap)
    done = jobs_module.jobs.get(job.id)
    assert done.template_version == 1 and done.template_sections == ["Overview", "Functions"]


@pytest.mark.parametrize("tid", ["default", "api-reference", "brief"])
def test_tm08_built_in_templates_cannot_change_in_any_way(tid):
    before = client.get(f"/templates/{tid}").json()
    assert client.put(f"/templates/{tid}", json=body()).status_code == 403
    assert client.delete(f"/templates/{tid}").status_code == 403
    assert client.post(f"/templates/{tid}/versions/1/restore").status_code == 403
    assert client.get(f"/templates/{tid}").json() == before
    assert len(client.get(f"/templates/{tid}/versions").json()) == 1
