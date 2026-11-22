"""LD-227: documentation template versions.

Every change of a custom template saves a new version; earlier versions are kept and can be read,
used for generation or restored (restoring saves a new version, history is never rewritten).
"""
import json
import os
import uuid

os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.models import TemplateIn  # noqa: E402
from app.templates import TemplateStore  # noqa: E402
from main import app  # noqa: E402
from test_templates import FILE, generate, headings  # noqa: E402

client = TestClient(app)


def new_template(**over):
    body = {"name": f"Mẫu {uuid.uuid4().hex[:6]}", "description": "d", "instructions": "Viết ngắn.",
            "sections": ["Overview", "Functions"], **over}
    r = client.post("/templates", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def edit(tpl, **over):
    body = {k: tpl[k] for k in ("name", "description", "instructions", "sections")} | over
    r = client.put(f"/templates/{tpl['id']}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_new_template_is_version_1_with_one_saved_version():
    t = new_template()
    assert t["version"] == 1
    [v] = client.get(f"/templates/{t['id']}/versions").json()
    assert v["version"] == 1 and v["template_id"] == t["id"] and v["sections"] == ["Overview", "Functions"]
    assert v["restored_from"] is None


def test_each_change_saves_a_new_version_and_keeps_the_old_ones():
    t = new_template()
    t2 = edit(t, sections=["Overview"])
    t3 = edit(t2, instructions="Viết chi tiết.")
    assert (t2["version"], t3["version"]) == (2, 3)
    versions = client.get(f"/templates/{t['id']}/versions").json()
    assert [v["version"] for v in versions] == [3, 2, 1]                     # newest first
    assert versions[2]["sections"] == ["Overview", "Functions"]              # v1 unchanged
    assert client.get(f"/templates/{t['id']}/versions/2").json()["instructions"] == "Viết ngắn."
    assert client.get(f"/templates/{t['id']}").json()["version"] == 3


def test_saving_the_same_content_does_not_add_a_version():
    t = new_template()
    same = edit(t)
    assert same["version"] == 1 and len(client.get(f"/templates/{t['id']}/versions").json()) == 1


def test_restore_saves_the_old_content_as_a_new_version():
    t = new_template()
    edit(t, sections=["Overview"], name=t["name"] + " v2")
    r = client.post(f"/templates/{t['id']}/versions/1/restore")
    assert r.status_code == 200, r.text
    restored = r.json()
    assert restored["version"] == 3 and restored["sections"] == ["Overview", "Functions"]
    assert restored["name"] == t["name"]
    newest = client.get(f"/templates/{t['id']}/versions").json()[0]
    assert newest["version"] == 3 and newest["restored_from"] == 1
    # restoring the current content again changes nothing
    assert client.post(f"/templates/{t['id']}/versions/3/restore").json()["version"] == 3


def test_restore_refuses_a_name_now_used_by_another_template():
    t = new_template()
    old_name = t["name"]
    edit(t, name=old_name + " renamed")
    new_template(name=old_name)                                              # name taken meanwhile
    r = client.post(f"/templates/{t['id']}/versions/1/restore")
    assert r.status_code == 409 and "already exists" in r.json()["detail"]


def test_built_in_templates_have_one_version_and_cannot_be_restored():
    [v] = client.get("/templates/default/versions").json()
    assert v["version"] == 1 and client.get("/templates/default").json()["version"] == 1
    assert client.post("/templates/default/versions/1/restore").status_code == 403


def test_missing_template_or_version_is_404():
    t = new_template()
    assert client.get("/templates/nope/versions").status_code == 404
    assert client.get(f"/templates/{t['id']}/versions/9").status_code == 404
    assert client.post(f"/templates/{t['id']}/versions/9/restore").status_code == 404
    assert client.post("/templates/nope/versions/1/restore").status_code == 404


def test_jobs_report_and_document_record_the_template_version():
    t = new_template(sections=["Overview", "Classes", "Functions"])
    edit(t, sections=["Overview", "Functions"])
    job, md = generate(t["id"])
    assert job["template_version"] == 2
    assert client.get(f"/jobs/{job['id']}/report").json()["template_version"] == 2
    doc = client.post("/documents", json={"job_id": job["id"], "actor": "tester"}).json()
    assert doc["template_version"] == 2


def test_generation_can_use_an_older_version():
    t = new_template(sections=["Overview", "Classes", "Functions"])
    edit(t, sections=["Overview"])
    r = client.post("/generate", json={"scope": "file", "target": "shop", "template_id": t["id"],
                                       "template_version": 1, "files": [FILE]})
    assert r.status_code == 202, r.text
    job = client.get(f"/jobs/{r.json()['id']}").json()
    assert job["template_version"] == 1 and job["template_sections"] == ["Overview", "Classes", "Functions"]
    md = client.get(f"/jobs/{job['id']}/result").text
    assert len(headings(md)) == 3
    r = client.post("/generate", json={"scope": "file", "target": "shop", "template_id": t["id"],
                                       "template_version": 7, "files": [FILE]})
    assert r.status_code == 404 and "version 7" in r.json()["detail"]


def test_versions_survive_a_restart_and_old_files_read_as_version_1(tmp_path):
    path = tmp_path / "templates.json"
    store = TemplateStore(str(path))
    t = store.create(TemplateIn(name="A", instructions="x", sections=["Overview"]))
    store.update(t.id, TemplateIn(name="A", instructions="y", sections=["Overview"]))
    again = TemplateStore(str(path))
    assert again.get(t.id).version == 2
    assert [v.instructions for v in again.versions(t.id)] == ["y", "x"]

    old = tmp_path / "old.json"                    # written before LD-227: no history, no version
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("history")
    for item in raw["templates"]:
        item.pop("version")
    old.write_text(json.dumps(raw), encoding="utf-8")
    legacy = TemplateStore(str(old))
    assert legacy.get(t.id).version == 1
    assert [v.version for v in legacy.versions(t.id)] == [1]


def test_deleting_a_template_removes_its_versions():
    t = new_template()
    edit(t, sections=["Overview"])
    assert client.delete(f"/templates/{t['id']}").status_code == 204
    assert client.get(f"/templates/{t['id']}/versions").status_code == 404
