import pytest
from app.analyzer import CodeAnalyzer
from app.models import AnalysisRequest

def test_python_bare_except():
    analyzer = CodeAnalyzer()
    code = "try:\n    x = 1 / 0\nexcept:\n    pass"
    req = AnalysisRequest(code=code, language="python")
    res = analyzer.analyze(req)
    assert len(res.issues) == 1
    assert res.issues[0].rule_id == "PY-W101"

def test_java_system_out():
    analyzer = CodeAnalyzer()
    code = 'public class Test { public static void main(String[] args) { System.out.println("Hello"); } }'
    req = AnalysisRequest(code=code, language="java")
    res = analyzer.analyze(req)
    assert len(res.issues) == 1
    assert res.issues[0].rule_id == "JAVA-I101"
