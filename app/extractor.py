"""Python AST code extractor."""
import ast
from typing import List
from app.models import Issue

class PythonASTExtractor:
    def extract_issues(self, code: str) -> List[Issue]:
        issues = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and node.type is None:
                    issues.append(Issue(
                        line=node.lineno,
                        severity="warning",
                        message="Bare except block detected",
                        rule_id="PY-W101"
                    ))
        except SyntaxError as e:
            issues.append(Issue(
                line=e.lineno or 1,
                severity="error",
                message=f"Syntax error: {e.msg}",
                rule_id="PY-E001"
            ))
        return issues
