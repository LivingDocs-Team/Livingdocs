from typing import List, Optional
from pydantic import BaseModel

class Function(BaseModel):
    name: str
    lineno: int
    end_lineno: int
    source: Optional[str] = None  # Mã nguồn thực tế của hàm

class Endpoint(BaseModel):
    path: str
    method: str

class ClassInfo(BaseModel):
    name: str
    methods: List[Function] = []

class FileAnalysis(BaseModel):
    path: str
    language: Optional[str] = "python"
    status: Optional[str] = "analyzed"
    classes: List[ClassInfo] = []
    functions: List[Function] = []
    endpoints: List[Endpoint] = []

class RepoAnalysisRequest(BaseModel):
    target: str          # Chuỗi định danh target / repo URL
    scope: Optional[str] = "full"
    files: Optional[List[str]] = None

class RepoAnalysisResponse(BaseModel):
    target: str
    scope: str
    files: List[FileAnalysis] = []
