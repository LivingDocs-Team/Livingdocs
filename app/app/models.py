from typing import List, Optional
from pydantic import BaseModel, Field

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
    status: str = "ok"  # ok | empty | invalid | unsupported
    error: Optional[str] = None
    classes: List[ClassInfo] = Field(default_factory=list)
    functions: List[Function] = Field(default_factory=list)
    endpoints: List[Endpoint] = Field(default_factory=list)
