"""Deterministic Markdown rendering (LD-340).

Structure comes from the analysis + template; descriptions come from FileDoc.
Every file is rendered with the same layout regardless of what the AI returned.
"""
from typing import Dict, List, Optional, Tuple

from .doc_schema import ClassDoc, EndpointDoc, FileDoc, FunctionDoc
from .evidence import location
from .models import (ClassInfo, Endpoint, EntityReport, Evidence, FileAnalysis, Function,
                     Parameter, Template)

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
        "confidence": "Độ tin cậy", "evidence": "Bằng chứng", "sources": "Nguồn tham chiếu",
        "levels": {"high": "cao", "medium": "trung bình", "low": "thấp"},
        "lines": "dòng", "overall": "Độ tin cậy chung",
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
        "confidence": "Confidence", "evidence": "Evidence", "sources": "References",
        "levels": {"high": "high", "medium": "medium", "low": "low"},
        "lines": "lines", "overall": "Overall confidence",
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


def doc_items(doc: FileDoc) -> Dict[str, object]:
    """Described items keyed like evidence.entities(): Class, Class.method, func, 'GET /p'."""
    items: Dict[str, object] = {}
    for c in doc.classes:
        items[c.name] = c
        for m in c.methods:
            items[f"{c.name}.{m.name}"] = m
    for fn in doc.functions:
        items[fn.name] = fn
    for e in doc.endpoints:
        items[f"{e.method.strip().upper()} {e.path}"] = e
    return items


def _score_text(score: Optional[float], L: dict) -> str:
    if score is None:
        return "-"
    lvl = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    return f"{score:.2f} ({L['levels'][lvl]})"


def _ev_ref(ev: Evidence) -> str:
    loc = f"`{location(ev)}`"
    return loc if ev.kind.value == "source" else f"{ev.id} {loc}"


def _annotation(rep: Optional[EntityReport], L: dict) -> str:
    if rep is None:
        return ""
    refs = ", ".join(_ev_ref(e) for e in rep.evidence) or "-"
    return (f"> {L['confidence']}: **{_score_text(rep.confidence, L)}** · "
            f"{L['evidence']}: {refs}\n")


def _params_table(params: List[Parameter], descs: Dict[str, str], L: dict) -> str:
    if not params:
        return f"_{L['no_params']}_\n"
    rows = [f"| {L['name']} | {L['type']} | {L['default']} | {L['desc']} |", "|---|---|---|---|"]
    for p in params:
        desc = descs.get(p.name) or p.description
        rows.append(f"| `{p.name}` | {_cell(p.type)} | {_cell(p.default)} | {_cell(desc)} |")
    return "\n".join(rows) + "\n"


def _function_md(fn: Function, doc: Optional[FunctionDoc], level: str, L: dict,
                 rep: Optional[EntityReport] = None) -> str:
    sig = fn.signature or f"{fn.name}({', '.join(p.name for p in fn.parameters)})"
    summary = (doc.summary if doc else "") or (fn.docstring or "").strip() or L["no_desc"]
    pdescs = {p.name: p.description for p in doc.parameters} if doc else {}
    returns = (doc.returns if doc else "") or ""
    rtype = f"`{fn.return_type}`" if fn.return_type else L["unknown"]
    ret_line = f"{rtype} — {returns}" if returns else rtype
    return "\n".join([
        f"{level} `{fn.name}`", "", f"```\n{sig}\n```", "", summary, "",
        f"**{L['params']}**", "", _params_table(fn.parameters, pdescs, L),
        f"**{L['returns']}:** {ret_line}", "", _annotation(rep, L),
    ])


def _class_md(c: ClassInfo, doc: Optional[ClassDoc], L: dict,
              reps: Dict[str, EntityReport]) -> str:
    bases = f" ({L['inherits']} {', '.join(c.bases)})" if c.bases else ""
    summary = (doc.summary if doc else "") or (c.docstring or "").strip() or L["no_desc"]
    mdocs = _by_name(doc.methods) if doc else {}
    out = [f"### {L['class']} `{c.name}`{bases}", "", summary, "", _annotation(reps.get(c.name), L)]
    for m in c.methods:
        out.append(_function_md(m, mdocs.get(m.name), "####", L, reps.get(f"{c.name}.{m.name}")))
    return "\n".join(out)


def _endpoint_md(e: Endpoint, summary: str, L: dict, rep: Optional[EntityReport] = None) -> str:
    out = [f"### `{e.http_method} {e.path}`", "", summary or L["no_desc"], ""]
    if e.handler:
        out += [f"{L['handler']}: `{e.handler}`", ""]
    out += [f"**{L['params']}**", "", _params_table(e.parameters, {}, L)]
    if e.request_body:
        out += [f"**{L['request']}:** {e.request_body}", ""]
    out += [f"**{L['response']}:** {e.response or L['unknown']}", "", _annotation(rep, L)]
    return "\n".join(out)


def render_file(f: FileAnalysis, doc: FileDoc, tpl: Template, lang: str,
                reports: Optional[Dict[str, EntityReport]] = None,
                file_confidence: Optional[float] = None,
                context_used: Optional[List[Evidence]] = None) -> str:
    L = _labels(lang)
    reps = reports or {}
    cdocs = _by_name(doc.classes)
    fdocs = _by_name(doc.functions)
    edocs = {(e.method.strip().upper(), e.path): e.summary for e in doc.endpoints}

    parts = [f"# {f.path}", ""]
    for section in tpl.sections:
        key = KNOWN_SECTIONS.get(section.strip().lower())
        body = ""
        if key == "Overview":
            stats = L["stats"].format(c=len(f.classes), f=len(f.functions), e=len(f.endpoints))
            meta = f"{L['language']}: {f.language or '-'} · {L['module']}: {f.module or '-'} · {stats}"
            if file_confidence is not None:
                meta += f" · {L['confidence']}: {_score_text(file_confidence, L)}"
            text = doc.overview or (L["nothing"] if f.entity_count() == 0 else "")
            body = "\n\n".join(x for x in [text, f"_{meta}_"] if x)
        elif key == "Classes" and f.classes:
            body = "\n".join(_class_md(c, cdocs.get(c.name), L, reps) for c in f.classes)
        elif key == "Functions" and f.functions:
            body = "\n".join(_function_md(fn, fdocs.get(fn.name), "###", L, reps.get(fn.name))
                             for fn in f.functions)
        elif key == "API Endpoints" and f.endpoints:
            body = "\n".join(
                _endpoint_md(e, edocs.get((e.http_method, e.path), ""), L,
                             reps.get(f"{e.http_method} {e.path}"))
                for e in f.endpoints
            )
        if body:
            parts += [f"## {L[key]}", "", body.rstrip(), ""]
    if context_used:
        ordered = sorted(context_used, key=lambda ev: (ev.id[0], int(ev.id[1:] or 0)))
        refs = [f"- **{ev.id}** {ev.name or ''} — `{location(ev)}`".rstrip() for ev in ordered]
        parts += [f"## {L['sources']}", "", "\n".join(refs), ""]
    return "\n".join(parts).rstrip() + "\n"


def render_overview(target: str, documented: List[Tuple[str, str, Optional[float]]],
                    skipped: List[Tuple[str, str]], lang: str,
                    overall: Optional[float] = None) -> str:
    """documented: (path, status, confidence) ; skipped: (path, reason)."""
    L = _labels(lang)
    lines = [f"# {target}", "", L["repo_intro"].format(n=len(documented))]
    if overall is not None:
        lines += ["", f"{L['overall']}: **{_score_text(overall, L)}**"]
    lines += ["", f"## {L['files_title']}", ""]
    lines += [f"- `{p}` — {L['status'].get(s, s)}"
              + (f" · {L['confidence'].lower()} {_score_text(c, L)}" if c is not None else "")
              for p, s, c in documented]
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
