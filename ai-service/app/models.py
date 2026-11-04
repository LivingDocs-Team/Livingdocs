"""AI Service data models."""
from pydantic import BaseModel, Field
from typing import List, Optional

class EvidenceItem(BaseModel):
    source: str
    relevance: float
    snippet: str

class ExplanationResponse(BaseModel):
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[EvidenceItem] = []
