"""Core analyzer implementation."""
import ast
from typing import List, Dict, Any
from app.models import AnalysisRequest, AnalysisResponse, Issue
from app.extractor import PythonASTExtractor
from app.java_extractor import JavaASTExtractor

class CodeAnalyzer:
    def __init__(self):
        self.py_extractor = PythonASTExtractor()
        self.java_extractor = JavaASTExtractor()

    def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        issues = []
        if request.language == "python":
            issues = self.py_extractor.extract_issues(request.code)
        elif request.language == "java":
            issues = self.java_extractor.extract_issues(request.code)
        return AnalysisResponse(issues=issues, score=max(0, 100 - len(issues) * 10))
