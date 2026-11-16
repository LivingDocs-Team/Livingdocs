import os
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, status

from app.models import (
    EvidenceResponse,
    EvidenceCreate,
    SubmissionResponse,
    SubmissionCreate,
    RepoAnalysisRequest,
    RepoAnalysisResponse,
    FileAnalysis,
)
from app.analyzer import ASTAnalyzer
from app.reader import FileReader
from app.extractor import EntityExtractor
from app.java_extractor import extract_java
from app.submissions import SubmissionError, submissions


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
        if file_input.path in seen_paths:
            warnings.append(f"{file_input.path}: duplicate path, only the first copy was analyzed.")
            continue
        seen_paths.add(file_input.path)

        lang = (
            (file_input.language or "").strip().lower()
            or FileReader.detect_language(file_input.path)
        )
        content = file_input.content.lstrip("\ufeff")

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


# --- EVIDENCE & SUBMISSION ROUTER ---
# LD-402: stored by app/submissions.py in SUBMISSIONS_FILE (survives a restart), not in memory.
router = APIRouter(prefix="/api/v1", tags=["Evidence & Submission"])


def _call(fn, *args):
    try:
        return fn(*args)
    except SubmissionError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@router.post("/evidences", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def create_evidence(payload: EvidenceCreate):
    return _call(submissions.add_evidence, payload)


@router.get("/evidences/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(evidence_id: str):
    return _call(submissions.evidence, evidence_id)


@router.post("/submissions", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_submission(payload: SubmissionCreate):
    return _call(submissions.add_submission, payload)


@router.get("/submissions", response_model=List[SubmissionResponse])
async def list_submissions(task_id: Optional[str] = None):
    return submissions.submissions(task_id)


@router.get("/submissions/{submission_id}", response_model=SubmissionResponse)
async def get_submission(submission_id: str):
    return _call(submissions.submission, submission_id)


@router.post("/submissions/{submission_id}/submit", response_model=SubmissionResponse)
async def submit_submission(submission_id: str):
    return _call(submissions.submit, submission_id)


# Đăng ký router vào FastAPI app
app.include_router(router)
