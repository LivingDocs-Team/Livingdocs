import os
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI, APIRouter, HTTPException, status

from app.models import (
    EvidenceResponse,
    EvidenceCreate,
    SubmissionResponse,
    SubmissionCreate,
    SubmissionStatus,
    RepoAnalysisRequest,
    RepoAnalysisResponse,
    FileAnalysis,
)
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
router = APIRouter(prefix="/api/v1", tags=["Evidence & Submission"])

db_evidences = {}
db_submissions = {}

@router.post("/evidences", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def create_evidence(payload: EvidenceCreate):
    evidence_id = f"ev-{uuid.uuid4().hex[:8]}"
    evidence_data = EvidenceResponse(
        id=evidence_id,
        created_at=datetime.now(timezone.utc),
        **payload.model_dump()
    )
    db_evidences[evidence_id] = evidence_data
    return evidence_data

@router.post("/submissions", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_submission(payload: SubmissionCreate):
    missing_evidences = [ev_id for ev_id in payload.evidence_ids if ev_id not in db_evidences]
    if missing_evidences:
        raise HTTPException(
            status_code=400, 
            detail=f"Các Evidence ID sau không tồn tại: {missing_evidences}"
        )

    sub_id = f"sub-{uuid.uuid4().hex[:8]}"
    evidences_list = [db_evidences[ev_id] for ev_id in payload.evidence_ids]
    
    submission_data = SubmissionResponse(
        id=sub_id,
        task_id=payload.task_id,
        title=payload.title,
        status=SubmissionStatus.DRAFT,
        evidences=evidences_list,
        created_at=datetime.now(timezone.utc)
    )
    db_submissions[sub_id] = submission_data
    return submission_data

@router.post("/submissions/{submission_id}/submit", response_model=SubmissionResponse)
async def submit_submission(submission_id: str):
    if submission_id not in db_submissions:
        raise HTTPException(status_code=404, detail="Submission không tồn tại")
    
    sub = db_submissions[submission_id]
    if not sub.evidences:
        raise HTTPException(status_code=400, detail="Cần ít nhất 1 evidence để thực hiện submit")
    
    sub.status = SubmissionStatus.SUBMITTED
    sub.submitted_at = datetime.now(timezone.utc)
    db_submissions[submission_id] = sub
    return sub

# Đăng ký router vào FastAPI app
app.include_router(router)