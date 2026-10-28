
import ast
import javalang


class ASTAnalyzer:
    @staticmethod
    def parse_code(source: str, lang: str):
        if lang == "python":
            return ast.parse(source), None
        if lang == "java":
            # nếu đang dùng parser Java thì làm ở đây
            # hoặc return None, "Java parsing not implemented yet"
            return None, None
        return None, f"Unsupported language: {lang}"

    @staticmethod
    def parse_python_ast(code: str):
        """Parse Python source code into an AST."""
        try:
            return ast.parse(code), None
        except SyntaxError as e:
            return None, f"SyntaxError line {e.lineno}: {e.msg}"
        except Exception as e:
            return None, f"AST Parse Error: {str(e)}"

    @staticmethod
    def parse_java_ast(code: str):
        """Parse Java source code into an AST."""
        try:
            return javalang.parse.parse(code), None
        except javalang.parser.JavaSyntaxError as e:
            return None, f"JavaSyntaxError: {str(e)}"
        except Exception as e:
            return None, f"Java AST Parse Error: {str(e)}"