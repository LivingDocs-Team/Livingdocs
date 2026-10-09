import ast
import javalang

class ASTAnalyzer:
    @staticmethod
    def parse_python_ast(code: str):
        return ast.parse(code)

    @staticmethod
    def parse_java_ast(code: str):
        return javalang.parse.parse(code)
