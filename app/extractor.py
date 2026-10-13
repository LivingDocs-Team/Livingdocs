import ast
import javalang
from app.models import ClassInfo, Function, Parameter, Endpoint

class EntityExtractor:
    @staticmethod
    def _clean_source(source_code: str) -> str:
        # Cắt nguồn tối đa 1.500 ký tự theo yêu cầu hợp đồng
        return source_code[:1500] if source_code else ""

    @staticmethod
    def extract_python_entities(tree, full_code: str = ""):
        classes = []
        functions = []
        endpoints = []

        lines = full_code.splitlines() if full_code else []

        for node in ast.iter_child_nodes(tree):
            # Hàm cấp Module
            if isinstance(node, ast.FunctionDef):
                functions.append(EntityExtractor._parse_py_func(node, lines))
            
            # Lớp (Class)
            elif isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        methods.append(EntityExtractor._parse_py_func(item, lines, is_method=True))
                
                docstring = ast.get_docstring(node)
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                classes.append(ClassInfo(name=node.name, bases=bases, docstring=docstring, methods=methods))

        return classes, functions, endpoints

    @staticmethod
    def _parse_py_func(node: ast.FunctionDef, lines: list, is_method: bool = False) -> Function:
        params = []
        for arg in node.args.args:
            # Bỏ self / cls theo đúng lưu ý trong Hợp đồng
            if is_method and arg.arg in ["self", "cls"]:
                continue
            params.append(Parameter(name=arg.arg, type=arg.annotation.id if isinstance(arg.annotation, ast.Name) else None))

        docstring = ast.get_docstring(node)
        
        # Lấy source code của hàm
        source = ""
        if lines and hasattr(node, "lineno") and hasattr(node, "end_lineno"):
            source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            source = EntityExtractor._clean_source(source)

        return Function(
            name=node.name,
            parameters=params,
            docstring=docstring,
            source=source
        )

    @staticmethod
    def extract_java_entities(tree, full_code: str = ""):
        classes = []
        functions = []
        endpoints = []

        for path, node in tree.filter(javalang.tree.ClassDeclaration):
            methods = []
            for m in node.methods:
                params = [Parameter(name=p.name, type=p.type.name if p.type else None) for p in m.parameters]
                methods.append(Function(name=m.name, parameters=params, return_type=m.return_type.name if m.return_type else "void"))
            
            bases = [node.extends.name] if node.extends else []
            classes.append(ClassInfo(name=node.name, bases=bases, methods=methods))

        return classes, functions, endpoints
