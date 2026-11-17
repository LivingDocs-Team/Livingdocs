"""Java analysis with tree-sitter (replaces javalang, which only understands Java 8).

Handles Java 17 syntax (records, text blocks, switch expressions, sealed types...) and extracts:
classes, interfaces, enums and records (nested ones as `Outer.Inner`), their fields, methods and
constructors with line numbers and source, Javadoc, and Spring MVC endpoints
(@RequestMapping on the class + @GetMapping/@PostMapping/... or @RequestMapping on the method).
"""
import re
from typing import List, Optional, Tuple

import tree_sitter_java
from tree_sitter import Language, Node, Parser, Tree

from app.models import ClassField, ClassInfo, Endpoint, Function, Parameter

MAX_SOURCE_CHARS = 1500

_PARSER = Parser(Language(tree_sitter_java.language()))

TYPE_DECLS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}
BODY_TYPES = {"class_body", "interface_body", "enum_body", "enum_body_declarations",
              "annotation_type_body"}
MAPPINGS = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
            "DeleteMapping": "DELETE", "PatchMapping": "PATCH"}
REQUEST_METHOD = re.compile(r"RequestMethod\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)")
PARAM_ANNOTATIONS = {"PathVariable", "RequestParam", "RequestHeader", "CookieValue", "MatrixVariable"}


def parse_java(code: str) -> Tuple[Optional[Tree], Optional[str]]:
    """Parse Java source. Returns (tree, None) or (None, 'JavaSyntaxError line L:C: ...')."""
    tree = _PARSER.parse(code.encode("utf-8"))
    if not tree.root_node.has_error:
        return tree, None
    bad = _first_error(tree.root_node)
    if bad is None:
        return None, "JavaSyntaxError: invalid Java source"
    line, col = bad.start_point[0] + 1, bad.start_point[1] + 1
    if bad.is_missing:
        return None, f"JavaSyntaxError line {line}:{col}: missing '{bad.type}'"
    near = bad.text.decode("utf-8", "replace").strip().splitlines()[0][:40] if bad.text else ""
    return None, f"JavaSyntaxError line {line}:{col}: unexpected '{near}'"


def _first_error(node: Node) -> Optional[Node]:
    if node.type == "ERROR" or node.is_missing:
        return node
    for child in node.children:
        if child.has_error or child.is_missing or child.type == "ERROR":
            found = _first_error(child)
            if found is not None:
                return found
    return None


# ---------- helpers ----------

def _text(node: Optional[Node]) -> str:
    return node.text.decode("utf-8", "replace") if node is not None and node.text is not None else ""


def _child(node: Node, *types: str) -> Optional[Node]:
    return next((c for c in node.named_children if c.type in types), None)


def _javadoc(node: Node) -> Optional[str]:
    """`/** ... */` immediately before the declaration."""
    prev = node.prev_named_sibling
    if prev is None or prev.type != "block_comment":
        return None
    raw = _text(prev)
    if not raw.startswith("/**"):
        return None
    if node.start_point[0] - prev.end_point[0] > 1:     # separated by a blank line
        return None
    body = re.sub(r"^/\*\*+|\*+/$", "", raw.strip())
    lines = [re.sub(r"^\s*\*\s?", "", ln).rstrip() for ln in body.splitlines()]
    text = "\n".join(lines).strip()
    return text or None


def _annotations(node: Node) -> List[Node]:
    mods = _child(node, "modifiers")
    if mods is None:
        return []
    return [c for c in mods.named_children if c.type in ("annotation", "marker_annotation")]


def _annotation_name(ann: Node) -> str:
    name = ann.child_by_field_name("name")
    return _text(name).split(".")[-1]


def _annotation_values(ann: Node) -> Tuple[List[str], str]:
    """(paths, raw arguments) of an annotation like @GetMapping("/x") or @RequestMapping(value = {"/a"})."""
    args = ann.child_by_field_name("arguments")
    if args is None:
        return [], ""
    raw = _text(args)
    candidates = []
    for c in args.named_children:
        if c.type == "element_value_pair":
            key = _text(c.child_by_field_name("key"))
            if key in ("value", "path"):
                candidates.append(c.child_by_field_name("value"))
        else:
            candidates.append(c)
    paths = []
    for c in candidates:
        if c is None:
            continue
        literals = [c] if c.type == "string_literal" else [
            n for n in c.named_children if n.type == "string_literal"]
        for lit in literals:
            paths.append(_text(lit)[1:-1])
    return paths, raw


def _join(prefix: str, path: str) -> str:
    joined = "/".join(p.strip("/") for p in (prefix, path) if p and p.strip("/"))
    return "/" + joined


def _line_range(node: Node, code_lines: List[str]) -> Tuple[int, int, str]:
    """Start at the declaration itself (after annotations), end at the closing brace."""
    start_node = node
    mods = _child(node, "modifiers")
    if mods is not None:
        after = mods.next_named_sibling
        if after is not None:
            start_node = after
    start, end = start_node.start_point[0] + 1, node.end_point[0] + 1
    source = "\n".join(code_lines[start - 1:end])[:MAX_SOURCE_CHARS]
    return start, end, source


def _parameters(node: Node) -> List[Parameter]:
    params = node.child_by_field_name("parameters")
    out = []
    if params is None:
        return out
    for p in params.named_children:
        if p.type not in ("formal_parameter", "spread_parameter"):
            continue
        ptype = p.child_by_field_name("type") or _child(p, *("type_identifier", "generic_type", "array_type",
                                                              "integral_type", "floating_point_type",
                                                              "boolean_type", "scoped_type_identifier"))
        name = p.child_by_field_name("name")
        if name is None:  # spread_parameter: Type... name
            decl = _child(p, "variable_declarator")
            name = decl.child_by_field_name("name") if decl else None
        type_text = _text(ptype) + ("..." if p.type == "spread_parameter" else "")
        out.append(Parameter(name=_text(name), type=type_text or None))
    return out


def _function(node: Node, code_lines: List[str], class_name: str) -> Function:
    is_ctor = node.type in ("constructor_declaration", "compact_constructor_declaration")
    name = class_name.split(".")[-1] if is_ctor else _text(node.child_by_field_name("name"))
    params = _parameters(node)
    ret = None if is_ctor else _text(node.child_by_field_name("type")) or "void"
    sig_params = ", ".join(f"{p.type or 'Object'} {p.name}" for p in params)
    signature = f"{name}({sig_params})" if is_ctor else f"{ret} {name}({sig_params})"
    start, end, source = _line_range(node, code_lines)
    return Function(name=name, signature=signature, parameters=params, return_type=ret,
                    docstring=_javadoc(node), source=source, lineno=start, end_lineno=end)


def _fields(node: Node, body: Optional[Node], kind: str) -> List[ClassField]:
    out: List[ClassField] = []
    if kind == "record":
        params = node.child_by_field_name("parameters")
        for p in (params.named_children if params else []):
            if p.type == "formal_parameter":
                out.append(ClassField(name=_text(p.child_by_field_name("name")),
                                      type=_text(p.child_by_field_name("type")) or None,
                                      lineno=p.start_point[0] + 1))
    if body is None:
        return out
    if kind == "enum":
        for c in body.named_children:
            if c.type == "enum_constant":
                out.append(ClassField(name=_text(c.child_by_field_name("name")), type=None,
                                      lineno=c.start_point[0] + 1, description=_javadoc(c)))
        body = _child(body, "enum_body_declarations") or body
    for c in body.named_children:
        if c.type not in ("field_declaration", "constant_declaration"):
            continue
        ftype = _text(c.child_by_field_name("type")) or None
        for d in c.named_children:
            if d.type == "variable_declarator":
                value = d.child_by_field_name("value")
                out.append(ClassField(name=_text(d.child_by_field_name("name")), type=ftype,
                                      default=_text(value)[:200] if value is not None else None,
                                      lineno=c.start_point[0] + 1, description=_javadoc(c)))
    return out


def _endpoints(method: Node, fn: Function, prefixes: List[str],
               class_verbs: Optional[List[str]] = None) -> List[Endpoint]:
    out = []
    for ann in _annotations(method):
        name = _annotation_name(ann)
        if name in MAPPINGS:
            verbs = [MAPPINGS[name]]
        elif name == "RequestMapping":
            # no method= : inherit the class-level methods, else GET
            verbs = REQUEST_METHOD.findall(_annotation_values(ann)[1]) or class_verbs or ["GET"]
        else:
            continue
        paths = _annotation_values(ann)[0] or [""]
        params, body = [], None
        for p_node, p in zip([n for n in (method.child_by_field_name("parameters").named_children
                                          if method.child_by_field_name("parameters") else [])
                              if n.type in ("formal_parameter", "spread_parameter")], fn.parameters):
            anns = {_annotation_name(a) for a in _annotations(p_node)}
            if "RequestBody" in anns:
                body = p.type
            elif anns & PARAM_ANNOTATIONS:
                params.append(p)
        for prefix in prefixes or [""]:
            for path in paths:
                for verb in verbs:
                    out.append(Endpoint(http_method=verb, path=_join(prefix, path), handler=fn.name,
                                        parameters=params, request_body=body,
                                        response=fn.return_type if fn.return_type != "void" else None,
                                        lineno=fn.lineno, end_lineno=fn.end_lineno))
    return out


def _walk_types(node: Node, code_lines: List[str], outer: str,
                classes: List[ClassInfo], endpoints: List[Endpoint]) -> None:
    for c in node.named_children:
        kind = TYPE_DECLS.get(c.type)
        if kind is None:
            if c.type in BODY_TYPES:
                _walk_types(c, code_lines, outer, classes, endpoints)
            continue
        name = _text(c.child_by_field_name("name"))
        full = f"{outer}.{name}" if outer else name
        body = c.child_by_field_name("body")

        bases = []
        sup = c.child_by_field_name("superclass")
        if sup is not None:
            bases += [_text(t) for t in sup.named_children]
        for field in ("interfaces",):
            n = c.child_by_field_name(field)
            if n is not None:
                tl = _child(n, "type_list")
                bases += [_text(t) for t in (tl.named_children if tl else n.named_children)]
        ext = _child(c, "extends_interfaces")
        if ext is not None:
            tl = _child(ext, "type_list")
            bases += [_text(t) for t in (tl.named_children if tl else ext.named_children)]

        prefixes, class_verbs = [], []
        for ann in _annotations(c):
            if _annotation_name(ann) == "RequestMapping":
                paths, raw = _annotation_values(ann)
                prefixes = paths or [""]
                class_verbs = list(dict.fromkeys(REQUEST_METHOD.findall(raw)))
        is_controller = any(_annotation_name(a) in ("RestController", "Controller") for a in _annotations(c))

        methods = []
        members = []
        if body is not None:
            members = list(body.named_children)
            decls = _child(body, "enum_body_declarations")
            if decls is not None:
                members += list(decls.named_children)
        for m in members:
            if m.type in ("method_declaration", "constructor_declaration", "compact_constructor_declaration"):
                fn = _function(m, code_lines, full)
                methods.append(fn)
                if m.type == "method_declaration" and (is_controller or prefixes):
                    endpoints.extend(_endpoints(m, fn, prefixes, class_verbs))
                elif m.type == "method_declaration":
                    # mapping annotations without a controller annotation still describe a route
                    if any(_annotation_name(a) in MAPPINGS or _annotation_name(a) == "RequestMapping"
                           for a in _annotations(m)):
                        endpoints.extend(_endpoints(m, fn, prefixes, class_verbs))

        start = c.start_point[0] + 1
        mods = _child(c, "modifiers")
        if mods is not None and mods.next_sibling is not None:
            start = mods.next_sibling.start_point[0] + 1
        classes.append(ClassInfo(name=full, kind=kind, bases=bases, docstring=_javadoc(c),
                                 methods=methods, fields=_fields(c, body, kind),
                                 lineno=start, end_lineno=c.end_point[0] + 1))
        if body is not None:
            _walk_types(body, code_lines, full, classes, endpoints)


def extract_java(tree: Tree, code: str):
    """Returns (classes, functions, endpoints, package)."""
    classes: List[ClassInfo] = []
    endpoints: List[Endpoint] = []
    _walk_types(tree.root_node, code.splitlines(), "", classes, endpoints)
    pkg = _child(tree.root_node, "package_declaration")
    package = None
    if pkg is not None:
        ident = _child(pkg, "scoped_identifier", "identifier")
        package = _text(ident) or None
    return classes, [], endpoints, package


def java_imports(tree: Tree) -> List[str]:
    out = []
    for c in tree.root_node.named_children:
        if c.type == "import_declaration":
            out.append(_text(c).removeprefix("import").removesuffix(";").replace("static ", "").strip())
    return sorted(set(out))
