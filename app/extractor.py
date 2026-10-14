import ast
import javalang
from app.models import ClassInfo, Function, Parameter, Endpoint

FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
MAX_SOURCE_CHARS = 1500

def _ann(node):
    return ast.unparse(node) if node is not None else None

def parse_py_func(node, lines, is_method=False) -> Function:
    a = node.args
    positional = a.posonlyargs + a.args
    defaults = [None] * (len(positional) - len(a.defaults)) + [ast.unparse(d) for d in a.defaults]

    params = []
    for arg, default in zip(positional, defaults):
        if is_method and arg.arg in ("self", "cls"):
            continue
        params.append(Parameter(name=arg.arg, type=_ann(arg.annotation), default=default))
    
    if a.vararg:
        params.append(Parameter(name="*" + a.vararg.arg, type=_ann(a.vararg.annotation)))
        
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        params.append(Parameter(name=arg.arg, type=_ann(arg.annotation),
                                default=ast.unparse(d) if d is not None else None))
                                
    if a.kwarg:
        params.append(Parameter(name="**" + a.kwarg.arg, type=_ann(a.kwarg.annotation)))

    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = _ann(node.returns)
    signature = f"{prefix} {node.name}({ast.unparse(a)})" + (f" -> {returns}" if returns else "")

    # Lấy thông tin dòng bắt đầu và kết thúc
    lineno = getattr(node, "lineno", None)
    end_lineno = getattr(node, "end_lineno", None)

    source = None
    if lines and lineno is not None and end_lineno is not None:
        source = "\n".join(lines[lineno - 1 : end_lineno])[:MAX_SOURCE_CHARS]

    return Function(
        name=node.name, 
        signature=signature, 
        parameters=params,
        return_type=returns, 
        docstring=ast.get_docstring(node), 
        source=source,
        lineno=lineno,
        end_lineno=end_lineno
    )

class EntityExtractor:
    @staticmethod
    def extract_python_entities(tree, full_code: str = ""):
        classes = []
        functions = []
        endpoints = []

        lines = full_code.splitlines() if full_code else []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, FUNC_TYPES):
                functions.append(parse_py_func(node, lines))
            
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
