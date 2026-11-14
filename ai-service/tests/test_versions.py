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
                                                   "files": [CART, USERS]})
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
    assert client.get(f"/documents/{response.json()['id']}").status_code == 404
    assert response.json()["id"] not in [doc["id"] for doc in client.get("/documents").json()]


def test_internal_document_edit_checks_owner_and_adds_version(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "workflow-internal-secret")
    job_response = client.post("/generate", json={"scope": "repository", "target": "acme/shop",
                                                   "files": [CART, USERS]})
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

    job_response = client.post("/generate", json=payload)
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
    # Version này không được kế thừa evidence/snapshot của version 1.
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

    # Version 2 là bản chỉnh sửa thủ công, không có evidence.
    response_v2 = client.get(
        f"/internal/documents/{doc['id']}/review-evidence?version=2",
        headers={
            "Authorization": "Bearer workflow-internal-secret",
        },
    )

    assert response_v2.status_code == 404


def test_review_evidence_returns_404_when_report_is_missing(monkeypatch):
    snapshot = {
        "repository_id": "repo-no-evidence",
        "repository_full_name": "acme/shop",
        "branch": "main",
        "commit_sha": "c" * 40,
        "fetched_at": "2026-11-09T10:00:00Z",
    }

    doc = create_internal_review_document(monkeypatch, snapshot)

    # Tạo version chỉnh sửa thủ công không có review_report.
    edit_response = client.put(
        f"/internal/documents/{doc['id']}/content",
        headers={
            "Authorization": "Bearer workflow-internal-secret",
            "X-User-Id": "73",
        },
        json={
            "content": "# Edited documentation",
            "expected_version": 1,
        },
    )

    assert edit_response.status_code == 200, edit_response.text

    response = client.get(
        f"/internal/documents/{doc['id']}/review-evidence?version=2",
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


