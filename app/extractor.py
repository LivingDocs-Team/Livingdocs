import ast
import javalang

from app.models import ClassInfo, Function, Parameter, Endpoint

FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
MAX_SOURCE_CHARS = 1500

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


def _safe_unparse(node):
    try:
        return _safe_unparse(node)
    except Exception:
        return None


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
            type=_safe_unparse(arg.annotation),
            default=default,
        ))

    if args.vararg:
        params.append(Parameter(
            name="*" + args.vararg.arg,
            type=_safe_unparse(args.vararg.annotation),
        ))

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        params.append(Parameter(
            name=arg.arg,
            type=_safe_unparse(arg.annotation),
            default=_safe_unparse(default) if default is not None else None,
        ))

    if args.kwarg:
        params.append(Parameter(
            name="**" + args.kwarg.arg,
            type=_safe_unparse(args.kwarg.annotation),
        ))

    return params


def parse_py_func(node, lines, is_method=False) -> Function:
    returns = _safe_unparse(node.returns)
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


def _route_endpoints(node):
    """Extract common FastAPI/Flask-style route decorators."""
    endpoints = []

    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue

        func = decorator.func
        if not isinstance(func, ast.Attribute):
            continue

        route_name = func.attr.lower()
        path = None
        methods = []

        if route_name in HTTP_METHODS:
            methods = [route_name.upper()]
            if decorator.args:
                path = _literal_string(decorator.args[0])

        elif route_name in ("api_route", "route"):
            if decorator.args:
                path = _literal_string(decorator.args[0])

            for keyword in decorator.keywords:
                if keyword.arg == "methods" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                    methods = [
                        item.value.upper()
                        for item in keyword.value.elts
                        if isinstance(item, ast.Constant)
                        and isinstance(item.value, str)
                    ]

        if not path:
            continue

        for method in methods:
            endpoints.append(Endpoint(
                http_method=method,
                path=path,
                handler=node.name,
                parameters=_python_parameters(node),
            ))

    return endpoints


def _java_source_range(code, start_line):
    """Approximate a Java declaration's end line by matching braces."""
    lines = code.splitlines()
    if not start_line or start_line > len(lines):
        return start_line, start_line, None

    start_offset = sum(len(line) + 1 for line in lines[:start_line - 1])
    opening = code.find("{", start_offset)

    # Abstract/interface methods may end with a semicolon.
    semicolon = code.find(";", start_offset)
    if opening < 0 or (semicolon >= 0 and semicolon < opening):
        end_line = code.count("\n", 0, semicolon) + 1 if semicolon >= 0 else start_line
        source = "\n".join(lines[start_line - 1:end_line])[:MAX_SOURCE_CHARS]
        return start_line, end_line, source

    depth = 0
    i = opening
    state = "code"

    while i < len(code):
        char = code[i]
        nxt = code[i + 1] if i + 1 < len(code) else ""

        if state == "code":
            if char == "/" and nxt == "/":
                state = "line_comment"
                i += 1
            elif char == "/" and nxt == "*":
                state = "block_comment"
                i += 1
            elif char == '"':
                state = "string"
            elif char == "'":
                state = "char"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end_line = code.count("\n", 0, i) + 1
                    source = "\n".join(lines[start_line - 1:end_line])[:MAX_SOURCE_CHARS]
                    return start_line, end_line, source

        elif state == "line_comment":
            if char == "\n":
                state = "code"
        elif state == "block_comment":
            if char == "*" and nxt == "/":
                state = "code"
                i += 1
        elif state in ("string", "char"):
            if char == "\\":
                i += 1
            elif (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "code"

        i += 1

    end_line = len(lines)
    source = "\n".join(lines[start_line - 1:end_line])[:MAX_SOURCE_CHARS]
    return start_line, end_line, source


def _java_type(type_node):
    if type_node is None:
        return "void"

    name = getattr(type_node, "name", str(type_node))
    args = getattr(type_node, "arguments", None) or []
    if args:
        rendered = []
        for arg in args:
            arg_type = getattr(arg, "type", None)
            rendered.append(_java_type(arg_type) if arg_type else "?")
        name += "<" + ", ".join(rendered) + ">"

    dimensions = getattr(type_node, "dimensions", None) or []
    name += "[]" * len(dimensions)
    return name


class EntityExtractor:
    @staticmethod
    def extract_python_entities(tree, full_code: str = ""):
        classes = []
        functions = []
        endpoints = []
        lines = full_code.splitlines()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, FUNC_TYPES):
                functions.append(parse_py_func(node, lines))
                endpoints.extend(_route_endpoints(node))

            elif isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, FUNC_TYPES):
                        methods.append(parse_py_func(item, lines, is_method=True))
                        endpoints.extend(_route_endpoints(item))

                bases = [
                    base.id for base in node.bases
                    if isinstance(base, ast.Name)
                ]
                classes.append(ClassInfo(
                    name=node.name,
                    bases=bases,
                    docstring=ast.get_docstring(node),
                    methods=methods,
                ))

        return classes, functions, endpoints
    
    @staticmethod
    def extract_java_entities(tree, full_code: str = ""):
        classes = []
        functions = []
        endpoints = []

        for _, node in tree.filter(javalang.tree.ClassDeclaration):
           methods = []

        for method in getattr(node, "methods", []):
            params = []
            for param in getattr(method, "parameters", []):
                try:
                    param_type = getattr(param.type, "name", None) or _java_type(param.type)
                except Exception:
                    param_type = "Object"
                params.append(Parameter(
                    name=getattr(param, "name", "arg"),
                    type=param_type,
                ))

            start_line = getattr(getattr(method, "position", None), "line", None)
            start_line, end_line, source = _java_source_range(full_code, start_line)

            signature = (
                f"{_java_type(method.return_type)} "
                f"{method.name}("
                + ", ".join(
                    f"{param.type or 'Object'} {param.name}"
                    for param in params
                )
                + ")"
            )

            methods.append(Function(
                name=method.name,
                signature=signature,
                parameters=params,
                return_type=_java_type(method.return_type),
                source=source,
                lineno=start_line,
                end_lineno=end_line,
            ))

        bases = [node.extends.name] if getattr(node, "extends", None) and getattr(node.extends, "name", None) else []
        classes.append(ClassInfo(
            name=node.name,
            bases=bases,
            methods=methods,
        ))

        return classes, functions, endpoints