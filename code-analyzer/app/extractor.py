import ast
from typing import Dict, List, Any

class CodeChangeAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.functions: List[Dict[str, Any]] = []
        self.classes: List[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        args = [a.arg for a in node.args.args]
        self.functions.append({
            "name": node.name,
            "args": args,
            "lineno": node.lineno,
            "docstring": ast.get_docstring(node)
        })
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        self.classes.append(node.name)
        self.generic_visit(node)

def analyze_code_diff(file_path: str, code_content: str) -> Dict[str, Any]:
    """
    Phân tích file code Python/Java và trích xuất cấu trúc AST
    """
    try:
        tree = ast.parse(code_content)
        analyzer = CodeChangeAnalyzer()
        analyzer.visit(tree)
        return {
            "file_path": file_path,
            "classes": analyzer.classes,
            "functions": analyzer.functions,
            "status": "SUCCESS"
        }
    except Exception as e:
        return {
            "file_path": file_path,
            "error": str(e),
            "status": "FAILED"
        }
