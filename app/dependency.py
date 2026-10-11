import ast
import javalang

class DependencyAnalyzer:
    @staticmethod
    def get_python_imports(tree):
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module)
        return imports

    @staticmethod
    def get_java_imports(tree):
        return [imp.path for imp in tree.imports]
