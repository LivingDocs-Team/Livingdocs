import ast

from app.models import ClassField, ClassInfo, Function, Parameter, Endpoint

FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
MAX_SOURCE_CHARS = 1500

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


def _ann(node):
    return ast.unparse(node) if node is not None else None


def _python_parameters(node, is_method=False):
    args = node.args
    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults))
    defaults += [ast.unparse(d) for d in args.defaults]

    params = []
    for arg, default in zip(positional, defaults):
        if is_method and arg.arg in ("self", "cls"):
            continue
        params.append(Parameter(
            name=arg.arg,
            type=_ann(arg.annotation),
            default=default,
        ))

    if args.vararg:
        params.append(Parameter(
            name="*" + args.vararg.arg,
            type=_ann(args.vararg.annotation),
        ))

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        params.append(Parameter(
            name=arg.arg,
            type=_ann(arg.annotation),
            default=ast.unparse(default) if default is not None else None,
        ))

    if args.kwarg:
        params.append(Parameter(
            name="**" + args.kwarg.arg,
            type=_ann(args.kwarg.annotation),
        ))

    return params


def parse_py_func(node, lines, is_method=False) -> Function:
    returns = _ann(node.returns)
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    signature = f"{prefix} {node.name}({ast.unparse(node.args)})"
    if returns:
        signature += f" -> {returns}"

    lineno = getattr(node, "lineno", None)
    end_lineno = getattr(node, "end_lineno", None)

    source = None
    if lineno is not None and end_lineno is not None:
        source = "\n".join(lines[lineno - 1:end_lineno])[:MAX_SOURCE_CHARS]

    return Function(
        name=node.name,
        signature=signature,
        parameters=_python_parameters(node, is_method),
        return_type=returns,
        docstring=ast.get_docstring(node),
        source=source,
        lineno=lineno,
        end_lineno=end_lineno,
    )


def _literal_string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


ROUTER_FACTORIES = {"APIRouter": "prefix", "Blueprint": "url_prefix"}


def _router_prefixes(tree):
    """Module-level `router = APIRouter(prefix="/api")` / `bp = Blueprint(..., url_prefix="/x")`."""
    prefixes = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        fname = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        key = ROUTER_FACTORIES.get(fname)
        if key is None:
            continue
        prefix = next((_literal_string(k.value) for k in node.value.keywords if k.arg == key), None)
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix or ""
    return prefixes


def _join_path(prefix, path):
    if not prefix:
        return path
    return prefix.rstrip("/") + "/" + path.lstrip("/") if path.strip("/") else prefix


def _route_endpoints(node, prefixes=None):
    """Extract common FastAPI/Flask-style route decorators."""
    endpoints = []
    prefixes = prefixes or {}

    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue

        func = decorator.func
        if not isinstance(func, ast.Attribute):
            continue

        route_name = func.attr.lower()
        owner = func.value.id if isinstance(func.value, ast.Name) else None
        path = None
        methods = []

        if decorator.args:
            path = _literal_string(decorator.args[0])
        if path is None:
            path = next((_literal_string(k.value) for k in decorator.keywords
                         if k.arg in ("path", "rule")), None)

        if route_name in HTTP_METHODS:
            methods = [route_name.upper()]

        elif route_name in ("api_route", "route"):
            for keyword in decorator.keywords:
                if keyword.arg == "methods" and isinstance(keyword.value, (ast.List, ast.Tuple, ast.Set)):
                    methods = [
                        item.value.upper()
                        for item in keyword.value.elts
                        if isinstance(item, ast.Constant)
                        and isinstance(item.value, str)
                    ]
            if not methods:
                methods = ["GET"]  # Flask route() and FastAPI api_route() default

        else:
            continue

        if path is None:
            continue
        path = _join_path(prefixes.get(owner, ""), path) or "/"

        for method in methods:
            endpoints.append(Endpoint(
                http_method=method,
                path=path,
                handler=node.name,
                parameters=_python_parameters(node),
                response=_ann(node.returns),
                lineno=getattr(node, "lineno", None),
                end_lineno=getattr(node, "end_lineno", None),
            ))

    return endpoints


def _class_fields(node):
    """Annotated attributes (pydantic, dataclass) and plain class constants."""
    fields = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            fields.append(ClassField(
                name=item.target.id,
                type=_ann(item.annotation),
                default=ast.unparse(item.value)[:200] if item.value is not None else None,
                lineno=item.lineno,
            ))
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    fields.append(ClassField(
                        name=target.id,
                        default=ast.unparse(item.value)[:200],
                        lineno=item.lineno,
                    ))
    return fields


class EntityExtractor:
    @staticmethod
    def extract_python_entities(tree, full_code: str = ""):
        classes = []
        functions = []
        endpoints = []
        lines = full_code.splitlines()
        prefixes = _router_prefixes(tree)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, FUNC_TYPES):
                functions.append(parse_py_func(node, lines))
                endpoints.extend(_route_endpoints(node, prefixes))

            elif isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, FUNC_TYPES):
                        methods.append(parse_py_func(item, lines, is_method=True))
                        endpoints.extend(_route_endpoints(item, prefixes))

                classes.append(ClassInfo(
                    name=node.name,
                    bases=[ast.unparse(base) for base in node.bases],
                    docstring=ast.get_docstring(node),
                    methods=methods,
                    fields=_class_fields(node),
                    lineno=node.lineno,
                    end_lineno=node.end_lineno,
                ))

        return classes, functions, endpoints

    @staticmethod
    def extract_java_entities(tree, full_code: str = ""):
        """`tree` is the tree-sitter tree from ASTAnalyzer.parse_code (re-parsed if missing)."""
        from app.java_extractor import extract_java, parse_java

        if tree is None or not hasattr(tree, "root_node"):
            tree, error = parse_java(full_code)
            if error:
                raise ValueError(error)
        classes, functions, endpoints, _ = extract_java(tree, full_code)
        return classes, functions, endpoints



