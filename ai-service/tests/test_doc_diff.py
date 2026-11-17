"""LD-183 Documentation diff & comparison: LD-184 select versions, LD-185 diff, LD-186 added /
removed content, LD-187 modified content, LD-188 tests."""
import os

os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.doc_diff import NO_SECTION, DiffLineKind, SectionStatus, diff_texts, inline_segments  # noqa: E402
from app.jobs import JobOutput  # noqa: E402
from app.models import Scope  # noqa: E402
from app.versions import DocumentStore, VersionError  # noqa: E402
from main import app  # noqa: E402

SECRET = "ld183-internal-secret"
H = {"Authorization": f"Bearer {SECRET}", "X-User-Id": "73"}
client = TestClient(app)

V1 = """# Cart

The cart total includes VAT.

## get_total

Returns the total in VND.
Parameters: cart

## Legacy

Old text."""

V2 = """# Cart

The cart total includes VAT and shipping.

## get_total

New intro line.
Returns the total in VND.
Parameters: cart, currency

## Shipping options

Brand new."""


def kinds(diff):
    return [r.kind for r in diff.rows]


# ---------- LD-185 diff engine ----------

def test_identical_texts_have_no_changes():
    d = diff_texts(V1, V1)
    assert d.identical and set(kinds(d)) == {DiffLineKind.unchanged}
    assert (d.stats.added, d.stats.removed, d.stats.modified) == (0, 0, 0)
    assert all(s.status == SectionStatus.unchanged for s in d.sections)


def test_added_removed_and_modified_lines_with_line_numbers():
    d = diff_texts(V1, V2)
    assert not d.identical
    assert (d.stats.added, d.stats.removed, d.stats.modified) == (3, 2, 2)
    added = [(r.new_number, r.new_text) for r in d.rows if r.kind == DiffLineKind.added]
    removed = [(r.old_number, r.old_text) for r in d.rows if r.kind == DiffLineKind.removed]
    assert (7, "New intro line.") in added and (11, "## Shipping options") in added
    assert removed == [(10, "## Legacy"), (12, "Old text.")]
    for r in d.rows:                          # a side exists exactly when it has a line number
        assert (r.old_text is None) == (r.old_number is None)
        assert (r.new_text is None) == (r.new_number is None)


def test_modified_lines_mark_only_the_changed_words():
    d = diff_texts(V1, V2)
    vat = next(r for r in d.rows if r.kind == DiffLineKind.modified and "VAT" in r.new_text)
    assert (vat.old_number, vat.new_number) == (3, 3)
    assert [(s.text, s.changed) for s in vat.new_segments] == [
        ("The cart total includes VAT", False), (" and shipping", True), (".", False)]
    assert "".join(s.text for s in vat.old_segments) == vat.old_text
    assert not any(s.changed for s in vat.old_segments)     # nothing was removed from this line
    params = next(r for r in d.rows if r.kind == DiffLineKind.modified and "Parameters" in r.new_text)
    assert [s.text for s in params.new_segments if s.changed] == [", currency"]


def test_unrelated_replacement_is_removed_plus_added_not_modified():
    d = diff_texts("alpha beta gamma", "completely different words")
    assert kinds(d) == [DiffLineKind.removed, DiffLineKind.added]


def test_sections_report_added_removed_and_modified_parts():
    d = diff_texts(V1, V2)
    status = {s.section: s.status for s in d.sections}
    assert status == {"Cart": SectionStatus.modified, "get_total": SectionStatus.modified,
                      "Legacy": SectionStatus.removed, "Shipping options": SectionStatus.added}
    get_total = next(s for s in d.sections if s.section == "get_total")
    assert (get_total.added, get_total.removed, get_total.modified) == (1, 0, 1)


@pytest.mark.parametrize("old, new, expected", [
    ("", "a\nb", (2, 0, 0)), ("a\nb", "", (0, 2, 0)), ("a\r\nb\r\n", "a\nb", (0, 0, 0)),
    ("x = 1", "x = 2", (0, 0, 1)),
])
def test_edge_cases(old, new, expected):
    d = diff_texts(old, new)
    assert (d.stats.added, d.stats.removed, d.stats.modified) == expected


def test_text_without_headings_has_one_section():
    d = diff_texts("one\ntwo", "one\nthree two")
    assert [s.section for s in d.sections] == [NO_SECTION]


def test_inline_segments_rebuild_both_lines():
    old, new = "Use GET /carts/{id} to read a cart.", "Use GET /api/carts/:id to read one cart."
    a, b = inline_segments(old, new)
    assert "".join(s.text for s in a) == old and "".join(s.text for s in b) == new
    assert any(s.changed for s in a) and any(s.changed for s in b)


# ---------- LD-184 choose versions (store) ----------

def store_with_versions(n=3):
    store = DocumentStore()
    out = JobOutput(scope=Scope.file, target="cart.md", template_id="default", template_name=None,
                    output_language="en", sections=[("cart.md", V1, "generated", 0.8)])
    doc = store.create_from_job("job-183", out, actor="73", owner_user_id="73")
    texts = [V2, V2 + "\n\nExtra line."]
    for k in range(n - 1):
        store.edit_owned(doc.id, "73", k + 1, texts[k])
    return store, doc.id


def test_default_compares_the_current_version_with_the_previous_one():
    store, d = store_with_versions(3)
    diff = store.compare(d)
    assert (diff.from_version.number, diff.to_version.number) == (2, 3)
    assert diff.stats.added == 2 and diff.document_id == d   # the blank line and "Extra line."


def test_any_two_versions_in_either_direction():
    store, d = store_with_versions(3)
    forward = store.compare(d, 1, 3)
    backward = store.compare(d, 3, 1)
    assert (forward.stats.added, forward.stats.removed) == (backward.stats.removed, backward.stats.added)
    assert forward.from_version.status.value == "superseded" and forward.to_version.origin.value == "edit"


@pytest.mark.parametrize("args, status, message", [
    ((2, 2), 400, "Select two different versions to compare."),
    ((1, 9), 404, "Version 9 not found"),
])
def test_invalid_choices(args, status, message):
    store, d = store_with_versions(2)
    with pytest.raises(VersionError) as e:
        store.compare(d, *args)
    assert (e.value.status, e.value.message) == (status, message)


def test_a_single_version_cannot_be_compared_yet():
    store, d = store_with_versions(1)
    with pytest.raises(VersionError) as e:
        store.compare(d)
    assert (e.value.status, e.value.message) == (409, "Create a version first to enable comparison.")


# ---------- API ----------

def test_internal_api_lists_and_compares_versions(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    store, d = store_with_versions(3)
    monkeypatch.setattr("main.documents", store)

    versions = client.get(f"/internal/documents/{d}/versions", headers=H)
    assert versions.status_code == 200 and [v["number"] for v in versions.json()] == [3, 2, 1]
    r = client.get(f"/internal/documents/{d}/compare", params={"from": 1, "to": 2}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert (body["from_version"]["number"], body["to_version"]["number"]) == (1, 2)
    assert body["stats"] == {"added": 3, "removed": 2, "modified": 2, "unchanged": 8}
    assert {s["section"]: s["status"] for s in body["sections"]}["Shipping options"] == "added"
    assert any(row["kind"] == "modified" and row["new_segments"] for row in body["rows"])
    latest = client.get(f"/internal/documents/{d}/compare", headers=H).json()
    assert (latest["from_version"]["number"], latest["to_version"]["number"]) == (2, 3)

    assert client.get(f"/internal/documents/{d}/compare", params={"from": 2, "to": 2}, headers=H).status_code == 400
    assert client.get(f"/internal/documents/{d}/compare", params={"from": 0}, headers=H).status_code == 422
    assert client.get("/internal/documents/nope/compare", headers=H).status_code == 404
    assert client.get(f"/internal/documents/{d}/compare").status_code == 401     # service credential


def test_public_comparison_only_for_documents_without_an_owner(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
    store, owned = store_with_versions(2)
    legacy = store.create_from_job("job-legacy", JobOutput(
        scope=Scope.file, target="a.md", template_id="default", template_name=None, output_language="en",
        sections=[("a.md", "# A\n\nold", "generated", 0.8)]), actor="tester")
    monkeypatch.setattr("main.documents", store)

    assert client.get(f"/documents/{owned}/compare").status_code == 404
    r = client.get(f"/documents/{legacy.id}/compare")
    assert r.status_code == 409 and r.json()["detail"] == "Create a version first to enable comparison."
