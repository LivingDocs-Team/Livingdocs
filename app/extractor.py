import ast
import javalang
from app.models import ClassInfo, Function, Parameter, Endpoint

# Hỗ trợ cả hàm def thường và async def để không bị bỏ sót
FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
MAX_SOURCE_CHARS = 1500

def _ann(node):
    """Trích xuất kiểu dữ liệu phức tạp (dict[int, float], Optional[str]...)"""
    return ast.unparse(node) if node is not None else None

def parse_py_func(node, lines, is_method=False) -> Function:
    a = node.args
    positional = a.posonlyargs + a.args
    defaults = [None] * (len(positional) - len(a.defaults)) + [ast.unparse(d) for d in a.defaults]

    params = []
    # Xử lý tham số vị trí
    for arg, default in zip(positional, defaults):
        if is_method and arg.arg in ("self", "cls"):
            continue
        params.append(Parameter(name=arg.arg, type=_ann(arg.annotation), default=default))
    
    # Xử lý *args
    if a.vararg:
        params.append(Parameter(name="*" + a.vararg.arg, type=_ann(a.vararg.annotation)))
        
    # Xử lý keyword-only args
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        params.append(Parameter(name=arg.arg, type=_ann(arg.annotation),
                                default=ast.unparse(d) if d is not None else None))
                                
    # Xử lý **kwargs
    if a.kwarg:
        params.append(Parameter(name="**" + a.kwarg.arg, type=_ann(a.kwarg.annotation)))

    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = _ann(node.returns)
    signature = f"{prefix} {node.name}({ast.unparse(a)})" + (f" -> {returns}" if returns else "")

    source = None
    if lines:
        source = "\n".join(lines[node.lineno - 1: node.end_lineno])[:MAX_SOURCE_CHARS]

    return Function(
        name=node.name, 
        signature=signature, 
        parameters=params,
        return_type=returns, 
        docstring=ast.get_docstring(node), 
        source=source
    )

class EntityExtractor:
    @staticmethod
    def extract_python_entities(tree, full_code: str = ""):
        classes = []
        functions = []
        endpoints = []

        lines = full_code.splitlines() if full_code else []

        for node in ast.iter_child_nodes(tree):
            # Dùng FUNC_TYPES để bắt cả hàm async lẫn sync
            if isinstance(node, FUNC_TYPES):
                functions.append(parse_py_func(node, lines))
            
            # Lớp (Class)
            elif isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, FUNC_TYPES):
                        methods.append(parse_py_func(item, lines, is_method=True))
                
                docstring = ast.get_docstring(node)
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                classes.append(ClassInfo(name=node.name, bases=bases, docstring=docstring, methods=methods))

        return classes, functions, endpoints

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
