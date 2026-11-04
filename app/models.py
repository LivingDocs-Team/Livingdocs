"""Pydantic data models for API payloads."""
from pydantic import BaseModel
from typing import List, Optional

class Issue(BaseModel):
    line: int
    severity: str
    message: str
    rule_id: str

class AnalysisRequest(BaseModel):
    code: str
    language: str

class AnalysisResponse(BaseModel):
    issues: List[Issue]
    score: int
