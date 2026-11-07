# LivingDocs AI Service (LD-90, LD-340, LD-195, LD-145)

AI-assisted documentation generation. Takes source code that has already been analyzed
(classes, methods, endpoints, parameters, return values) and produces Markdown docs
using a managed template. Generation runs as a background job with status and progress.

## Run

```bash
cd ai-service
python -m venv venv
source venv/Scripts/activate      # Windows Git Bash / MSYS2; on Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Open http://localhost:8001/docs to try the API.

**Dependencies (DOCKER-03).** `requirements.txt` pins every package (direct and indirect) to an
exact version, so local, CI and Docker builds use the same libraries. Do not edit it by hand: change
the direct dependencies in `requirements.in`, then regenerate:

```bash
pip install uv
uv pip compile requirements.in --python-version 3.12 --python-platform linux -o requirements.txt
```

`tests/test_requirements_pinned.py` fails if a line in `requirements.txt` is not pinned with `==`.

Without `ANTHROPIC_API_KEY` the service uses a rule-based offline generator (good for
development and tests). Set the key to use Claude:

```bash
export ANTHROPIC_API_KEY=...        # never commit this; put it in .env
export LLM_MODEL=claude-sonnet-5-5  # optional
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/generate` | Start a job for a `file`, `module` or `repository` |
| GET | `/jobs` | List jobs |
| GET | `/jobs/{id}` | Status, progress, message, error, result |
| GET | `/jobs/{id}/result` | Generated Markdown |
| GET | `/jobs/{id}/report` | Evidence and confidence per file and entity |
| GET/POST | `/templates` | List (built-in first, then custom by name) / create templates |
| GET | `/templates/sections` | Sections a template may contain |
| GET/PUT/DELETE | `/templates/{id}` | Read / update / delete (built-ins are read-only) |
| POST | `/documents` | Save a completed job as version 1 of a document (LD-195) |
| GET | `/documents`, `/documents/{id}` | List / read documents |
| GET | `/documents/{id}/content?version=N` | Markdown of the current (or given) version |
| GET | `/documents/{id}/versions`, `/versions/{n}` | Version history (newest first) / one version |
| GET | `/documents/{id}/history` | Audit trail: created, proposed, accepted, edited, dismissed, ... |
| POST | `/drift/changes` | Changed code entities of a Pull Request (LD-146); nothing is stored |
| POST | `/drift/analyze` | Drift report of a Pull Request: findings, affected docs, evidence (LD-147/148/149) |
| GET | `/drift/reports?repository=&pull_request=` | Drift reports, newest first |
| GET | `/drift/reports/{id}` | One drift report |

Built-in templates: `default`, `api-reference`, `brief`.

### Documentation templates

A template = `name` (unique, case-insensitive), `description`, `instructions` (writing style
for the AI) and an ordered list of `sections` taken from `Overview`, `Classes`, `Functions`,
`API Endpoints` (any letter case is accepted and stored in this spelling).

- Every generated file has exactly the template's sections, in the template's order. The prompt
  tells the AI which parts to fill; warnings and confidence scores cover only the entities the
  template documents (e.g. `api-reference` scores endpoints only).
- A job keeps a snapshot of its template (`template_id`, `template_name`, `template_sections` on
  the job, `template_id` / `template_name` on the report): editing or deleting the template
  later does not change a running job. The repository overview names the template used.
- Custom templates are saved to `TEMPLATES_FILE` (default `data/templates.json`, written
  atomically) and survive a restart. Set `TEMPLATES_FILE=` (empty) to keep them in memory only.
  An unreadable file is renamed to `templates.corrupt-<time>.json` and the service starts with
  the built-in templates.
- Errors: `422` invalid template, `409` duplicate name, `403` built-in template, `404` unknown id.

### Versioned documentation (LD-195)

- `POST /documents {"job_id": ...}` stores a completed job as **version 1** (accepted). Every later
  change adds a new, immutable version; nothing is edited in place or deleted (LD-195).
- Saved to `DOCUMENTS_FILE` (default `data/documents.json`, atomic writes; empty = memory only).
- Details: `Docs/Linh/` FR6.md.

### Documentation drift detection (LD-145)

Checks whether a Pull Request makes existing documentation outdated.

```
PR files (patch + analyzer result at base/head)
  -> LD-146 app/drift_changes.py   changed entities: added / removed / renamed /
                                   signature_changed / behavior_changed
  -> LD-148 app/drift_affected.py  saved document sections + repository Markdown that name them
  -> LD-147 app/drift.py           findings: type, severity, confidence
  -> LD-149 app/drift_evidence.py  code diff, documentation passage, commit, Jira ticket
```

- **Input** (`DriftAnalyzeRequest`): `pull_request` (number, title, branch, `head_sha`, url, ...),
  `files[]` with `path`, `status` (GitHub values), `previous_path`, `patch` (unified diff) and
  optionally `before` / `after` (analyzer `FileAnalysis`, see [CONTRACT.md](CONTRACT.md)). With
  `before`/`after` the comparison is exact; with only `patch`, Python and Java declarations are read
  from the diff (confidence x0.8). `docs[]`: Markdown files of the repository; `document_ids`:
  saved documents to check (omit = all).
- **Types** (BR-49): *Referential* (removed / renamed code, moved endpoint, deleted or moved file
  still named), *Signature* (parameters, return type, fields, endpoint contract changed), *Semantic*
  (body or docstring changed, or a new entity is not described in its file's section).
- **Severity** Low < Medium < High < Critical: removed/renamed entity High (endpoint Critical);
  signature Medium (endpoint +1, the docs still name a removed parameter +1); behaviour Low
  (docstring changed +1, >= 15 changed lines +1); private `_name` -1. Rules: `app/drift.py`.
- **Confidence** 0-1 = match x method x location x certainty; levels as LD-340 (high >= 0.75,
  medium >= 0.50). Every finding has `factors` explaining the score.
- **Evidence** (BR-50): `X1` code diff of the entity (without a diff: signature and docstring
  before -> after), `D1..` documentation lines, `C1` commit / PR link, `T1..` Jira keys from the PR
  title, branch and description.
- Matching avoids false positives: whole identifiers only, common words (`add`, `run`) only in
  code / headings, bare method names only in the section of their own file, endpoint paths match
  any placeholder style (`{id}`, `:id`, `<id>`).
- Reports are kept in memory (last 500); history and resolution of drift are LD-167.
- Tests (LD-150): `tests/test_drift.py`, `tests/test_drift_api.py`,
  `tests/integration/test_drift_integration.py`, live: `test_live_pipeline.py`.

### Example request

```json
POST /generate
{
  "scope": "file",
  "target": "src/users/service.py",
  "template_id": "default",
  "output_language": "vi",
  "files": [{
    "path": "src/users/service.py",
    "language": "python",
    "classes": [{"name": "UserService", "methods": [
      {"name": "get_user", "parameters": [{"name": "user_id", "type": "int"}], "return_type": "User"}
    ]}],
    "endpoints": [{"http_method": "GET", "path": "/users/{id}", "response": "User JSON"}]
  }]
}
```

Poll `GET /jobs/{id}` until `status` is `completed` (or `failed`), then read `/jobs/{id}/result`.

## Tests

```bash
pytest -q                      # unit + in-process integration tests (no network)
```

### Integration tests (LD-390)

`tests/integration/` checks the AI service together with the analyzer (LD-328). Details and the
list of test cases: [`tests/integration/README.md`](tests/integration/README.md).

```bash
# two services running (CI job `ai-service-integration` does this automatically)
ANALYZER_URL=http://localhost:8000 AI_SERVICE_URL=http://localhost:8001 pytest -m live -v

# real Claude API, by hand only
RUN_LLM_TESTS=1 ANTHROPIC_API_KEY=... pytest -m llm -v
```

## Documentation generation (LD-340)

```
analysis (LD-328) -> prompt -> Claude -> JSON (FileDoc) -> validate -> Markdown renderer
```

- `app/prompts.py`: system prompt and per-file prompt (JSON-only output, no invented entities,
  output language, template style; long source snippets are truncated).
- `app/doc_schema.py`: the JSON shape the AI must return and its parser/validator.
- `app/renderer.py`: deterministic Markdown. Names, types and section order come from the
  analysis and template, so every file has the same structure; the AI only adds descriptions.
- `app/generator.py`: retries on API errors (exponential backoff) and on invalid JSON (repair
  prompt). After `LLM_MAX_ATTEMPTS` (default 3) it falls back to analysis-only docs.
- Files with analyzer `status` other than `ok` are skipped and reported; one failing file never
  stops the job. Every job exposes `warnings` and per-file `file_results`.
- `app/retrieval.py`: for each file, retrieves related code from other analyzed files and the most
  relevant passages of existing docs passed in `context` (TF-IDF over identifier-aware tokens,
  no external service). They go into the prompt as citable context.
- `app/evidence.py`: evidence catalog per file — `E` = the entity's own code (file + lines),
  `C` = retrieved related code, `D` = retrieved documentation. The AI must cite ids for every
  description; unknown ids are dropped and reported.
- `app/confidence.py`: 0-1 confidence per entity, file and job, mostly from checkable signals
  (input quality, evidence grounding, whether it was described) plus the AI's self-assessment.
  Shown in the Markdown and returned by `GET /jobs/{id}/report`.

Input format agreed with LD-328: see [CONTRACT.md](CONTRACT.md).

Try it without the server:

```bash
python scripts/run_sample.py                          # sample_data/sample_analysis.json -> output.md
python scripts/run_sample.py path/to/real_analysis.json
```

Environment variables: `TEMPLATES_FILE` (default `data/templates.json`), `ANTHROPIC_API_KEY`, `LLM_MODEL` (default `claude-sonnet-5-5`),
`LLM_MAX_TOKENS` (4096), `LLM_TIMEOUT` seconds (60), `LLM_MAX_ATTEMPTS` (3).

## Notes / next steps

- Jobs and drift reports are stored in memory and reset on restart. Custom templates are saved to
  `TEMPLATES_FILE`; templates are shared by all users (the AI service has no user accounts).
- The `files` input format should match what the LivingDocs code analyzer outputs.
