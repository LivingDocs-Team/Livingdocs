
import os

from fastapi import FastAPI, HTTPException, status

from app.models import RepoAnalysisRequest, RepoAnalysisResponse, FileAnalysis
from app.analyzer import ASTAnalyzer
from app.reader import FileReader
from app.extractor import EntityExtractor
from app.java_extractor import extract_java


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
    warnings = []
    seen_paths = set()

    for file_input in request.files:
        # The same path twice would make the AI service reject the whole request: keep the first.
        if file_input.path in seen_paths:
            warnings.append(f"{file_input.path}: duplicate path, only the first copy was analyzed.")
            continue
        seen_paths.add(file_input.path)

        # Detect the language if the client did not provide one ("Python" == "python").
        lang = (
            (file_input.language or "").strip().lower()
            or FileReader.detect_language(file_input.path)
        )
        # Files saved on Windows may start with a UTF-8 byte order mark.
        content = file_input.content.lstrip("\ufeff")

        # Handle empty files.
        if not content.strip():
            analyzed_files.append(
                FileAnalysis(
                    path=file_input.path,
                    language=lang,
                    status="empty",
                    error="File rỗng, không có nội dung để phân tích.",
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
                    error=(f"Language '{lang}' is not supported "
                           f"(file extension '{os.path.splitext(file_input.path)[1] or '-'}')."),
                )
            )
            continue

        # Parse the source code into an AST.
        tree, error = ASTAnalyzer.parse_code(content, lang)

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
                EntityExtractor.extract_python_entities(tree, content)
            )
            module = python_module(file_input.path)
        else:
            classes, functions, endpoints, package = extract_java(tree, content)
            module = package or java_module(file_input.path)

        analyzed_files.append(
            FileAnalysis(
                path=file_input.path,
                language=lang,
                module=module,
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
        warnings=warnings,
    )


def python_module(path: str):
    """app/services/cart.py -> app.services.cart ; pkg/__init__.py -> pkg"""
    stem = path.replace("\\", "/").lstrip("./").rsplit(".", 1)[0]
    if stem.startswith("src/"):
        stem = stem[4:]
    parts = [p for p in stem.split("/") if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or None


def java_module(path: str):
    """Package folder when the file has no package declaration."""
    p = path.replace("\\", "/")
    for root in ("src/main/java/", "src/test/java/"):
        if root in p:
            p = p.split(root, 1)[1]
            break
    folder = p.rsplit("/", 1)[0] if "/" in p else ""
    return folder.replace("/", ".") or None
