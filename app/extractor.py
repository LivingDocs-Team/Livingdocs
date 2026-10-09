import ast
import javalang

class EntityExtractor:
    @staticmethod
    def extract_python_entities(tree):
        classes, functions = [], []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                functions.append({
                    "name": node.name,
                    "args": [arg.arg for arg in node.args.args]
                })
        return {"classes": classes, "functions": functions}

    @staticmethod
    def extract_java_entities(tree):
        classes, methods = [], []
        for _, node in tree.filter(javalang.tree.ClassDeclaration):
            classes.append(node.name)
            for m in node.methods:
                methods.append({"name": m.name, "return_type": str(m.return_type)})
        return {"classes": classes, "methods": methods}
