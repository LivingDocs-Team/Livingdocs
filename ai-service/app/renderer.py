"""Deterministic Markdown rendering (LD-340).

Structure comes from the analysis + template; descriptions come from FileDoc.
Every file is rendered with the same layout regardless of what the AI returned.
"""
from typing import Dict, List, Optional, Tuple

from .doc_schema import ClassDoc, FileDoc, FunctionDoc
from .models import ClassInfo, Endpoint, FileAnalysis, Function, Parameter, Template

LABELS = {
    "vi": {
        "Overview": "Tổng quan", "Classes": "Các lớp", "Functions": "Các hàm",
        "API Endpoints": "API Endpoints",
        "class": "Lớp", "inherits": "kế thừa", "params": "Tham số", "returns": "Giá trị trả về",
        "no_params": "Không có tham số.", "unknown": "Không xác định", "no_desc": "Chưa có mô tả.",
        "name": "Tên", "type": "Kiểu", "default": "Mặc định", "desc": "Mô tả",
        "handler": "Hàm xử lý", "request": "Request body", "response": "Response",
        "language": "Ngôn ngữ", "module": "Module",
        "stats": "{c} lớp, {f} hàm, {e} endpoint",
        "nothing": "Không tìm thấy lớp, hàm hoặc endpoint nào trong file này.",
        "files_title": "Danh sách file", "skipped_title": "File không sinh được tài liệu",
        "repo_intro": "Tài liệu cho {n} file.",
        "status": {"generated": "AI", "offline": "offline", "fallback": "dự phòng (AI lỗi)"},
    },
    "en": {
        "Overview": "Overview", "Classes": "Classes", "Functions": "Functions",
        "API Endpoints": "API Endpoints",
        "class": "Class", "inherits": "inherits", "params": "Parameters", "returns": "Returns",
        "no_params": "No parameters.", "unknown": "Not specified", "no_desc": "No description.",
        "name": "Name", "type": "Type", "default": "Default", "desc": "Description",
        "handler": "Handler", "request": "Request body", "response": "Response",
        "language": "Language", "module": "Module",
        "stats": "{c} class(es), {f} function(s), {e} endpoint(s)",
        "nothing": "No classes, functions or endpoints were found in this file.",
        "files_title": "Files", "skipped_title": "Files without documentation",
        "repo_intro": "Documentation for {n} file(s).",
        "status": {"generated": "AI", "offline": "offline", "fallback": "fallback (AI error)"},
    },
}

KNOWN_SECTIONS = {"overview": "Overview", "classes": "Classes",
                  "functions": "Functions", "api endpoints": "API Endpoints"}


def _labels(lang: str) -> dict:
    return LABELS.get(lang, LABELS["en"])


def _by_name(items) -> Dict[str, object]:
    return {i.name: i for i in items}


def _cell(text: Optional[str]) -> str:
    return (text or "-").replace("|", "\\|").replace("\n", " ")


def _params_table(params: List[Parameter], descs: Dict[str, str], L: dict) -> str:
    if not params:
        return f"_{L['no_params']}_\n"
    rows = [f"| {L['name']} | {L['type']} | {L['default']} | {L['desc']} |", "|---|---|---|---|"]
    for p in params:
        desc = descs.get(p.name) or p.description
        rows.append(f"| `{p.name}` | {_cell(p.type)} | {_cell(p.default)} | {_cell(desc)} |")
    return "\n".join(rows) + "\n"


def _function_md(fn: Function, doc: Optional[FunctionDoc], level: str, L: dict) -> str:
    sig = fn.signature or f"{fn.name}({', '.join(p.name for p in fn.parameters)})"
    summary = (doc.summary if doc else "") or (fn.docstring or "").strip() or L["no_desc"]
    pdescs = {p.name: p.description for p in doc.parameters} if doc else {}
    returns = (doc.returns if doc else "") or ""
    rtype = f"`{fn.return_type}`" if fn.return_type else L["unknown"]
    ret_line = f"{rtype} — {returns}" if returns else rtype
    return "\n".join([
        f"{level} `{fn.name}`", "", f"```\n{sig}\n```", "", summary, "",
        f"**{L['params']}**", "", _params_table(fn.parameters, pdescs, L),
        f"**{L['returns']}:** {ret_line}", "",
    ])


def _class_md(c: ClassInfo, doc: Optional[ClassDoc], L: dict) -> str:
    bases = f" ({L['inherits']} {', '.join(c.bases)})" if c.bases else ""
    summary = (doc.summary if doc else "") or (c.docstring or "").strip() or L["no_desc"]
    mdocs = _by_name(doc.methods) if doc else {}
    out = [f"### {L['class']} `{c.name}`{bases}", "", summary, ""]
    for m in c.methods:
        out.append(_function_md(m, mdocs.get(m.name), "####", L))
    return "\n".join(out)


def _endpoint_md(e: Endpoint, summary: str, L: dict) -> str:
    out = [f"### `{e.http_method} {e.path}`", "", summary or L["no_desc"], ""]
    if e.handler:
        out += [f"{L['handler']}: `{e.handler}`", ""]
    out += [f"**{L['params']}**", "", _params_table(e.parameters, {}, L)]
    if e.request_body:
        out += [f"**{L['request']}:** {e.request_body}", ""]
    out += [f"**{L['response']}:** {e.response or L['unknown']}", ""]
    return "\n".join(out)


def render_file(f: FileAnalysis, doc: FileDoc, tpl: Template, lang: str) -> str:
    L = _labels(lang)
    cdocs = _by_name(doc.classes)
    fdocs = _by_name(doc.functions)
    edocs = {(e.method.upper(), e.path): e.summary for e in doc.endpoints}

    parts = [f"# {f.path}", ""]
    for section in tpl.sections:
        key = KNOWN_SECTIONS.get(section.strip().lower())
        body = ""
        if key == "Overview":
            stats = L["stats"].format(c=len(f.classes), f=len(f.functions), e=len(f.endpoints))
            meta = f"{L['language']}: {f.language or '-'} · {L['module']}: {f.module or '-'} · {stats}"
            text = doc.overview or (L["nothing"] if f.entity_count() == 0 else "")
            body = "\n\n".join(x for x in [text, f"_{meta}_"] if x)
        elif key == "Classes" and f.classes:
            body = "\n".join(_class_md(c, cdocs.get(c.name), L) for c in f.classes)
        elif key == "Functions" and f.functions:
            body = "\n".join(_function_md(fn, fdocs.get(fn.name), "###", L) for fn in f.functions)
        elif key == "API Endpoints" and f.endpoints:
            body = "\n".join(
                _endpoint_md(e, edocs.get((e.http_method, e.path), ""), L) for e in f.endpoints
            )
        if body:
            parts += [f"## {L[key]}", "", body.rstrip(), ""]
    return "\n".join(parts).rstrip() + "\n"


def render_overview(target: str, documented: List[Tuple[str, str]],
                    skipped: List[Tuple[str, str]], lang: str) -> str:
    """documented: (path, status) ; skipped: (path, reason)."""
    L = _labels(lang)
    lines = [f"# {target}", "", L["repo_intro"].format(n=len(documented)), "",
             f"## {L['files_title']}", ""]
    lines += [f"- `{p}` ({L['status'].get(s, s)})" for p, s in documented]
    if skipped:
        lines += ["", f"## {L['skipped_title']}", ""]
        lines += [f"- `{p}`: {reason}" for p, reason in skipped]
    return "\n".join(lines) + "\n"


def missing_entities(f: FileAnalysis, doc: FileDoc) -> List[str]:
    """Entities in the analysis that the AI did not describe."""
    missing = []
    cdocs = _by_name(doc.classes)
    for c in f.classes:
        cd = cdocs.get(c.name)
        if cd is None:
            missing.append(c.name)
            continue
        mdocs = _by_name(cd.methods)
        missing += [f"{c.name}.{m.name}" for m in c.methods if m.name not in mdocs]
    fdocs = _by_name(doc.functions)
    missing += [fn.name for fn in f.functions if fn.name not in fdocs]
    edocs = {(e.method.upper(), e.path) for e in doc.endpoints}
    missing += [f"{e.http_method} {e.path}" for e in f.endpoints
                if (e.http_method, e.path) not in edocs]
    return missing


def unknown_entities(f: FileAnalysis, doc: FileDoc) -> List[str]:
    """Entities the AI described that do not exist in the analysis (ignored when rendering)."""
    known_c = _by_name(f.classes)
    extra = [c.name for c in doc.classes if c.name not in known_c]
    for cd in doc.classes:
        if cd.name in known_c:
            names = {m.name for m in known_c[cd.name].methods}
            extra += [f"{cd.name}.{m.name}" for m in cd.methods if m.name not in names]
    fnames = {fn.name for fn in f.functions}
    extra += [fd.name for fd in doc.functions if fd.name not in fnames]
    return extra
