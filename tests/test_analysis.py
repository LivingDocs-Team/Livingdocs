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

from app.analyzer import ASTAnalyzer
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
    tree, error = ASTAnalyzer.parse_code(source, "java")
    assert error is None
    classes, _, _ = EntityExtractor.extract_java_entities(tree, source)

    method = next(
        m for c in classes for m in c.methods if m.name == "greet"
    )

    assert method.signature == "String greet(String name)"
    assert method.source is not None
    assert 'return "hello " + name;' in method.source
    assert method.lineno == 2
    assert method.end_lineno == 4


# ---------- output quality fixes (A1-A12, see ai-service/tests/integration/QUALITY.md) ----------

def analyze(path, content, language=None, extra=()):
    files = [{"path": path, "content": content, **({"language": language} if language else {})}]
    files += [dict(f) for f in extra]
    r = client.post("/api/v1/analyze-repo", json={"target": "t", "files": files})
    assert r.status_code == 200, r.text
    return r.json()


SPRING = '''package com.acme.web;

import org.springframework.web.bind.annotation.*;

/** Orders API. */
@RestController
@RequestMapping("/orders")
public class OrderApi {
    private final OrderService service;

    public OrderApi(OrderService service) { this.service = service; }

    /**
     * Get one order.
     * @param id order id
     */
    @GetMapping("/{id}")
    public Order get(@PathVariable Long id) { return service.find(id); }

    @PostMapping
    public Order create(@RequestBody Order order) { return order; }

    @RequestMapping(value = "/search", method = RequestMethod.POST)
    public List<Order> search(@RequestParam String q, int page) { return null; }
}

interface OrderService { Order find(Long id); }

enum Status { NEW, PAID }

record OrderDto(Long id, String code) {
    String label() { return """
        Order
        """; }
}
'''


def test_java17_syntax_is_parsed():                                   # A1
    f = analyze("src/main/java/com/acme/web/OrderApi.java", SPRING)["files"][0]
    assert f["status"] == "ok", f["error"]
    assert f["module"] == "com.acme.web"                              # A9 (package)
    kinds = {c["name"]: c["kind"] for c in f["classes"]}
    assert kinds == {"OrderApi": "class", "OrderService": "interface", "Status": "enum",
                     "OrderDto": "record"}                            # A4


def test_java_syntax_error_has_position():                            # A1
    f = analyze("B.java", "class B { void f( { }")["files"][0]
    assert f["status"] == "invalid"
    assert f["error"].startswith("JavaSyntaxError line 1:")


def test_spring_endpoints():                                          # A2
    f = analyze("OrderApi.java", SPRING)["files"][0]
    eps = {(e["http_method"], e["path"]): e for e in f["endpoints"]}
    assert set(eps) == {("GET", "/orders/{id}"), ("POST", "/orders"), ("POST", "/orders/search")}
    get = eps[("GET", "/orders/{id}")]
    assert get["handler"] == "get" and get["parameters"][0]["name"] == "id" and get["response"] == "Order"
    assert eps[("POST", "/orders")]["request_body"] == "Order"
    assert [p["name"] for p in eps[("POST", "/orders/search")]["parameters"]] == ["q"]
    assert get["lineno"] == 18                                        # A6: line of the declaration


def test_java_constructor_javadoc_fields():                           # A4, A5, A8
    f = analyze("OrderApi.java", SPRING)["files"][0]
    api = next(c for c in f["classes"] if c["name"] == "OrderApi")
    assert api["docstring"] == "Orders API."
    assert [m["name"] for m in api["methods"]] == ["OrderApi", "get", "create", "search"]
    assert api["methods"][1]["docstring"] == "Get one order.\n@param id order id"
    assert api["fields"][0] == {"name": "service", "type": "OrderService", "default": None,
                                "description": None, "lineno": 9}
    assert (api["lineno"], api["end_lineno"]) == (8, 25)              # A6
    dto = next(c for c in f["classes"] if c["name"] == "OrderDto")
    assert [x["name"] for x in dto["fields"]] == ["id", "code"]


def test_python_route_variants():                                     # A3
    src = '''from fastapi import APIRouter
from flask import Flask, Blueprint
app = Flask(__name__)
router = APIRouter(prefix="/api/v1")
bp = Blueprint("admin", __name__, url_prefix="/admin")

@app.route("/ping")
def ping():
    return "ok"

@router.get("/items/{name}")
def get_item(name: str) -> dict:
    return {}

@router.post(path="/items")
def create_item():
    pass

@bp.route("/users", methods=["GET", "POST"])
def users():
    pass
'''
    eps = {(e["http_method"], e["path"]) for e in analyze("api.py", src)["files"][0]["endpoints"]}
    assert eps == {("GET", "/ping"), ("GET", "/api/v1/items/{name}"), ("POST", "/api/v1/items"),
                   ("GET", "/admin/users"), ("POST", "/admin/users")}


def test_python_classes_lines_bases_fields():                         # A6, A7, A8
    src = '''import typing
from django.db import models
from pydantic import BaseModel


class Item(BaseModel):
    name: str
    price: float = 0.0
    TAX = 0.1


class Order(models.Model, typing.Generic[T]):
    pass
'''
    f = analyze("app/models.py", src)["files"][0]
    item, order = f["classes"]
    assert (item["lineno"], item["end_lineno"]) == (6, 9)
    assert [(x["name"], x["type"], x["default"]) for x in item["fields"]] == [
        ("name", "str", None), ("price", "float", "0.0"), ("TAX", None, "0.1")]
    assert order["bases"] == ["models.Model", "typing.Generic[T]"]
    assert f["module"] == "app.models"                                # A9


def test_bom_language_case_duplicates():                              # A10, A11, A12
    assert analyze("a.py", "﻿def f():\n    return 1\n")["files"][0]["status"] == "ok"
    assert analyze("b.py", "def f(): pass\n", language="Python")["files"][0]["status"] == "ok"
    out = analyze("c.py", "x = 1\n", extra=[{"path": "c.py", "content": "y = 2\n"}])
    assert [f["path"] for f in out["files"]] == ["c.py"]
    assert out["warnings"] == ["c.py: duplicate path, only the first copy was analyzed."]



