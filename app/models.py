from typing import List, Optional
from pydantic import BaseModel

class Function(BaseModel):
    name: str
    start_line: int
    end_line: int

class ClassInfo(BaseModel):
    name: str
    methods: List[Function] = []

class FileAnalysis(BaseModel):
    file_path: str
    classes: List[ClassInfo] = []
    functions: List[Function] = []

class RepoAnalysisRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = "main"

class RepoAnalysisResponse(BaseModel):
    files: List[FileAnalysis] = []
