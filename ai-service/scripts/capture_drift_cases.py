"""Refresh the analyzer output of the drift fixture cases (LD-347) from the real analyzer (LD-328).

Every folder of ai-service/tests/fixtures/drift_cases/ holds `before.py` / `after.py` (the
changed file at the base and head commit). This script writes `before.json` / `after.json`, the
analyzer's result for each, which tests/test_drift_cases.py feeds to drift detection.

Run from the repository root (the analyzer package is the top-level `app/`):

    python ai-service/scripts/capture_drift_cases.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = ROOT / "ai-service/tests/fixtures/drift_cases"


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from app.main import app  # analyzer service (repository root), not ai-service

    client = TestClient(app)
    for case in sorted(p for p in CASES.iterdir() if p.is_dir()):
        meta = json.loads((case / "case.json").read_text(encoding="utf-8"))
        for side, path in (("before", meta.get("previous_path") or meta["path"]), ("after", meta["path"])):
            body = {"scope": "repository", "target": "acme/shop",
                    "files": [{"path": path, "language": "python",
                               "content": (case / f"{side}.py").read_text(encoding="utf-8")}]}
            r = client.post("/api/v1/analyze-repo", json=body)
            r.raise_for_status()
            [result] = r.json()["files"]
            (case / f"{side}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
        print(f"wrote {case.relative_to(ROOT)}/before.json, after.json")


if __name__ == "__main__":
    main()
