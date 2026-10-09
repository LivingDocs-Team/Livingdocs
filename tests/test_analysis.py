from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_python_analysis():
    code = "import math\ndef add(a, b): return a + b"
    res = client.post("/api/v1/analyze", json={"code": code, "language": "python"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "math" in data["dependencies"]

def test_java_analysis():
    code = "import java.util.List; public class Demo {}"
    res = client.post("/api/v1/analyze", json={"code": code, "language": "java"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "java.util.List" in data["dependencies"]
