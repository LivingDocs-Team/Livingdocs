"""Refresh tests/integration/fixtures/analyzer_output.json from the real analyzer (LD-328).

Run from the repository root (the analyzer package is the top-level `app/`):

    python ai-service/scripts/capture_analyzer_output.py

The fixture is what the in-process integration tests feed into POST /generate, so
re-run this whenever the analyzer output format changes.
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = pathlib.Path("ai-service/tests/integration/fixtures")
FILES = ["cart_service.py", "routes.py", "OrderController.java", "broken.py", "empty.py", "widget.js"]


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from app.main import app  # analyzer service (repository root), not ai-service

    # paths are relative to the fixtures folder, like paths inside a real repository
    os.chdir(ROOT / FIXTURES)
    paths = [f"shop/{name}" for name in FILES]
    body = {"scope": "repository", "target": "acme/shop",
            "file_paths": paths,  # LD-328 input
            "files": [{"path": p, "content": pathlib.Path(p).read_text(encoding="utf-8")}
                      for p in paths]}  # LD-395 input
    r = TestClient(app).post("/api/v1/analyze-repo", json=body)
    r.raise_for_status()
    out = ROOT / FIXTURES / "analyzer_output.json"
    out.write_text(json.dumps(r.json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(r.json()['files'])} files)")


if __name__ == "__main__":
    main()
