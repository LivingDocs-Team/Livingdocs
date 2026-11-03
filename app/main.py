import os

# Cấu hình API Key cho AI Service
AI_API_KEY = os.getenv("AI_SERVICE_API_KEY", "AQ.Ab8RN6KTUwn0WoljiN33D1g-jtHNCURHFJg6tPWjNexfbviDYg")
from fastapi import FastAPI, HTTPException, status

from app.models import RepoAnalysisRequest, RepoAnalysisResponse, FileAnalysis
from app.analyzer import ASTAnalyzer
from app.reader import FileReader
from app.extractor import EntityExtractor


app = FastAPI(
    title="Source Code Analysis Service",
    version="1.0.0",
)


@app.get("/health", tags=["health"])
async def health():
    """Liveness probe used by Docker Compose and other services."""
    return {"status": "ok", "service": "code-analyzer"}


@app.post("/api/v1/analyze-repo", response_model=RepoAnalysisResponse)
async def analyze_repository(request: RepoAnalysisRequest):
    """Analyze repository files according to the input contract."""

    if not request.files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The list of files to analyze must not be empty.",
        )

    analyzed_files = []

    for file_input in request.files:
        # Detect the language if the client did not provide one.
        lang = (
            file_input.language
            or FileReader.detect_language(file_input.path)
        )

        # Handle empty files.
        if not file_input.content.strip():
            analyzed_files.append(
                FileAnalysis(
                    path=file_input.path,
                    language=lang,
                    status="empty",
                )
            )
            continue

        # Handle unsupported languages.
        if lang not in ("python", "java"):
            analyzed_files.append(
                FileAnalysis(
                    path=file_input.path,
                    language=lang,
                    status="unsupported",
                    error=f"Language '{lang}' is not supported.",
                )
            )
            continue

        # Parse the source code into an AST.
        tree, error = ASTAnalyzer.parse_code(file_input.content, lang)

        if error:
            analyzed_files.append(
                FileAnalysis(
                    path=file_input.path,
                    language=lang,
                    status="invalid",
                    error=error,
                )
            )
            continue

        # Extract classes, functions, and endpoints.
        if lang == "python":
            classes, functions, endpoints = (
                EntityExtractor.extract_python_entities(
                    tree,
                    file_input.content,
                )
            )
        else:
            classes, functions, endpoints = (
                EntityExtractor.extract_java_entities(
                    tree,
                    file_input.content,
                )
            )

        analyzed_files.append(
            FileAnalysis(
                path=file_input.path,
                language=lang,
                status="ok",
                classes=classes,
                functions=functions,
                endpoints=endpoints,
            )
        )
    return RepoAnalysisResponse(
        scope=request.scope,
        target=request.target,
        files=analyzed_files,
    )
    # Bổ sung các Route Healthcheck phục vụ CI Test
@app.get("/")
async def root():
    return {"status": "ok", "generator": "online"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}
