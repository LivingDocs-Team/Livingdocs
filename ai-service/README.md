# LivingDocs AI Service (LD-90)

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
pytest -q
```

## Notes / next steps

- Jobs and templates are stored in memory; they reset on restart. Swap `JobStore` /
  `TemplateStore` for a database when the backend is ready.
- The `files` input format should match what the LivingDocs code analyzer outputs.
