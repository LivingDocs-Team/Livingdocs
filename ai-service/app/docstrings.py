"""Docstring processing utilities."""
import ast

def extract_docstring(code: str) -> str:
    try:
        tree = ast.parse(code)
        return ast.get_docstring(tree) or ""
    except Exception:
        return ""
