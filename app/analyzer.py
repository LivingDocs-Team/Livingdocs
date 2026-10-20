
import ast
import javalang


class ASTAnalyzer:
    @staticmethod
    def parse_code(code: str, language: str):
        if language == "python":
            return ASTAnalyzer.parse_python_ast(code)
        elif language == "java":
            return ASTAnalyzer.parse_java_ast(code)
        else:
            return None, f"Unsupported language: {language}"

    @staticmethod
    def parse_python_ast(code: str):
        try:
            return ast.parse(code), None
        except SyntaxError as e:
            return None, f"SyntaxError line {e.lineno}: {e.msg}"
        except Exception as e:
            return None, f"AST Parse Error: {str(e)}"

    @staticmethod
    def parse_java_ast(code: str):
        try:
            return javalang.parse.parse(code), None
        except javalang.parser.JavaSyntaxError as e:
            return None, f"JavaSyntaxError: {str(e)}"
        except Exception as e:
            return None, f"Java AST Parse Error: {str(e)}"
