"""Dependency injection utilities."""
from app.analyzer import CodeAnalyzer

def get_analyzer() -> CodeAnalyzer:
    return CodeAnalyzer()
