from pathlib import Path

from scripts.check_documentation_drift import ROOT, check_file


def test_existing_local_markdown_link_passes(tmp_path: Path):
    target = tmp_path / "target.md"
    target.write_text("# target", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text("[target](target.md)\n", encoding="utf-8")
    assert check_file(source) == []


def test_missing_local_markdown_link_is_reported(tmp_path: Path):
    source = tmp_path / "README.md"
    source.write_text("[missing](missing.md)\n", encoding="utf-8")
    errors = check_file(source)
    assert len(errors) == 1
    assert "missing local link" in errors[0]
