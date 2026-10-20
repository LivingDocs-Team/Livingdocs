# Livingdocs
BLCK

## Local Docker Verification

Start the full local MVP stack:

```powershell
docker compose up --build -d
```

Check service status:

```powershell
docker compose ps
```

Expected result:
- `backend` is healthy
- `backend-db` is healthy
- `code-analyzer` is healthy
- `ai-service` is healthy
- `github-integration` is healthy
- `github-db` is healthy
- `frontend` is running

Verify Code Analyzer:

```powershell
curl.exe -fsS http://localhost:8000/health
```

Verify AI service:

```powershell
curl.exe -fsS http://localhost:8001/health
```

Verify backend:

```powershell
curl.exe -fsS http://localhost:8080/actuator/health
```

Verify GitHub Integration:

```powershell
curl.exe -fsS http://localhost:8082/actuator/health
```

Verify frontend:

```powershell
curl.exe -I http://localhost:3000
```

Verify backend-to-Code-Analyzer Docker networking:

```powershell
docker compose exec backend curl -fsS http://code-analyzer:8000/health
```

The backend should be able to resolve `code-analyzer` by Docker Compose service name and receive:

```json
{"status":"ok"}
```

Stop the local stack:

```powershell
docker compose down
```