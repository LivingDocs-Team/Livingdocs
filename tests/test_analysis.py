from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_unsupported_file():
    response = client.post("/api/v1/analyze-repo", json={
        "scope": "file",
        "target": "test",
        "files": [{
            "path": "main.rb",
            "content": "puts 'hello'",
            "language": "ruby"
        }]
    })

    assert response.status_code == 200
    assert response.json()["files"][0]["status"] == "unsupported"


def test_empty_content_file():
    response = client.post("/api/v1/analyze-repo", json={
        "scope": "file",
        "target": "test",
        "files": [{
            "path": "empty.py",
            "content": "",
            "language": "python"
        }]
    })

    assert response.status_code == 200
    assert response.json()["files"][0]["status"] == "empty"


def test_empty_files_returns_422():
    response = client.post("/api/v1/analyze-repo", json={
        "scope": "repository",
        "target": "test",
        "files": []
    })

    assert response.status_code == 422

import ast
import javalang

from app.extractor import EntityExtractor


def test_python_endpoint_extraction():
    source = '''
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
'''
    _, functions, endpoints = EntityExtractor.extract_python_entities(
        ast.parse(source), source
    )

    assert any(f.name == "health" for f in functions)
    assert any(
        e.http_method == "GET"
        and e.path == "/health"
        and e.handler == "health"
        for e in endpoints
    )


def test_java_method_source_and_line_numbers():
    source = '''class Example {
    public String greet(String name) {
        return "hello " + name;
    }
}'''
    tree = javalang.parse.parse(source)
    classes, _, _ = EntityExtractor.extract_java_entities(tree, source)

    method = next(
        m for c in classes for m in c.methods if m.name == "greet"
    )

    assert method.signature == "String greet(String name)"
    assert method.source is not None
    assert 'return "hello " + name;' in method.source
    assert method.lineno == 2
    assert method.end_lineno == 4
