import pytest
import ast
from app.analyzer import ASTAnalyzer
from app.reader import FileReader
from app.extractor import EntityExtractor

def test_reader_detect_language():
    """LD-371: Kiểm thử bộ nhận diện ngôn ngữ mã nguồn"""
    assert FileReader.detect_language("main.py") == "python"
    assert FileReader.detect_language("Service.java") == "java"
    assert FileReader.detect_language("script.rb") == "ruby"

def test_ast_analyzer_valid_python():
    """LD-371: Kiểm thử phân tích AST cú pháp Python hợp lệ"""
    code = "def hello(): pass"
    tree, error = ASTAnalyzer.parse_code(code, "python")
    assert tree is not None
    assert error is None
    assert isinstance(tree, ast.Module)

def test_ast_analyzer_invalid_python():
    """LD-371: Kiểm thử xử lý lỗi cú pháp SyntaxError"""
    code = "def broken_func(:"
    tree, error = ASTAnalyzer.parse_code(code, "python")
    assert tree is None
    assert "SyntaxError" in error or "invalid syntax" in error.lower()

def test_entity_extractor_async_function():
    """LD-371: Trích xuất chính xác hàm async, signature và dòng bắt đầu/kết thúc"""
    code = "async def fetch_data(url: str) -> dict:\n    return {}"
    tree, _ = ASTAnalyzer.parse_code(code, "python")
    classes, functions, endpoints = EntityExtractor.extract_python_entities(tree, code)
    
    assert len(functions) == 1
    func = functions[0]
    assert func.name == "fetch_data"
    assert "async def" in func.signature
    assert func.lineno == 1
    assert func.end_lineno == 2
