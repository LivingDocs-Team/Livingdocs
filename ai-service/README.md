# LivingDocs AI Service (LD-90, LD-340)

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
| GET/POST | `/templates` | List / create templates |
| GET/PUT/DELETE | `/templates/{id}` | Read / update / delete (built-ins are read-only) |

Built-in templates: `default`, `api-reference`, `brief`.

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

Environment variables: `ANTHROPIC_API_KEY`, `LLM_MODEL` (default `claude-sonnet-5-5`),
`LLM_MAX_TOKENS` (4096), `LLM_TIMEOUT` seconds (60), `LLM_MAX_ATTEMPTS` (3).

## Notes / next steps

- Jobs and templates are stored in memory; they reset on restart. Swap `JobStore` /
  `TemplateStore` for a database when the backend is ready.
- The `files` input format should match what the LivingDocs code analyzer outputs.
