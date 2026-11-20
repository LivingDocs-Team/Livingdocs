"""Versioned documentation tests: LD-195."""
import os
import pytest

os.environ.pop("ANTHROPIC_API_KEY", None)  # offline generator

from fastapi.testclient import TestClient  # noqa: E402

from app.jobs import JobOutput  # noqa: E402
from app.models import (
    ConfidenceLevel,
    EntityReport,
    Evidence,
    EvidenceKind,
    FileReport,
    FileResultStatus,
    JobReport,
    Scope,
)  # noqa: E402
from app.versions import DocumentStore, VersionError
from main import app  # noqa: E402

client = TestClient(app)

CART = {
    "path": "shop/cart.py", "language": "python", "status": "ok",
    "functions": [{"name": "get_cart_total", "parameters": [{"name": "cart_id", "type": "int"}],
                   "return_type": "float", "lineno": 10, "end_lineno": 13}],
}
USERS = {
    "path": "shop/users.py", "language": "python", "status": "ok",
    "classes": [{"name": "UserService", "docstring": "Manages users.",
                 "methods": [{"name": "get_user", "parameters": [{"name": "user_id", "type": "int"}],
                              "return_type": "User"}]}],
}
REVIEW_REPORT = JobReport(
    job_id="job-review-001",
    template_id="default",
    template_name="Standard technical docs",
    confidence=0.9,
    level=ConfidenceLevel.high,
    method="Evidence-based confidence assessment",
    files=[
        FileReport(
            path="shop/cart.py",
            status=FileResultStatus.generated,
            confidence=0.9,
            level=ConfidenceLevel.high,
            entities=[],
            context_used=[
                Evidence(
                    id="E1",
                    kind=EvidenceKind.source,
                    path="shop/cart.py",
                    name="get_cart_total",
                    line_start=10,
                    line_end=13,
                    excerpt="def get_cart_total(cart_id: int):",
                )
            ],
        )
    ],
)

def test_save_job_report_in_document_version():
    store = DocumentStore()

    out = JobOutput(
        scope=Scope.repository,
        target="acme",
        template_id="default",
        template_name="Standard technical docs",
        output_language="en",
        sections=[("shop/cart.py", "# Cart documentation\n", "offline", 0.5)],
        confidence=0.5,
    )

    doc = store.create_from_job(
        "job-review-001",
        out,
        actor="linh",
        report=REVIEW_REPORT,
    )

    version = store.version(doc.id, 1)

    assert version.review_report is not None
    assert version.review_report.job_id == "job-review-001"
    assert version.review_report.confidence == 0.9
    assert version.review_report.files[0].path == "shop/cart.py"
    assert version.review_report.files[0].context_used[0].id == "E1"
# ---------- LD-195: documents and version history ----------

def new_document(files=None, scope="repository", target="acme/shop"):
    files = files or [CART, USERS]
    r = client.post("/generate", json={"scope": scope, "target": target, "files": files})
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "completed"
    r = client.post("/documents", json={"job_id": job_id, "actor": "linh"})
    assert r.status_code == 201, r.text
    return r.json()


def test_save_job_as_version_1():
    doc = new_document()
    assert doc["current_version"] == 1 and doc["pending_version"] is None
    assert doc["target"] == "acme/shop" and doc["versions_total"] == 1

    v1 = client.get(f"/documents/{doc['id']}/versions/1").json()
    assert v1["status"] == "accepted" and v1["origin"] == "generated"
    assert [s["path"] for s in v1["sections"]] == ["shop/cart.py", "shop/users.py"]
    md = client.get(f"/documents/{doc['id']}/content").text
    assert md == v1["content"] and "get_cart_total" in md and "UserService" in md

    history = client.get(f"/documents/{doc['id']}/history").json()
    assert [(e["action"], e["version"], e["actor"]) for e in history] == [("created", 1, "linh")]
    assert doc["id"] in [d["id"] for d in client.get("/documents").json()]


def test_create_document_errors():
    assert client.post("/documents", json={"job_id": "nope"}).status_code == 404
    r = client.post("/generate", json={"scope": "file", "target": "x.py",
                                       "files": [{"path": "x.py", "status": "invalid", "error": "bad"}]})
    failed = r.json()["id"]
    assert client.get(f"/jobs/{failed}").json()["status"] == "failed"
    r = client.post("/documents", json={"job_id": failed})
    assert r.status_code == 409 and "failed" in r.json()["detail"]
    assert client.get("/documents/nope").status_code == 404
    doc = new_document()
    assert client.get(f"/documents/{doc['id']}/versions/9").status_code == 404
    assert client.get(f"/documents/{doc['id']}/content?version=9").status_code == 404


# ---------- persistence ----------

def test_documents_survive_restart(tmp_path):
    path = tmp_path / "documents.json"
    store = DocumentStore(str(path))
    evidence_report = JobReport(
        job_id="job1",
        template_id="default",
        template_name="Standard technical docs",
        confidence=0.5,
        method="test",
        files=[
            FileReport(
                path="a.py",
                status=FileResultStatus.offline,
                entities=[
                    EntityReport(
                        kind="class",
                        name="Example",
                        confidence=0.5,
                        level=ConfidenceLevel.low,
                        evidence=[
                            Evidence(
                                id="E1",
                                kind=EvidenceKind.source,
                                path="a.py",
                                name="Example",
                                line_start=1,
                                line_end=3,
                                excerpt="class Example:",
                            )
                        ],
                    )
                ],
            )
        ],
    )

    out = JobOutput(
        scope=Scope.repository,
        target="acme",
        template_id="default",
        template_name="Standard technical docs",
        output_language="en",
        sections=[("a.py", "# a.py\n\nA.\n", "offline", 0.5)],
        skipped=[("b.py", "bad")],
        confidence=0.5,
        evidence_report=evidence_report,
    )
    doc = store.create_from_job("job1", out, actor="linh")

    again = DocumentStore(str(path))
    d = again.get(doc.id)
    assert d.current_version == 1 and d.target == "acme"
    v = again.version(doc.id)
    assert "# a.py" in v.content and [s.path for s in v.skipped] == ["b.py"]
    assert v.evidence_report is not None
    assert v.evidence_report.job_id == "job1"
    evidence = v.evidence_report.files[0].entities[0].evidence[0]
    assert evidence.id == "E1"
    assert evidence.path == "a.py"
    assert evidence.line_start == 1
    assert [e.action.value for e in again.history(doc.id)] == ["created"]

    path.write_text("{not json", encoding="utf-8")
    assert DocumentStore(str(path)).list() == []
    assert list(tmp_path.glob("documents.corrupt-*.json"))
def test_review_report_survives_restart(tmp_path):
    path = tmp_path / "documents.json"
    store = DocumentStore(str(path))

    out = JobOutput(
        scope=Scope.repository,
        target="acme",
        template_id="default",
        template_name="Standard technical docs",
        output_language="en",
        sections=[("shop/cart.py", "# Cart documentation\n", "offline", 0.5)],
        confidence=0.5,
    )

    doc = store.create_from_job(
        "job-review-001",
        out,
        actor="linh",
        report=REVIEW_REPORT,
    )

    restored = DocumentStore(str(path))
    version = restored.version(doc.id, 1)

    assert version.review_report is not None
    assert version.review_report.job_id == "job-review-001"
    assert version.review_report.files[0].context_used[0].excerpt == (
        "def get_cart_total(cart_id: int):"
    )

def test_workflow_owner_is_persisted_and_legacy_actor_is_not_an_owner(tmp_path):
    path = tmp_path / "documents.json"
    store = DocumentStore(str(path))
    out = JobOutput(scope=Scope.repository, target="acme", template_id="default",
                    template_name="Standard technical docs", output_language="en",
                    sections=[("a.py", "# a.py\n", "offline", 0.5)])
    legacy = store.create_from_job("legacy-job", out, actor="untrusted-actor")
    owned = store.create_from_job("owned-job", out, actor="73", owner_user_id="73")

    restored = DocumentStore(str(path))
    assert restored.get(legacy.id).owner_user_id is None
    assert restored.get_owned(owned.id, "73").owner_user_id == "73"
    assert restored.version(owned.id, 1).created_by == "73"
    with pytest.raises(VersionError) as error:
        restored.get_owned(legacy.id, "73")
    assert error.value.status == 404
    with pytest.raises(VersionError) as error:
        restored.get_owned(owned.id, "74")
    assert error.value.status == 404


def test_owner_edit_adds_a_new_proposal_version_and_rejects_duplicate_pending_edit():
    store = DocumentStore()
    out = JobOutput(scope=Scope.file, target="a.py", template_id="default",
                    template_name="Standard technical docs", output_language="en",
                    sections=[("a.py", "# a.py\n", "offline", 0.5)])
    doc = store.create_from_job("job1", out, actor="73", owner_user_id="73")

    proposal = store.edit_owned(doc.id, "73", 1, "# Revised document", "Updated after staff feedback")

    assert proposal.number == 2
    assert proposal.status.value == "proposed"
    assert proposal.created_by == "73"
    assert store.get(doc.id).pending_version == 2
    assert store.history(doc.id)[-1].action.value == "proposed"
    with pytest.raises(VersionError) as error:
        store.edit_owned(doc.id, "73", 1, "# Another edit")
    assert error.value.status == 409


def test_internal_document_routes_require_the_service_credential(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")
    response = client.get("/internal/documents/missing", headers={
        "Authorization": "Bearer wrong-secret",
    })
    assert response.status_code == 401


def test_internal_document_creation_uses_trusted_owner_not_request_fields(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")
    job_response = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                                   "files": [CART, USERS]},
                                 headers={"Authorization": "Bearer workflow-internal-secret"})
    assert job_response.status_code == 202
    job_id = job_response.json()["id"]

    response = client.post("/internal/documents/from-job", headers={
        "Authorization": "Bearer workflow-internal-secret", "X-User-Id": "73",
    }, json={"job_id": job_id, "actor": "999", "owner_user_id": "999", "user_id": "999"})

    assert response.status_code == 201, response.text
    assert response.json()["owner_user_id"] == "73"
    assert response.json()["id"]
    assert response.json()["current_version"] == 0
    assert response.json()["pending_version"] == 1
    assert client.get(f"/documents/{response.json()['id']}",
                      headers={"Authorization": "Bearer workflow-internal-secret"}).status_code == 404
    assert response.json()["id"] not in [doc["id"] for doc in client.get("/documents", headers={"Authorization": "Bearer workflow-internal-secret"}).json()]


def test_internal_document_edit_checks_owner_and_adds_version(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")
    job_response = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                                   "files": [CART, USERS]},
                                 headers={"Authorization": "Bearer workflow-internal-secret"})
    job_id = job_response.json()["id"]
    created = client.post("/internal/documents/from-job", headers={
        "Authorization": "Bearer workflow-internal-secret", "X-User-Id": "73",
    }, json={"job_id": job_id}).json()
    path = f"/internal/documents/{created['id']}/content"

    denied = client.put(path, headers={
        "Authorization": "Bearer workflow-internal-secret", "X-User-Id": "74",
    }, json={"content": "Not the owner", "expected_version": 1})
    assert denied.status_code == 404

    edited = client.put(path, headers={
        "Authorization": "Bearer workflow-internal-secret", "X-User-Id": "73",
    }, json={"content": "# Updated by owner", "expected_version": 1})
    assert edited.status_code == 200, edited.text
    assert edited.json()["number"] == 2
    assert edited.json()["status"] == "proposed"
    assert client.get(f"/internal/documents/{created['id']}", headers={
        "Authorization": "Bearer workflow-internal-secret",
        "X-User-Id": "73",
    }).json()["owner_user_id"] == "73"

    forged_owner_edit = client.put(path, headers={
        "Authorization": "Bearer workflow-internal-secret", "X-User-Id": "73",
    }, json={"content": "# Still the same owner", "expected_version": 2,
            "owner_user_id": "74", "actor": "999"})
    assert forged_owner_edit.status_code == 200, forged_owner_edit.text
    assert client.get(f"/internal/documents/{created['id']}", headers={
        "Authorization": "Bearer workflow-internal-secret",
        "X-User-Id": "73",
    }).json()["owner_user_id"] == "73"


def test_document_versions_support_repeated_changes_and_final_decision():
    store = DocumentStore()
    out = JobOutput(scope=Scope.file, target="a.py", template_id="default",
                    template_name="Standard technical docs", output_language="en",
                    sections=[("a.py", "# a.py\n", "offline", 0.5)])
    doc = store.create_from_job("job1", out, actor="73", owner_user_id="73")
    first = store.edit_owned(doc.id, "73", 1, "# First proposal")
    second = store.edit_owned(doc.id, "73", first.number, "# Revised proposal")
    assert first.status.value == "superseded"
    assert second.status.value == "proposed"

    store.resolve_workflow_version(doc.id, "73", second.number, "APPROVED", "84", "Looks good")
    persisted = store.get(doc.id)
    assert persisted.current_version == second.number
    assert persisted.pending_version is None
    assert store.version(doc.id).status.value == "accepted"
    assert store.history(doc.id)[-1].actor == "84"

def test_legacy_job_report_without_template_snapshot_remains_valid():
    report = JobReport(
        job_id="legacy-job",
        template_id="default",
        template_name="Default",
    )

    assert report.template_instructions is None
    assert report.template_sections == []
def create_internal_review_document(monkeypatch, source_snapshot=None):
    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")

    payload = {
        "scope": "repository",
        "target": "acme/shop",
        "files": [CART, USERS],
    }

    if source_snapshot is not None:
        payload["source_snapshot"] = source_snapshot

    job_response = client.post("/generate", json=payload,
                               headers={"Authorization": "Bearer workflow-internal-secret"})
    assert job_response.status_code == 202, job_response.text

    job_id = job_response.json()["id"]

    created_response = client.post(
        "/internal/documents/from-job",
        headers={
            "Authorization": "Bearer workflow-internal-secret",
            "X-User-Id": "73",
        },
        json={"job_id": job_id},
    )

    assert created_response.status_code == 201, created_response.text
    return created_response.json()
def test_review_evidence_returns_report_and_source_snapshot(monkeypatch):
    snapshot = {
        "repository_id": "repo-123",
        "repository_full_name": "acme/shop",
        "branch": "main",
        "commit_sha": "a" * 40,
        "fetched_at": "2026-11-09T10:00:00Z",
    }

    doc = create_internal_review_document(monkeypatch, snapshot)

    response = client.get(
        f"/internal/documents/{doc['id']}/review-evidence?version=1",
        headers={
            "Authorization": "Bearer workflow-internal-secret",
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    # Các trường evidence cũ vẫn được giữ nguyên.
    assert data["job_id"]
    assert "files" in data
    assert "template_name" in data

    # Snapshot phải đúng với snapshot đã lưu ở version 1.
    assert data["source_snapshot"]["repository_id"] == "repo-123"
    assert data["source_snapshot"]["repository_full_name"] == "acme/shop"
    assert data["source_snapshot"]["branch"] == "main"
    assert data["source_snapshot"]["commit_sha"] == "a" * 40


def test_review_evidence_without_source_snapshot_returns_null(monkeypatch):
    doc = create_internal_review_document(monkeypatch)

    response = client.get(
        f"/internal/documents/{doc['id']}/review-evidence?version=1",
        headers={
            "Authorization": "Bearer workflow-internal-secret",
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["job_id"]
    assert "files" in data
    assert data["source_snapshot"] is None


def test_review_evidence_uses_requested_version(monkeypatch):
    snapshot = {
        "repository_id": "repo-version-test",
        "repository_full_name": "acme/shop",
        "branch": "main",
        "commit_sha": "b" * 40,
        "fetched_at": "2026-11-09T10:00:00Z",
    }

    doc = create_internal_review_document(monkeypatch, snapshot)

    # Tạo version 2 bằng chỉnh sửa thủ công.
    # LD-402: version này kế thừa evidence/snapshot của version 1 (evidence_from_version = 1).
    edit_response = client.put(
        f"/internal/documents/{doc['id']}/content",
        headers={
            "Authorization": "Bearer workflow-internal-secret",
            "X-User-Id": "73",
        },
        json={
            "content": "# Manually edited documentation",
            "expected_version": 1,
        },
    )

    assert edit_response.status_code == 200, edit_response.text
    assert edit_response.json()["number"] == 2

    # Yêu cầu version 1 phải nhận snapshot của version 1.
    response_v1 = client.get(
        f"/internal/documents/{doc['id']}/review-evidence?version=1",
        headers={
            "Authorization": "Bearer workflow-internal-secret",
        },
    )

    assert response_v1.status_code == 200, response_v1.text
    assert response_v1.json()["source_snapshot"]["commit_sha"] == "b" * 40

    # LD-402: version 2 là bản chỉnh sửa thủ công; staff vẫn review được với evidence của version 1.
    response_v2 = client.get(
        f"/internal/documents/{doc['id']}/review-evidence?version=2",
        headers={
            "Authorization": "Bearer workflow-internal-secret",
        },
    )

    assert response_v2.status_code == 200, response_v2.text
    assert response_v2.json()["source_snapshot"]["commit_sha"] == "b" * 40
    assert edit_response.json()["evidence_from_version"] == 1


def test_review_evidence_returns_404_when_report_is_missing(monkeypatch):
    # LD-402: an edit now keeps the evidence of its base, so "missing" means a version whose
    # whole history has no review report (a document saved without a job report).
    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")
    store = DocumentStore()
    out = JobOutput(scope=Scope.file, target="a.py", template_id="default", template_name=None,
                    output_language="en", sections=[("a.py", "# A\n", "offline", 0.5)])
    doc = store.create_from_job("no-report-job", out, actor="73", owner_user_id="73")
    store.edit_owned(doc.id, "73", 1, "# Edited documentation")
    monkeypatch.setattr("main.documents", store)

    for version in (1, 2):
        response = client.get(
            f"/internal/documents/{doc.id}/review-evidence?version={version}",
            headers={
                "Authorization": "Bearer workflow-internal-secret",
            },
        )
        assert response.status_code == 404

# ---------- Rollback approved document versions ----------

def create_approved_owned_document():
    store = DocumentStore()

    out = JobOutput(
        scope=Scope.file,
        target="a.py",
        template_id="default",
        template_name="Standard technical docs",
        output_language="en",
        sections=[("a.py", "# Original document\n", "offline", 0.5)],
    )

    doc = store.create_from_job(
        "rollback-job",
        out,
        actor="73",
        owner_user_id="73",
    )

    store.resolve_workflow_version(
        doc.id,
        "73",
        1,
        "APPROVED",
        "84",
        "Initial approval",
    )

    return store, doc


def test_rollback_creates_new_proposal_from_approved_version():
    store, doc = create_approved_owned_document()

    source = store.version(doc.id, 1)

    rollback = store.rollback_owned(
        doc.id,
        "73",
        1,
        "manager-9",
        "Restore the previously approved version",
    )

    assert rollback.number == 2
    assert rollback.status.value == "proposed"
    assert rollback.origin.value == "rollback"
    assert rollback.restored_from == 1
    assert rollback.base_version == 1
    assert rollback.content == source.content
    assert rollback.created_by == "manager-9"

    persisted = store.get(doc.id)
    assert persisted.current_version == 1
    assert persisted.pending_version == 2
    assert persisted.versions_total == 2

    history = store.history(doc.id)
    assert history[-1].action.value == "rolled_back"
    assert history[-1].version == 2
    assert history[-1].related_version == 1
    assert history[-1].actor == "manager-9"


def test_rollback_rejects_version_that_is_not_approved():
    store = DocumentStore()

    out = JobOutput(
        scope=Scope.file,
        target="a.py",
        template_id="default",
        template_name="Standard technical docs",
        output_language="en",
        sections=[("a.py", "# Draft document\n", "offline", 0.5)],
    )

    doc = store.create_from_job(
        "rollback-job",
        out,
        actor="73",
        owner_user_id="73",
    )

    with pytest.raises(VersionError) as error:
        store.rollback_owned(doc.id, "73", 1, "manager-9", "Restore version")

    assert error.value.status == 409
    assert store.get(doc.id).pending_version == 1


def test_rollback_rejects_when_another_version_is_pending():
    store, doc = create_approved_owned_document()

    proposal = store.edit_owned(
        doc.id,
        "73",
        1,
        "# New proposed document",
        "New changes",
    )

    assert proposal.number == 2

    with pytest.raises(VersionError) as error:
        store.rollback_owned(doc.id, "73", 1, "manager-9", "Restore version")

    assert error.value.status == 409
    assert store.get(doc.id).pending_version == 2


def test_rollback_retry_returns_existing_matching_proposal():
    store, doc = create_approved_owned_document()

    first = store.rollback_owned(
        doc.id,
        "73",
        1,
        "manager-9",
        "Restore version 1",
    )

    retry = store.rollback_owned(
        doc.id,
        "73",
        1,
        "manager-9",
        "Restore version 1",
    )

    assert retry.number == first.number
    assert store.get(doc.id).versions_total == 2
    assert len(store.history(doc.id)) == 3
def test_revision_draft_is_grounded_idempotent_and_only_exact_version_can_publish(monkeypatch):
    from app.generator import FileDocResult
    from datetime import timedelta
    from app.models import SourceSnapshot, now
    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")
    store, doc = create_approved_owned_document()
    base = store.version(doc.id)
    base.source_snapshot = SourceSnapshot(
        repository_id="repo-1", repository_full_name="org/repo",
        branch="main", commit_sha="a" * 40,
    )
    monkeypatch.setattr("main.documents", store)
    calls = []

    class Generator:
        def document_file(self, file, template, language, retrieved):
            calls.append(file.path)
            return FileDocResult(
                "# Updated documentation\n", FileResultStatus.generated,
                report=FileReport(path=file.path, status=FileResultStatus.generated, confidence=0.9),
            )

    monkeypatch.setattr("main.get_generator", Generator)
    headers = {"Authorization": "Bearer workflow-internal-secret", "X-User-Id": "73"}
    url = f"/internal/documents/{doc.id}/revision-drafts"
    prepare, commit = url + "/prepare", url + "/commit"
    data = {
        "source_change_id": "change-1",
        "trigger": "COMMIT",
        "source_snapshot": base.source_snapshot.model_dump(mode="json") | {"commit_sha": "b" * 40},
        "base_version": 1,
        "files": [{"path": "a.py", "language": "python"}],
    }
    assert client.post(prepare, json=data).status_code in (401, 403)
    assert client.post(prepare, headers=headers | {"X-User-Id": "someone-else"}, json=data).status_code == 404
    assert client.post(prepare, headers=headers, json=data | {
        "source_snapshot": data["source_snapshot"] | {"repository_id": "repo-2"},
    }).status_code == 409

    response = client.post(prepare, headers=headers, json=data)
    assert response.status_code == 200, response.text
    assert store.get(doc.id).pending_version is None
    commit_data = data | {"prepared": response.json(), "lease_expires_at": now().isoformat()}
    assert client.post(commit, headers=headers, json=commit_data).status_code == 409
    assert store.get(doc.id).versions_total == 1
    assert store.get(doc.id).pending_version is None
    commit_data["lease_expires_at"] = (now() + timedelta(minutes=15)).isoformat()
    response = client.post(commit, headers=headers, json=commit_data)
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["number"] == 2
    assert draft["base_version"] == 1
    assert draft["source_snapshot"]["commit_sha"] == "b" * 40
    assert draft["evidence_report"]["files"][0]["path"] == "a.py"
    assert store.version(doc.id).content == "# Original document\n"
    retry = client.post(prepare, headers=headers, json=data)
    assert retry.status_code == 200
    assert client.post(commit, headers=headers, json=commit_data | {"prepared": retry.json()}).json()["number"] == 2
    assert calls == ["a.py"]
    assert client.post(prepare, headers=headers, json=data | {"source_change_id": "other"}).status_code == 409

    with pytest.raises(VersionError, match="pending document version has changed"):
        store.resolve_workflow_version(doc.id, "73", 1, "APPROVED", "manager")
    store.resolve_workflow_version(doc.id, "73", 2, "APPROVED", "manager")
    assert store.version(doc.id).number == 2
    assert [event.actor for event in store.history(doc.id)][-2:] == ["AI", "manager"]

def test_revision_operations_preserve_evidence_and_require_exact_generated_sections():
    from app.models import SourceSnapshot
    from app.version_models import FileSection, RevisionDraftRequest

    store = DocumentStore()
    snapshot = SourceSnapshot(repository_id="repo", repository_full_name="org/repo",
                              branch="main", commit_sha="a" * 40)
    doc = store.create_from_job(
        "seed", JobOutput(
            scope=Scope.repository, target="org/repo", template_id="default",
            template_name="Standard", output_language="en",
            sections=[(path, f"# {path}", "generated", 0.8)
                      for path in ("old.py", "deleted.py", "consumer.py", "unchanged.py")],
            source_snapshot=snapshot,
        ), owner_user_id="owner",
    )
    store.resolve_workflow_version(doc.id, "owner", 1, "APPROVED", "manager")
    blob = "c" * 40
    request = RevisionDraftRequest(
        source_change_id="change", trigger="COMMIT", base_version=1,
        source_snapshot=snapshot.model_copy(update={"commit_sha": "b" * 40}),
        files=[{"path": path} for path in ("new.py", "renamed.py", "consumer.py")],
        file_changes=[
            {"path": "new.py", "action": "added", "blob_sha": blob},
            {"path": "deleted.py", "action": "removed"},
            {"path": "renamed.py", "action": "renamed", "previous_path": "old.py", "blob_sha": blob},
            {"path": "consumer.py", "action": "dependent", "blob_sha": blob},
        ],
    )

    def generate(document, files):
        assert {file.path for file in files} == {"new.py", "renamed.py", "consumer.py"}
        return {file.path: FileSection(path=file.path, markdown=f"# New {file.path}", status="generated")
                for file in files}, REVIEW_REPORT

    prepared = store.prepare_revision(doc.id, "owner", request, generate)
    invalid = prepared.model_copy(update={"replacements": {"new.py": prepared.replacements["new.py"]}})
    with pytest.raises(VersionError, match="Prepared sections do not match"):
        store.commit_revision(doc.id, "owner", request, invalid)
    assert store.get(doc.id).pending_version is None

    version = store.commit_revision(doc.id, "owner", request, prepared)
    assert [section.path for section in version.sections] == [
        "renamed.py", "consumer.py", "unchanged.py", "new.py",
    ]
    assert [(change.path, change.action.value, change.previous_path) for change in version.changes] == [
        ("new.py", "added", None), ("deleted.py", "removed", None),
        ("renamed.py", "renamed", "old.py"), ("consumer.py", "updated", None),
    ]
    assert version.revision_files[-1].action == "dependent"
    assert version.revision_files[-1].blob_sha == blob
    assert version.source_snapshot.commit_sha == "b" * 40
    assert store.version(doc.id).number == 1


def test_revision_delete_only_never_calls_generator(monkeypatch):
    from datetime import timedelta
    from app.models import SourceSnapshot, now

    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")
    store, doc = create_approved_owned_document()
    source = SourceSnapshot(repository_id="repo", repository_full_name="org/repo",
                            branch="main", commit_sha="a" * 40)
    store.version(doc.id).source_snapshot = source
    monkeypatch.setattr("main.documents", store)
    monkeypatch.setattr("main.get_generator", lambda: pytest.fail("Delete-only draft called AI"))
    headers = {"Authorization": "Bearer workflow-internal-secret", "X-User-Id": "73"}
    url = f"/internal/documents/{doc.id}/revision-drafts"
    body = {
        "source_change_id": "delete", "trigger": "COMMIT", "base_version": 1,
        "source_snapshot": source.model_dump(mode="json") | {"commit_sha": "b" * 40},
        "files": [], "file_changes": [{"path": "a.py", "action": "removed"}],
    }
    response = client.post(f"{url}/prepare", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert store.version(doc.id).sections[0].path == "a.py"
    body.update(prepared=response.json(), lease_expires_at=(now() + timedelta(minutes=15)).isoformat())
    response = client.post(f"{url}/commit", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["sections"] == []
    assert response.json()["changes"] == [{"path": "a.py", "action": "removed",
                                            "previous_path": None, "entities": []}]

    evidence = client.get(f"/internal/documents/{doc.id}/review-evidence?version=2", headers=headers)
    assert evidence.status_code == 200
    assert evidence.json()["source_snapshot"]["commit_sha"] == "b" * 40
    assert evidence.json()["revision_files"][0]["action"] == "removed"


def test_concurrent_revision_drafts_persist_one_version_and_rollback_requires_review(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.models import SourceSnapshot
    from app.version_models import FileSection, RevisionDraftRequest

    path = tmp_path / "documents.json"
    store = DocumentStore(str(path))
    source = SourceSnapshot(repository_id="repo-1", repository_full_name="org/repo",
                            branch="main", commit_sha="a" * 40)
    doc = store.create_from_job(
        "seed", JobOutput(scope=Scope.file, target="a.py", template_id="default",
                          template_name="Standard", output_language="en",
                          sections=[("a.py", "# Original", "generated", 0.8)], source_snapshot=source),
        owner_user_id="owner",
    )
    store.resolve_workflow_version(doc.id, "owner", 1, "APPROVED", "manager")
    request = RevisionDraftRequest(
        source_change_id="change-1", trigger="COMMIT", base_version=1,
        source_snapshot=source.model_copy(update={"commit_sha": "b" * 40}),
        files=[{"path": "a.py"}],
    )
    simultaneous = Barrier(2, timeout=5)

    def generate(document, files):
        simultaneous.wait()
        return {"a.py": FileSection(path="a.py", markdown="# New", status="generated")}, REVIEW_REPORT

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(store.propose_revision, doc.id, "owner", request, generate)
        second = pool.submit(store.propose_revision, doc.id, "owner", request, generate)
        assert first.result(timeout=6).number == second.result(timeout=6).number == 2

    restored = DocumentStore(str(path))
    assert [version.number for version in restored.versions(doc.id)] == [2, 1]
    assert restored.get(doc.id).pending_revision.commit_sha == "b" * 40
    restored.resolve_workflow_version(doc.id, "owner", 2, "APPROVED", "manager")
    rollback = restored.rollback_owned(doc.id, "owner", 1, "manager")
    assert rollback.number == 3
    assert restored.version(doc.id).content == "# New"
    assert restored.get(doc.id).pending_revision is None
    restored.resolve_workflow_version(doc.id, "owner", 3, "APPROVED", "manager")
    assert restored.version(doc.id).content == "# Original"
