# Repository documentation generation API

The GitHub Integration Service coordinates repository analysis and AI documentation generation.
The browser calls these endpoints through the authenticated Backend BFF. The Backend derives
`X-User-Id` from its verified session and sends it with the internal service credential. Direct
requests without that credential are rejected by GitHub Integration.

## Start generation

Generate only from the latest successful repository sync:

```http
POST /api/repositories/{repositoryId}/documentation/generate
Content-Type: application/json
```

Optional request body:

```json
{"templateId":"default","outputLanguage":"vi"}
```

`templateId` and `outputLanguage` may be omitted. The AI service defaults are `default` and `vi`.
The selected repository must belong to the user and must have a latest sync with source content.
Run `POST /api/repositories/{repositoryId}/sync` first when the latest snapshot is unavailable.

The service converts synchronized source files to `AnalysisInput`, posts them to the Code Analyzer
at `POST /api/v1/analyze-repo`, then forwards the analyzer response to the AI service at
`POST /generate`. The response is HTTP `202 Accepted` with the AI job, including its `id` and
`status`.

## Poll and fetch the result

| Method | Endpoint | Response |
|---|---|---|
| GET | `/api/documentation/jobs/{jobId}` | AI job status and progress |
| GET | `/api/documentation/jobs/{jobId}/result` | Generated Markdown (`text/markdown`), only after completion |
| GET | `/api/documentation/jobs/{jobId}/report` | AI evidence and confidence report, only after completion |

The job can only be fetched by the user who started it. Job ownership is held in service memory;
restarting either service loses its jobs, so generate again after a restart.

## Errors

Errors use `{status, code, message, timestamp}`. Repository ownership/not-found and missing-sync
errors retain their repository API status. Empty source input returns `400 BAD_REQUEST`. Analyzer
and AI failures return `502` with stable codes such as `ANALYZER_FAILED`,
`ANALYZER_INVALID_RESPONSE`, `AI_SERVICE_FAILED`, or `AI_SERVICE_INVALID_RESPONSE`; upstream
exception details and credentials are not returned to the caller.

Configure `CODE_ANALYZER_BASE_URL` and `AI_SERVICE_BASE_URL` for the GitHub Integration Service.
The defaults target local development ports `8000` and `8001`; Compose sets the service DNS names.

## Local Compose verification

After preparing the root `.env` with the required project configuration, validate and start only
the services needed for this workflow:

```powershell
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml up --build -d backend-db github-db backend ai-service code-analyzer github-integration frontend
docker compose -f compose.yaml ps
curl.exe -fsS http://localhost:8000/openapi.json
curl.exe -fsS http://localhost:8001/health
```

Then connect GitHub, add a repository to the workspace, synchronize it, and start generation
through `POST /api/repositories/{repositoryId}/documentation/generate`. A successful health check
proves service availability only; it does not prove the GitHub-to-documentation workflow.
