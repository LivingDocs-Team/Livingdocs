"""Refresh the analyzer results of the drift fixture cases (LD-347) from the real analyzer (LD-328).

ai-service/tests/fixtures/drift_cases.json holds every case: the changed file at the base and
head commit (`before` / `after`), the documentation, and the expected findings. This script adds
`before_analysis` / `after_analysis`, the analyzer's result for each side, which
tests/test_drift_cases.py feeds to drift detection ("analysis" mode).

Run from the repository root (the analyzer package is the top-level `app/`):

    python ai-service/scripts/capture_drift_cases.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = ROOT / "ai-service/tests/fixtures/drift_cases.json"


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from app.main import app  # analyzer service (repository root), not ai-service

    client = TestClient(app)
    data = json.loads(CASES.read_text(encoding="utf-8"))
    for case in data["cases"]:
        for side, path in (("before", case.get("previous_path") or case["path"]), ("after", case["path"])):
            body = {"scope": "repository", "target": "acme/shop",
                    "files": [{"path": path, "language": "python", "content": case[side]}]}
            r = client.post("/api/v1/analyze-repo", json=body)
            r.raise_for_status()
            [result] = r.json()["files"]
            case[f"{side}_analysis"] = result
    CASES.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {CASES.relative_to(ROOT)} ({len(data['cases'])} cases)")


if __name__ == "__main__":
    main()
