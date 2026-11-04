"""Java code static extractor using regex heuristics."""
import re
from typing import List
from app.models import Issue

class JavaASTExtractor:
    def extract_issues(self, code: str) -> List[Issue]:
        issues = []
        lines = code.splitlines()
        for idx, line in enumerate(lines, 1):
            if "System.out.println" in line:
                issues.append(Issue(
                    line=idx,
                    severity="info",
                    message="Avoid using System.out.println for logging",
                    rule_id="JAVA-I101"
                ))
            if "catch (Exception e)" in line and "e.printStackTrace()" in line:
                issues.append(Issue(
                    line=idx,
                    severity="warning",
                    message="Catching generic Exception and printing stack trace",
                    rule_id="JAVA-W202"
                ))
        return issues
