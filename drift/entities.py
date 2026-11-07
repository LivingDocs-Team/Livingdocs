"""Lightweight entity extraction for the drift detector (LD-146).

Deliberately dependency-free (stdlib `ast` for Python, a brace-aware scanner for Java) so the
drift check runs in any CI job without installing the analyzer's tree-sitter stack. It extracts
only what documentation talks about: classes, functions/methods, their signatures, HTTP routes
and class attributes.
"""
from __future__ import annotations

import ast
import hashlib
import re
from typing import Dict, List, Optional, Sequence, Tuple

from .models import Entity, Param

MAX_SOURCE_CHARS = 1200
HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


class ExtractionError(Exception):
    """The file could not be parsed (syntax error)."""


def extract_entities(path: str, source: str, language: str) -> List[Entity]:
    source = source.lstrip("\ufeff")
    if language == "python":
        return extract_python(path, source)
    if language == "java":
        return extract_java(path, source)
    return []


def _digest(text: str) -> str:
    return hashlib.sha1(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()[:12]


def _join_route(prefix: str, path: str) -> str:
    prefix, path = prefix or "", path or ""
    if not prefix:
        return path or "/"
    if not path.strip("/"):
        return prefix
    return prefix.rstrip("/") + "/" + path.lstrip("/")


# --------------------------------------------------------------------------- Python

def _literal_str(node) -> Optional[str]:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _unparse(node) -> Optional[str]:
    return ast.unparse(node) if node is not None else None


def _router_prefixes(tree: ast.Module) -> Dict[str, str]:
    prefixes: Dict[str, str] = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        fname = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        key = {"APIRouter": "prefix", "Blueprint": "url_prefix"}.get(fname)
        if not key:
            continue
        prefix = next((_literal_str(k.value) for k in node.value.keywords if k.arg == key), None)
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix or ""
    return prefixes


def _py_routes(node, prefixes: Dict[str, str]) -> Tuple[str, ...]:
    routes: List[str] = []
    for dec in node.decorator_list:
        if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
            continue
        attr = dec.func.attr.lower()
        owner = dec.func.value.id if isinstance(dec.func.value, ast.Name) else None
        path = _literal_str(dec.args[0]) if dec.args else None
        if path is None:
            path = next((_literal_str(k.value) for k in dec.keywords if k.arg in ("path", "rule")), None)
        if path is None:
            continue
        if attr in HTTP_METHODS:
            methods = [attr.upper()]
        elif attr in ("route", "api_route"):
            methods = []
            for k in dec.keywords:
                if k.arg == "methods" and isinstance(k.value, (ast.List, ast.Tuple, ast.Set)):
                    methods = [e.value.upper() for e in k.value.elts
                               if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            methods = methods or ["GET"]
        else:
            continue
        full = _join_route(prefixes.get(owner, ""), path)
        routes += [f"{m} {full}" for m in methods]
    return tuple(routes)


def _py_params(node, is_method: bool) -> Tuple[Param, ...]:
    a = node.args
    positional = a.posonlyargs + a.args
    defaults = [False] * (len(positional) - len(a.defaults)) + [True] * len(a.defaults)
    params: List[Param] = []
    for i, (arg, has_default) in enumerate(zip(positional, defaults)):
        if is_method and i == 0 and arg.arg in ("self", "cls"):
            continue
        params.append(Param(arg.arg, _unparse(arg.annotation), has_default))
    if a.vararg:
        params.append(Param(a.vararg.arg, _unparse(a.vararg.annotation), False, "*"))
    for arg, default in zip(a.kwonlyargs, a.kw_defaults):
        params.append(Param(arg.arg, _unparse(arg.annotation), default is not None))
    if a.kwarg:
        params.append(Param(a.kwarg.arg, _unparse(a.kwarg.annotation), False, "**"))
    return tuple(params)


def _body_without_docstring(node) -> list:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and _literal_str(body[0].value) is not None:
        body = body[1:]
    return body


def extract_python(path: str, source: str) -> List[Entity]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ExtractionError(f"SyntaxError line {exc.lineno}: {exc.msg}") from exc
    lines = source.splitlines()
    prefixes = _router_prefixes(tree)
    out: List[Entity] = []

    def span(node) -> Tuple[int, int]:
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        return start, getattr(node, "end_lineno", node.lineno) or node.lineno

    def snippet(start: int, end: int) -> str:
        return "\n".join(lines[start - 1:end])[:MAX_SOURCE_CHARS]

    def visit(body: Sequence[ast.stmt], scope: str, in_class: bool) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                qname = scope + node.name
                start, end = span(node)
                bases = tuple(_unparse(b) or "" for b in node.bases)
                enum_like = any(b.split(".")[-1].endswith("Enum") for b in bases)
                fields: List[str] = []
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        fields.append(f"{item.target.id}: {_unparse(item.annotation)}")
                    elif enum_like and isinstance(item, ast.Assign):
                        fields += [t.id for t in item.targets if isinstance(t, ast.Name)]
                out.append(Entity(
                    kind="class", name=qname, file=path, line=start, end_line=end,
                    signature=f"class {node.name}" + (f"({', '.join(bases)})" if bases else ""),
                    bases=bases, fields=tuple(fields), language="python", source=snippet(start, end)))
                visit(node.body, qname + ".", True)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start, end = span(node)
                params = _py_params(node, in_class)
                ret = _unparse(node.returns)
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                arg_text = ast.unparse(node.args)
                if in_class and arg_text.split(",")[0].strip() in ("self", "cls"):
                    arg_text = ", ".join(p.strip() for p in arg_text.split(",")[1:])  # naive but display-only
                sig = f"{prefix} {node.name}({arg_text})" + (f" -> {ret}" if ret else "")
                out.append(Entity(
                    kind="method" if in_class else "function", name=scope + node.name, file=path,
                    line=start, end_line=end, signature=sig, params=params, return_type=ret,
                    routes=_py_routes(node, prefixes),
                    body_digest=_digest("".join(ast.dump(n) for n in _body_without_docstring(node))),
                    language="python", source=snippet(start, end)))

    visit(tree.body, "", False)
    return out


# --------------------------------------------------------------------------- Java

_MODIFIERS = {"public", "protected", "private", "static", "final", "abstract", "synchronized",
              "native", "default", "transient", "volatile", "strictfp", "sealed", "non-sealed"}
_MAPPING_METHODS = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
                    "DeleteMapping": "DELETE", "PatchMapping": "PATCH"}
_TYPE_DECL = re.compile(r"^(?:(?:public|protected|private|abstract|static|final|sealed|non-sealed|strictfp)\s+)*"
                        r"(class|interface|enum|record|@interface)\s+([A-Za-z_]\w*)")


def _mask(src: str, keep_strings: bool = False) -> str:
    """Blank out comments (and string contents) keeping every offset and newline in place."""
    out = list(src)
    n, i = len(src), 0

    def blank(a: int, b: int, fill: str = " ") -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = fill

    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif src.startswith('"""', i):
            j = src.find('"""', i + 3)
            j = n if j < 0 else j
            if not keep_strings:
                blank(i + 3, j, "_")
            i = j + 3
        elif src[i] in "\"'":
            quote, j = src[i], i + 1
            while j < n and src[j] != quote and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            if not keep_strings:
                blank(i + 1, j, "_")
            i = j + 1
        else:
            i += 1
    return "".join(out)


def _match(masked: str, i: int, open_ch: str, close_ch: str) -> int:
    """Index of the bracket closing the one at masked[i] (len(masked) - 1 when unbalanced)."""
    depth = 0
    for j in range(i, len(masked)):
        if masked[j] == open_ch:
            depth += 1
        elif masked[j] == close_ch:
            depth -= 1
            if depth == 0:
                return j
    return len(masked) - 1


def _split_top(text: str, sep: str = ",") -> List[str]:
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "<([{":
            depth += 1
        elif ch in ">)]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _strip_annotations(masked: str, original: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Remove @Annotation(...) from a header; return (header, [(name, args_text)])."""
    annotations: List[Tuple[str, str]] = []
    out: List[str] = []
    i, n = 0, len(masked)
    while i < n:
        if masked[i] == "@" and not masked.startswith("@interface", i):
            m = re.match(r"@\s*([A-Za-z_][\w.]*)", masked[i:])
            if m:
                j = i + m.end()
                k = j
                while k < n and masked[k] in " \t\r\n":
                    k += 1
                args = ""
                if k < n and masked[k] == "(":
                    close = _match(masked, k, "(", ")")
                    args = original[k + 1:close]
                    j = close + 1
                annotations.append((m.group(1).split(".")[-1], args))
                out.append(" ")
                i = j
                continue
        out.append(masked[i])
        i += 1
    return "".join(out), annotations


def _annotation_paths(args: str) -> List[str]:
    args = args.strip()
    if not args:
        return [""]
    m = re.search(r"\b(?:value|path)\s*=\s*(\{[^}]*\}|\"[^\"]*\")", args)
    chunk = m.group(1) if m else (args if args[0] in '"{' else "")
    paths = re.findall(r'"([^"]*)"', chunk)
    return paths or [""]


def _java_params(text: str) -> Tuple[Param, ...]:
    params: List[Param] = []
    for raw in _split_top(text):
        raw = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", raw)
        raw = re.sub(r"\bfinal\s+", "", raw).strip()
        variadic = "*" if "..." in raw else ""
        raw = raw.replace("...", " ")
        m = re.match(r"^(.*?)\s*\b([A-Za-z_]\w*)\s*(?:\[\s*\])*$", raw, re.S)
        if not m:
            continue
        ptype = re.sub(r"\s+", " ", m.group(1)).strip() or None
        params.append(Param(m.group(2), ptype, False, variadic))
    return tuple(params)


def _line_of(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def extract_java(path: str, source: str) -> List[Entity]:
    masked = _mask(source)
    plain = _mask(source, keep_strings=True)   # comments removed, strings kept (for digests)
    out: List[Entity] = []

    def snippet(a: int, b: int) -> str:
        return source[a:b + 1].strip()[:MAX_SOURCE_CHARS]

    def scan(start: int, end: int, scope: str, container: str, route_prefix: str,
             class_name: str) -> List[str]:
        """Scan one class body; append entities to `out`; return the class' own field list."""
        fields: List[str] = []
        skip_constants = container == "enum"
        seg, i = start, start
        while i < end:
            ch = masked[i]
            if ch == "(":
                i = _match(masked, i, "(", ")") + 1
                continue
            if ch not in ";{":
                i += 1
                continue
            block = None
            if ch == "{":
                close = _match(masked, i, "{", "}")
                block = (i, close)
            if skip_constants:
                if ch == ";":
                    skip_constants = False
                i = (block[1] if block else i) + 1
                seg = i
                continue
            handle(seg, i, block, scope, container, route_prefix, class_name, fields)
            i = (block[1] if block else i) + 1
            seg = i
        return fields

    def handle(hs: int, he: int, block, scope: str, container: str, route_prefix: str,
               class_name: str, fields: List[str]) -> None:
        header_m, annotations = _strip_annotations(masked[hs:he], source[hs:he])
        header = re.sub(r"\s+", " ", header_m).strip()
        if not header:
            return
        first = re.search(r"\S", masked[hs:he])
        decl_start = hs + (first.start() if first else 0)
        line_start = _line_of(source, decl_start)
        end_pos = block[1] if block else he

        tm = _TYPE_DECL.match(header)
        if tm and block:
            kind, simple = tm.group(1).replace("@", ""), tm.group(2)
            qname = scope + simple
            prefix = route_prefix
            for name, args in annotations:
                if name == "RequestMapping":
                    prefix = _join_route(route_prefix, _annotation_paths(args)[0])
            bases: List[str] = []
            for key in ("extends", "implements", "permits"):
                bm = re.search(rf"\b{key}\s+(.+?)(?=\s+(?:extends|implements|permits)\b|$)", header[tm.end():])
                if bm and key != "permits":
                    bases += [re.sub(r"<.*", "", b).strip() for b in _split_top(bm.group(1))]
            record_fields: List[str] = []
            if kind == "record":
                pm = re.search(r"\(", masked[hs:he])
                if pm:
                    p_open = hs + pm.start()
                    p_close = _match(masked, p_open, "(", ")")
                    comps = _java_params(source[p_open + 1:p_close])
                    record_fields = [f"{c.name}: {c.type}" if c.type else c.name for c in comps]
            slot = len(out)
            out.append(None)  # type: ignore[arg-type]  # placeholder keeps parent-before-child order
            body_fields = scan(block[0] + 1, block[1], qname + ".", kind, prefix, simple)
            out[slot] = Entity(
                kind="class", name=qname, file=path, line=line_start,
                end_line=_line_of(source, end_pos), signature=header, bases=tuple(bases),
                fields=tuple(record_fields + body_fields), language="java",
                source=snippet(decl_start, end_pos))
            return

        paren = header_m.find("(")
        eq = header_m.find("=")
        if paren > 0 and (eq < 0 or paren < eq):
            left = header_m[:paren]
            nm = re.search(r"([A-Za-z_]\w*)\s*$", left)
            if not nm:
                return
            name = nm.group(1)
            before = re.sub(r"\s+", " ", left[:nm.start()]).strip()
            tokens = [t for t in re.split(r"\s+(?![^<]*>)", before) if t]
            while tokens and tokens[0] in _MODIFIERS:
                tokens.pop(0)
            ret = " ".join(tokens) or None
            if ret and re.match(r"^<.*>$", ret):  # only a generic declaration, no return type
                ret = None
            # parameter list, located in the original header text
            rel_open = _first_paren_after_name(masked, hs, he, name)
            p_close = _match(masked, rel_open, "(", ")")
            params = _java_params(source[rel_open + 1:p_close])
            is_ctor = ret is None and name == class_name
            routes: List[str] = []
            for aname, args in annotations:
                if aname in _MAPPING_METHODS:
                    methods = [_MAPPING_METHODS[aname]]
                elif aname == "RequestMapping":
                    methods = re.findall(r"RequestMethod\.(\w+)", args) or ["ANY"]
                else:
                    continue
                for sub in _annotation_paths(args):
                    routes += [f"{m} {_join_route(route_prefix, sub)}" for m in methods]
            sig_params = ", ".join(f"{p.type} {p.name}" if p.type else p.name for p in params)
            signature = (f"{ret} " if ret else "") + f"{name}({sig_params})"
            body = plain[block[0]:block[1] + 1] if block else ""
            if ret is None and not is_ctor:
                return
            out.append(Entity(
                kind="method", name=scope + name, file=path, line=line_start,
                end_line=_line_of(source, end_pos), signature=signature, params=params,
                return_type=ret, routes=tuple(routes), body_digest=_digest(body),
                language="java", source=snippet(decl_start, end_pos)))
            return

        # field: "Type name [= value]"
        decl = header_m.split("=", 1)[0]
        tokens = [t for t in re.split(r"\s+(?![^<]*>)", re.sub(r"\s+", " ", decl).strip()) if t]
        while tokens and tokens[0] in _MODIFIERS:
            tokens.pop(0)
        if len(tokens) >= 2 and re.match(r"^[A-Za-z_]\w*$", tokens[-1].rstrip(";")):
            fields.append(f"{tokens[-1]}: {' '.join(tokens[:-1])}")

    scan(0, len(source), "", "file", "", "")
    return [e for e in out if e is not None]


def _first_paren_after_name(masked: str, hs: int, he: int, name: str) -> int:
    """Offset of the '(' that opens the parameter list of method `name` in masked[hs:he]."""
    seg = masked[hs:he]
    # annotations were removed from the *header copy*, not from `masked`: skip their parentheses
    i = 0
    while i < len(seg):
        if seg[i] == "@" and not seg.startswith("@interface", i):
            m = re.match(r"@\s*[A-Za-z_][\w.]*\s*", seg[i:])
            if m:
                i += m.end()
                if i < len(seg) and seg[i] == "(":
                    i = _match(masked, hs + i, "(", ")") - hs + 1
                continue
        m = re.compile(rf"\b{re.escape(name)}\s*\(").match(seg, i)
        if m:
            return hs + m.end() - 1
        i += 1
    return hs + seg.find("(")
