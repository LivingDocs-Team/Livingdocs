import ast

from app.java_extractor import java_imports


class DependencyAnalyzer:
    @staticmethod
    def get_python_imports(tree):
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return list(set(imports))

    @staticmethod
    def get_java_imports(tree):
        """`tree` is a tree-sitter tree (ASTAnalyzer.parse_code)."""
        return java_imports(tree)
