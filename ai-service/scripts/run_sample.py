"""Generate docs from an analysis JSON file without starting the server.

Usage (from the ai-service folder):
    python scripts/run_sample.py                        # uses sample_data/sample_analysis.json
    python scripts/run_sample.py path/to/analysis.json  # e.g. real output from LD-328

Uses Claude when ANTHROPIC_API_KEY is set, otherwise the offline generator.
Writes the Markdown to output.md and prints the job status and warnings.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.jobs import jobs, run_job  # noqa: E402
from app.models import GenerateRequest  # noqa: E402

path = Path(sys.argv[1] if len(sys.argv) > 1 else "sample_data/sample_analysis.json")
req = GenerateRequest.model_validate(json.loads(path.read_text(encoding="utf-8")))
job = jobs.create(req)
run_job(job.id, req)
job = jobs.get(job.id)

print(f"Status : {job.status.value} - {job.message}")
for r in job.file_results:
    print(f"  {r.status.value:<9} {r.path}")
for w in job.warnings:
    print(f"  ! {w}")
if job.error:
    print(f"Error  : {job.error}")
if job.result:
    Path("output.md").write_text(job.result, encoding="utf-8")
    print("Markdown written to output.md")
