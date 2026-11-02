from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# ==========================================
# 1. Models cho Code Analyzer (Hợp đồng LD-395)
# ==========================================

class FileInput(BaseModel):
    path: str = Field(..., example="app/models.py")
    language: str = Field(..., example="python")
    content: str = Field(..., example="class MyModel: pass")

class Parameter(BaseModel):
    name: str
    type: Optional[str] = None
    default: Optional[str] = None

class FunctionInfo(BaseModel):
    name: str
    signature: str
    parameters: List[Parameter] = []
    return_type: Optional[str] = None
    lineno: int
    end_lineno: int

class ClassInfo(BaseModel):
    name: str
    docstring: Optional[str] = None
    methods: List[FunctionInfo] = []

class CodeAnalysisResult(BaseModel):
    files: List[FileInput]
    classes: List[ClassInfo] = []
    functions: List[FunctionInfo] = []

# ==========================================
# 2. Models cho Grounding Evidence & Submission (LD-106)
# ==========================================

class GroundingEvidence(BaseModel):
    file_path: str = Field(..., example="app/models.py")
    start_line: int = Field(..., ge=1, example=10)
    end_line: int = Field(..., ge=1, example=25)
    code_snippet: str = Field(..., example="def create_evidence(): pass")
    job_id: str = Field(..., example="job-106-xyz")
    repository_url: str = Field(..., example="https://github.com/org/repo")
    commit_hash: str = Field(..., example="a1b2c3d4e5f6")

class GenerationStatusResponse(BaseModel):
    job_id: str
    document_id: str
    status: str  # pending, processing, completed, failed
    progress_percentage: float = Field(..., ge=0.0, le=100.0)
    files_processed: int
    total_files: int
    repository_url: str
    commit_hash: str

class DocumentationSubmissionRequest(BaseModel):
    job_id: str
    document_id: str
    author: str
    evidences: List[GroundingEvidence]
    notes: Optional[str] = None
