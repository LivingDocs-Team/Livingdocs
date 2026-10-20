from typing import List, Optional
from pydantic import BaseModel, Field

class FileInput(BaseModel):
    path: str
    content: str
    language: Optional[str] = None

class RepoAnalysisRequest(BaseModel):
    target: str = Field(..., description="Repository name, e.g. acme/shop")
    scope: str = Field("repository", description="file | module | repository")
    files: List[FileInput] = Field(default_factory=list)
    file_paths: List[str] = Field(default_factory=list)
    options: Optional[dict] = Field(default_factory=dict)

class Parameter(BaseModel):
    name: str
    type: Optional[str] = None
    default: Optional[str] = None
    description: Optional[str] = None

class Function(BaseModel):
    name: str
    signature: Optional[str] = None
    parameters: List[Parameter] = Field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    source: Optional[str] = None
    lineno: Optional[int] = None
    end_lineno: Optional[int] = None

class ClassInfo(BaseModel):
    name: str
    bases: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    methods: List[Function] = Field(default_factory=list)

class Endpoint(BaseModel):
    http_method: str
    path: str
    handler: Optional[str] = None
    parameters: List[Parameter] = Field(default_factory=list)
    request_body: Optional[str] = None
    response: Optional[str] = None

class FileAnalysis(BaseModel):
    path: str
    language: Optional[str] = None
    module: Optional[str] = None
    status: str = "ok"
    error: Optional[str] = None
    classes: List[ClassInfo] = Field(default_factory=list)
    functions: List[Function] = Field(default_factory=list)
    endpoints: List[Endpoint] = Field(default_factory=list)

class RepoAnalysisResponse(BaseModel):
    scope: str
    target: str
    files: List[FileAnalysis] = Field(default_factory=list)