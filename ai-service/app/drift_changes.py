"""LD-146 Analyze Pull Request changes.

Turns the changed files of a Pull Request into a list of changed *code entities*
(class, method, function, endpoint) - the unit documentation describes.

Two ways, per file, best first:

1. analysis  - the code analyzer's result for the file at the base commit (`before`) and the head
               commit (`after`) are compared entity by entity (same keys as the evidence catalog,
               app/evidence.py: `Class`, `Class.method`, `function`, `GET /path`). The diff
               (`patch`) is then only used to find bodies that changed and to count lines.
2. patch     - only the unified diff is known: declarations (def / class / Java methods / route
               annotations) are read from the removed and added lines, and the enclosing function
               of every other changed line (hunk header or a declaration above it) is marked as
               changed. Less exact: e.g. a parameter list spread over several lines is cut.

Renames are recognised when a removed and an added entity of the same kind have the same shape
(parameters and return type, class fields and methods, endpoint handler).
"""
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .drift_models import (ChangedFile, ChangeStatus, DiffHunk, EntityChange, EntityChangeType,
                           FileChangeSummary, PullRequestAnalysis, PullRequestInfo)
from .drift_semantic import code_key, extract_signals, line_key, without_renames
from .drift_signature import assess, parameter_changes, parse_java_param, parse_python_param
from .evidence import entities
from .models import AnalysisStatus, ClassInfo, Endpoint, FileAnalysis, Function, Parameter

# ---------- unified diff ----------

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")


def parse_patch(patch: Optional[str]) -> List[DiffHunk]:
    """Hunks of a unified diff (GitHub `patch` field or `git diff` output for one file)."""
    hunks: List[DiffHunk] = []
    if not patch:
        return hunks
    current: Optional[DiffHunk] = None
    for line in patch.splitlines():
        m = HUNK_RE.match(line)
        if m:
            current = DiffHunk(old_start=int(m.group(1)), old_lines=int(m.group(2) or 1),
                               new_start=int(m.group(3)), new_lines=int(m.group(4) or 1),
                               header=m.group(5).strip())
            hunks.append(current)
        elif current is not None and line[:1] in (" ", "+", "-", ""):
            current.lines.append(line if line else " ")
        # '\ No newline at end of file', 'diff --git', '---', '+++' lines are ignored
    return hunks


def numbered(hunk: DiffHunk) -> Iterable[Tuple[Optional[int], Optional[int], str]]:
    """(old line number, new line number, line) for every line of a hunk; a removed line has no
    new number, an added line no old number."""
    old, new = hunk.old_start, hunk.new_start
    for line in hunk.lines:
        tag = line[:1]
        if tag == "+":
            yield None, new, line
            new += 1
        elif tag == "-":
            yield old, None, line
            old += 1
        else:
            yield old, new, line
            old += 1
            new += 1


def count_changes(hunks: List[DiffHunk]) -> Tuple[int, int]:
    adds = sum(1 for h in hunks for line in h.lines if line.startswith("+"))
    dels = sum(1 for h in hunks for line in h.lines if line.startswith("-"))
    return adds, dels


def changed_lines_in(hunks: List[DiffHunk], old_range: Optional[Tuple[int, int]],
                     new_range: Optional[Tuple[int, int]]) -> int:
    """Number of added lines inside `new_range` plus removed lines inside `old_range`."""
    n = 0
    for h in hunks:
        for o, nw, line in numbered(h):
            if line.startswith("+") and new_range and nw is not None and new_range[0] <= nw <= new_range[1]:
                n += 1
            elif line.startswith("-") and old_range and o is not None and old_range[0] <= o <= old_range[1]:
                n += 1
    return n


# ---------- tickets ----------

TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
NOT_TICKETS = {"UTF", "ISO", "SHA", "RFC", "HTTP", "TLS", "SSL", "UTC", "GMT", "CVE"}


def find_tickets(pr: PullRequestInfo) -> List[str]:
    """Jira keys (e.g. LD-145) named in the PR title, branch or description, in that order."""
    out: List[str] = []
    # branch names are often lower case ("ld-145-drift-detection")
    for text in (pr.title, (pr.head_branch or "").upper(), pr.body or ""):
        for key in TICKET_RE.findall(text):
            if key.split("-")[0] not in NOT_TICKETS and key not in out:
                out.append(key)
    return out


# ---------- entity shapes (analysis mode) ----------

def _param(p: Parameter) -> str:
    s = p.name + (f": {p.type}" if p.type else "")
    return s + (f" = {p.default}" if p.default is not None else "")


def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


@dataclass
class Shape:
    kind: str
    key: str
    signature: str                    # human readable, compared to detect signature changes
    params: List[str] = field(default_factory=list)    # parameter names (or fields for classes)
    contract: Tuple = ()              # what must be equal for "same signature"
    body: Optional[str] = None        # source / docstring, compared to detect behaviour changes
    docstring: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    rename_key: Tuple = ()            # what must be equal for "renamed"
    recognisable: bool = True         # False: too little information to pair a rename
    param_info: List[Tuple] = field(default_factory=list)   # (name, type, default), LD-153
    source: Optional[str] = None      # raw source, LD-154
    handler: Optional[str] = None     # endpoints


def _function_shape(kind: str, key: str, fn: Function, lang: Optional[str] = None) -> Shape:
    if fn.parameters:
        params = [_param(p) for p in fn.parameters]
        sig = f"{fn.name}({', '.join(params)})" + (f" -> {fn.return_type}" if fn.return_type else "")
        contract = (tuple(params), _norm(fn.return_type))
    else:
        sig = _norm(fn.signature) or f"{fn.name}()" + (f" -> {fn.return_type}" if fn.return_type else "")
        # the analyzer's signature starts with the name; leave it out so a rename keeps the shape
        contract = (_norm(fn.signature).split("(", 1)[-1] if fn.signature else "",
                    _norm(fn.return_type))
    body = fn.source
    if body:  # a renamed function keeps its body: compare it without the name (LD-347: and
        # without comments / formatting, which change nothing)
        body = code_key(re.sub(rf"\b{re.escape(fn.name)}\b", "<name>", body), lang)
    return Shape(kind, key, sig, [p.name for p in fn.parameters], contract, body,
                 _norm(fn.docstring) or None, fn.line_start, fn.line_end,
                 rename_key=(kind, contract, body or ""),
                 recognisable=bool(fn.parameters or fn.return_type or body or fn.signature),
                 param_info=[(p.name, p.type, p.default) for p in fn.parameters], source=fn.source)


def _class_shape(c: ClassInfo) -> Shape:
    fields_ = [f.name + (f": {f.type}" if f.type else "") for f in c.fields]
    sig = f"{c.kind or 'class'} {c.name}" + (f"({', '.join(c.bases)})" if c.bases else "")
    if fields_:
        sig += " {" + ", ".join(fields_) + "}"
    contract = (c.kind or "class", tuple(c.bases), tuple(fields_))
    methods = tuple(sorted(m.name for m in c.methods))
    return Shape("class", c.name, sig, [f.name for f in c.fields], contract, None,
                 _norm(c.docstring) or None, c.line_start, c.line_end,
                 rename_key=("class", contract, methods),
                 recognisable=bool(fields_ or methods or c.bases),
                 param_info=[(f.name, f.type, f.default) for f in c.fields])


def _endpoint_shape(e: Endpoint) -> Shape:
    params = [_param(p) for p in e.parameters]
    key = f"{e.http_method} {e.path}"
    sig = key + (f" ({', '.join(params)})" if params else "")
    if e.request_body:
        sig += f" body: {e.request_body}"
    if e.response:
        sig += f" -> {e.response}"
    contract = (tuple(params), _norm(e.request_body), _norm(e.response))
    return Shape("endpoint", key, sig, [p.name for p in e.parameters], contract, None, None,
                 e.line_start, e.line_end,
                 rename_key=("endpoint", e.http_method, e.handler or "", contract),
                 recognisable=bool(e.handler),
                 param_info=[(p.name, p.type, p.default) for p in e.parameters], handler=e.handler)


def shapes(f: Optional[FileAnalysis]) -> Dict[str, Shape]:
    if f is None or f.status != AnalysisStatus.ok:
        return {}
    out: Dict[str, Shape] = {}
    for ent in entities(f):
        if ent.kind in ("function", "method"):
            out[ent.key] = _function_shape(ent.kind, ent.key, ent.obj, _lang(f.language, f.path))
        elif ent.kind == "class":
            out[ent.key] = _class_shape(ent.obj)
        else:
            out[ent.key] = _endpoint_shape(ent.obj)
    return out


def _range(s: Shape) -> Optional[Tuple[int, int]]:
    if s.line_start is None:
        return None
    return s.line_start, s.line_end or s.line_start


def _param_names(params: List[str]) -> List[str]:
    return [re.split(r"[:=\s]", p.strip().lstrip("*@"), maxsplit=1)[0] for p in params if p.strip()]


def _signature_details(old: Shape, new: Shape) -> Tuple[List[str], List[str], List[str]]:
    """Readable details and removed / added parameter names (LD-146)."""
    info = signature_change(old, new)
    return info["details"], info["removed_parameters"], info["added_parameters"]


def signature_change(old: Shape, new: Shape) -> dict:
    """LD-146 + LD-153: what exactly changed in the contract of an entity (EntityChange fields)."""
    removed = [p for p in old.params if p not in new.params]
    added = [p for p in new.params if p not in old.params]
    params = parameter_changes(old.param_info, new.param_info)
    aspects: List[str] = []
    details = []
    if removed:
        details.append("removed parameter(s): " + ", ".join(removed))
    if added:
        details.append("added parameter(s): " + ", ".join(added))
    for c in params:
        if c.change.value in ("type_changed", "default_removed", "default_added", "default_changed",
                              "reordered"):
            details.append(f"parameter {c.name}: " + {
                "type_changed": f"type {c.old_type} -> {c.new_type}",
                "default_removed": f"now required (default {c.old_default} removed)",
                "default_added": f"now optional (default {c.new_default})",
                "default_changed": f"default {c.old_default} -> {c.new_default}",
                "reordered": "order changed"}[c.change.value])
    old_ret = new_ret = None
    if old.kind in ("function", "method"):
        if old.contract[0] != new.contract[0]:
            aspects.append("parameters")
        if old.contract[1:] != new.contract[1:]:
            aspects.append("return_type")
            old_ret, new_ret = old.contract[1] or None, new.contract[1] or None
            details.append(f"return type: {old.contract[1] or '-'} -> {new.contract[1] or '-'}")
    if old.kind == "class":
        if old.contract[0] != new.contract[0]:
            aspects.append("kind")
            details.append(f"kind: {old.contract[0]} -> {new.contract[0]}")
        if old.contract[1] != new.contract[1]:
            aspects.append("bases")
            details.append(f"bases: {', '.join(old.contract[1]) or '-'} -> "
                           f"{', '.join(new.contract[1]) or '-'}")
        if old.contract[2] != new.contract[2]:
            aspects.append("fields")
    if old.kind == "endpoint":
        if old.contract[0] != new.contract[0]:
            aspects.append("parameters")
        if old.contract[1] != new.contract[1]:
            aspects.append("request_body")
            details.append(f"request body: {old.contract[1] or '-'} -> {new.contract[1] or '-'}")
        if old.contract[2] != new.contract[2]:
            aspects.append("response")
            details.append(f"response: {old.contract[2] or '-'} -> {new.contract[2] or '-'}")
    if not details:
        details.append(f"signature: {old.signature} -> {new.signature}")
    return dict(details=details, removed_parameters=removed, added_parameters=added,
                aspects=aspects, parameter_changes=params, old_return_type=old_ret,
                new_return_type=new_ret, breaking=assess(old.kind, aspects, params))


def _renames(params, removed: List[str], added: List[str]) -> List[Tuple[str, str]]:
    """Old -> new names of renamed (or removed + added in the same number) parameters."""
    pairs = [(p.old_name, p.name) for p in params if p.change.value == "renamed" and p.old_name]
    if not pairs and removed and len(removed) == len(added):
        pairs = list(zip(removed, added))
    return pairs


def _path_key(endpoint_key: str) -> str:
    path = endpoint_key.split(" ", 1)[-1]
    return re.sub(r"\{[^}/]*\}|:\w+|<[^>/]*>", "{}", path).rstrip("/") or "/"


def _pair_methods(removed: Dict[str, Shape], added: Dict[str, Shape]) -> List[Tuple[Shape, Shape]]:
    """LD-153: an endpoint that keeps its path (and handler) but changes its HTTP method."""
    pairs = []
    for ok, o in list(removed.items()):
        if o.kind != "endpoint":
            continue
        verb = ok.split(" ", 1)[0]
        same = [a for a in added.values() if a.kind == "endpoint"
                and _path_key(a.key) == _path_key(ok) and a.key.split(" ", 1)[0] != verb
                and (a.handler == o.handler or not (a.handler and o.handler))]
        if len(same) == 1:
            pairs.append((o, same[0]))
            removed.pop(ok)
            added.pop(same[0].key)
    return pairs


def _diff_texts(hunks: List[DiffHunk], old_range: Optional[Tuple[int, int]],
                new_range: Optional[Tuple[int, int]]) -> Tuple[str, str]:
    """Removed lines inside `old_range` and added lines inside `new_range` (LD-154 signals)."""
    old, new = [], []
    for h in hunks:
        for o, n, line in numbered(h):
            if line.startswith("-") and old_range and o is not None and old_range[0] <= o <= old_range[1]:
                old.append(line[1:])
            elif line.startswith("+") and new_range and n is not None and new_range[0] <= n <= new_range[1]:
                new.append(line[1:])
    return "\n".join(old), "\n".join(new)


def _pair_renames(removed: Dict[str, Shape], added: Dict[str, Shape]) -> List[Tuple[Shape, Shape]]:
    pairs = []
    for ok, o in list(removed.items()):
        if not o.recognisable:
            continue  # nothing to recognise it by (no params, no body, no fields)
        same = [a for a in added.values() if a.kind == o.kind and a.rename_key == o.rename_key]
        if o.kind == "method":  # a method moves only together with its class (see below)
            same = [a for a in same if a.key.split(".")[0] == o.key.split(".")[0]]
        if len(same) == 1:
            pairs.append((o, same[0]))
            removed.pop(ok)
            added.pop(same[0].key)
    return pairs


def _lang(language: Optional[str], path: str) -> Optional[str]:
    lang = (language or "").lower() or language_of(path)
    return lang if lang in ("python", "java") else None


def _without_handler_duplicates(changes: List[EntityChange], after: Dict[str, Shape]) -> List[EntityChange]:
    """LD-347: an endpoint whose only change is its parameters, when its handler function's
    signature changed too, is the same change seen twice: keep it on the handler (whose
    parameters the documentation lists) and drop the endpoint's copy."""
    changed = {c.name for c in changes if c.change == EntityChangeType.signature_changed
               and c.kind in ("function", "method")}
    out = []
    for c in changes:
        shape = after.get(c.name)
        handler = shape.handler if shape is not None else None
        if (c.kind == "endpoint" and c.change == EntityChangeType.signature_changed
                and c.aspects == ["parameters"] and handler
                and any(name == handler or name.endswith("." + handler) for name in changed)):
            continue
        out.append(c)
    return out


def compare_analyses(cf: ChangedFile, hunks: List[DiffHunk]) -> List[EntityChange]:
    before, after = shapes(cf.before), shapes(cf.after)
    lang = _lang((cf.after or cf.before).language, cf.path)
    path, prev = cf.path, cf.previous_path if cf.previous_path != cf.path else None
    changes: List[EntityChange] = []

    removed = {k: s for k, s in before.items() if k not in after}
    added = {k: s for k, s in after.items() if k not in before}

    # classes first: when a class is renamed its methods keep their names under the new class
    class_pairs = _pair_renames({k: s for k, s in removed.items() if s.kind == "class"},
                                {k: s for k, s in added.items() if s.kind == "class"})
    for o, n in class_pairs:
        removed.pop(o.key)
        added.pop(n.key)
        for mk in [k for k in removed if k.startswith(o.key + ".")]:
            nk = n.key + mk[len(o.key):]
            if nk in added:
                before[nk] = removed.pop(mk)
                added.pop(nk)
        changes.append(EntityChange(path=path, previous_path=prev, kind="class", name=n.key,
                                    change=EntityChangeType.renamed, old_name=o.key,
                                    old_signature=o.signature, new_signature=n.signature,
                                    details=[f"renamed: {o.key} -> {n.key}"],
                                    line_start=n.line_start, line_end=n.line_end,
                                    old_line_start=o.line_start, old_line_end=o.line_end))
    for o, n in _pair_methods(removed, added):
        info = signature_change(o, n)
        info["aspects"] = ["http_method"] + info["aspects"]
        info["details"] = [f"HTTP method: {o.key.split(' ', 1)[0]} -> {n.key.split(' ', 1)[0]}"] + \
            [d for d in info["details"] if not d.startswith("signature:")]
        info["breaking"] = True
        changes.append(EntityChange(path=path, previous_path=prev, kind="endpoint", name=n.key,
                                    change=EntityChangeType.signature_changed, old_name=o.key,
                                    old_signature=o.signature, new_signature=n.signature,
                                    line_start=n.line_start, line_end=n.line_end,
                                    old_line_start=o.line_start, old_line_end=o.line_end,
                                    changed_lines=changed_lines_in(hunks, _range(o), _range(n)), **info))
    for o, n in _pair_renames(removed, added):
        changes.append(EntityChange(path=path, previous_path=prev, kind=n.kind, name=n.key,
                                    change=EntityChangeType.renamed, old_name=o.key,
                                    old_signature=o.signature, new_signature=n.signature,
                                    details=[f"renamed: {o.key} -> {n.key}"],
                                    line_start=n.line_start, line_end=n.line_end,
                                    old_line_start=o.line_start, old_line_end=o.line_end))
    for o in removed.values():
        changes.append(EntityChange(path=path, previous_path=prev, kind=o.kind, name=o.key,
                                    change=EntityChangeType.removed, old_signature=o.signature,
                                    details=["removed"], removed_parameters=list(o.params),
                                    old_line_start=o.line_start, old_line_end=o.line_end,
                                    changed_lines=changed_lines_in(hunks, _range(o), None)))
    for n in added.values():
        changes.append(EntityChange(path=path, previous_path=prev, kind=n.kind, name=n.key,
                                    change=EntityChangeType.added, new_signature=n.signature,
                                    details=["added"], added_parameters=list(n.params),
                                    line_start=n.line_start, line_end=n.line_end,
                                    changed_lines=changed_lines_in(hunks, None, _range(n))))

    for key, n in after.items():
        o = before.get(key)
        if o is None:
            continue
        lines = changed_lines_in(hunks, _range(o), _range(n))
        common = dict(path=path, previous_path=prev, kind=n.kind, name=key,
                      old_signature=o.signature, new_signature=n.signature,
                      line_start=n.line_start, line_end=n.line_end,
                      old_line_start=o.line_start, old_line_end=o.line_end, changed_lines=lines)
        if o.source is not None and n.source is not None:
            old_code, new_code = o.source, n.source
        else:                                # LD-154: only the diff lines of the entity
            old_code, new_code = _diff_texts(hunks, _range(o), _range(n))
        if o.contract != n.contract:
            # the body may change too: those signals give a second, semantic finding (LD-151)
            info = signature_change(o, n)
            signals = without_renames(extract_signals(old_code, new_code, o.docstring, n.docstring, lang),
                                      _renames(info["parameter_changes"], info["removed_parameters"],
                                               info["added_parameters"]),
                                      info["removed_parameters"] + info["added_parameters"])
            changes.append(EntityChange(change=EntityChangeType.signature_changed, signals=signals,
                                        **info, **common))
            continue
        details = []
        if o.docstring != n.docstring:
            details.append("docstring changed")
        if o.body is not None and n.body is not None and o.body != n.body:
            details.append("body changed")
        elif o.body is None or n.body is None:
            # no source from the analyzer: rely on the diff lines inside the entity
            own = lines
            if n.kind == "class":  # lines of its methods are reported on the methods
                own = 0 if any(k.startswith(key + ".") for k in after) else lines
            if own and code_key(old_code, lang) == code_key(new_code, lang):
                own = 0            # LD-347: only comments / whitespace changed
            if own and n.kind != "endpoint":
                details.append(f"{own} changed line(s) in the body")
        if details:
            docs = {}
            if o.docstring != n.docstring:   # shown as evidence (LD-149) when there is no diff
                docs = dict(old_docstring=o.docstring, new_docstring=n.docstring)
            signals = extract_signals(old_code, new_code, o.docstring, n.docstring, lang)
            changes.append(EntityChange(change=EntityChangeType.behavior_changed, details=details,
                                        signals=signals, **docs, **common))
    return _without_handler_duplicates(changes, after)


# ---------- patch-only mode ----------

PY_DEF = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\((.*?)(\)\s*(?:->\s*(.+?))?\s*:)?\s*(#.*)?$")
PY_CLASS = re.compile(r"^(\s*)class\s+(\w+)\s*(?:\((.*?)\))?\s*:")
PY_ROUTE = re.compile(r"^\s*@\w+(?:\.\w+)*\.(get|post|put|patch|delete|head|options|route)"
                      r"\(\s*[rbuf]?['\"]([^'\"]+)['\"](.*)$", re.I)
JAVA_TYPE = re.compile(r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*"
                       r"(?:(?:public|protected|private|abstract|final|static|sealed|non-sealed)\s+)*"
                       r"(class|interface|enum|record)\s+(\w+)")
JAVA_METHOD = re.compile(r"^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|default"
                         r"|native)\s+)*(?:<[^>]+>\s+)?([\w.$<>\[\], ?]+?\s+)?(\w+)\s*\(([^)]*)\)?"
                         r"\s*(?:throws\s+[\w., ]+)?\s*[{;]?\s*$")
JAVA_ROUTE = re.compile(r"^\s*@(Get|Post|Put|Patch|Delete|Request)Mapping\s*(?:\((.*)\))?")
JAVA_NOT_METHODS = {"if", "for", "while", "switch", "catch", "return", "new", "else", "do", "try",
                    "synchronized", "throw", "super", "this"}


def language_of(path: str) -> Optional[str]:
    p = path.lower()
    if p.endswith(".py"):
        return "python"
    if p.endswith(".java"):
        return "java"
    return None


def _split_params(text: str) -> List[str]:
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _java_param_name(p: str) -> str:
    p = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", p).replace("final ", "").strip()
    return p.split()[-1] if p.split() else p


@dataclass
class Decl:
    kind: str                # class | function | method | endpoint
    key: str
    signature: str
    params: List[str]
    contract: str
    line: int
    param_info: List[Tuple] = field(default_factory=list)   # LD-153


def _java_route(m: re.Match, rest: str) -> Tuple[str, str]:
    verb = m.group(1).upper()
    args = m.group(2) or ""
    path_m = re.search(r"\"([^\"]*)\"", args)
    if verb == "REQUEST":
        mm = re.search(r"RequestMethod\.(\w+)", args)
        verb = mm.group(1).upper() if mm else "GET"
    return verb, (path_m.group(1) if path_m else "/")


def _python_route(m: re.Match) -> Tuple[str, str]:
    verb = m.group(1).upper()
    if verb == "ROUTE":
        mm = re.search(r"methods\s*=\s*\[\s*['\"](\w+)", m.group(3) or "")
        verb = mm.group(1).upper() if mm else "GET"
    return verb, m.group(2)


def _decl(line: str, lang: str, cls: Optional[str], lineno: int) -> Optional[Decl]:
    text = line[1:]
    if lang == "python":
        m = PY_CLASS.match(text)
        if m:
            sig = f"class {m.group(2)}" + (f"({m.group(3)})" if m.group(3) else "")
            return Decl("class", m.group(2), sig, [], _norm(m.group(3)), lineno)
        m = PY_DEF.match(text)
        if m:
            raw = _split_params(m.group(3))
            params = [p for p in raw if p.split(":")[0].strip() not in ("self", "cls", "*", "/")]
            names = _param_names(params)
            ret = _norm(m.group(5))
            nested = bool(m.group(1)) and cls
            key = f"{cls}.{m.group(2)}" if nested else m.group(2)
            sig = f"{m.group(2)}({', '.join(params)})" + (f" -> {ret}" if ret else "")
            return Decl("method" if nested else "function", key, sig, names,
                        _norm(", ".join(params)) + "|" + ret, lineno,
                        [parse_python_param(p) for p in params])
        m = PY_ROUTE.match(text)
        if m:
            verb, path = _python_route(m)
            return Decl("endpoint", f"{verb} {path}", f"{verb} {path}", [], "", lineno)
        return None
    m = JAVA_TYPE.match(text)
    if m:
        return Decl("class", m.group(2), f"{m.group(1)} {m.group(2)}", [], m.group(1), lineno)
    m = JAVA_ROUTE.match(text)
    if m:
        verb, path = _java_route(m, text)
        return Decl("endpoint", f"{verb} {path}", f"{verb} {path}", [], "", lineno)
    m = JAVA_METHOD.match(text)
    stripped = text.strip()
    if m and m.group(2) not in JAVA_NOT_METHODS and not stripped.startswith(("return ", "new ", "@")) \
            and (m.group(1) or re.match(r"^\s*(public|protected|private)\s", text)) \
            and (m.group(1) or "").strip() not in JAVA_NOT_METHODS and "=" not in stripped.split("(")[0]:
        params = _split_params(m.group(3))
        names = [_java_param_name(p) for p in params]
        ret = _norm(m.group(1))
        key = f"{cls}.{m.group(2)}" if cls else m.group(2)
        sig = f"{ret + ' ' if ret else ''}{m.group(2)}({', '.join(params)})"
        return Decl("method" if cls else "function", key, sig, names,
                    _norm(", ".join(params)) + "|" + ret, lineno,
                    [parse_java_param(p) for p in params])
    return None


def _enclosing(header: str, lang: str) -> Tuple[Optional[str], Optional[str]]:
    """(class, function) named in a hunk header such as 'def total(self):' or 'class Cart:'."""
    if not header:
        return None, None
    d = _decl("+" + header, lang, None, 0)
    if d is None:
        return None, None
    if d.kind == "class":
        return d.key, None
    if d.kind in ("function", "method"):
        return None, d.key.split(".")[-1]
    return None, None


def _is_code(line: str, lang: str) -> bool:
    s = line[1:].strip()
    if not s:
        return False
    if lang == "python":
        return not s.startswith("#")
    return not s.startswith(("//", "*", "/*", "import ", "package "))


def scan_patch(path: str, prev: Optional[str], hunks: List[DiffHunk], lang: str) -> List[EntityChange]:
    old: Dict[str, Decl] = {}
    new: Dict[str, Decl] = {}
    body: Dict[str, Tuple[str, int, int, int]] = {}  # key -> (kind, line, changed lines, old line)
    body_lines: Dict[str, Dict[str, List[str]]] = {}  # key -> {"-": [...], "+": [...]} (LD-154)

    for h in hunks:
        cls, func = _enclosing(h.header, lang)
        func_kind = "function"
        func_key = func
        if func and lang == "java":
            func_kind, func_key = "method", (f"{cls}.{func}" if cls else func)
        pending_route: Dict[str, Optional[Decl]] = {"+": None, "-": None, " ": None}
        for o, n, line in numbered(h):
            tag = line[:1]
            d = _decl(line, lang, cls, (n if tag != "-" else o) or 0)
            if d is not None and d.kind == "class":
                cls = d.key
            if d is not None and d.kind in ("function", "method"):
                func_key, func_kind = d.key, d.kind
                if lang == "python" and not line[1:2].isspace():
                    cls = None if d.kind == "function" else cls
            if d is not None and tag in "+-":
                (new if tag == "+" else old)[d.key] = d
                if d.kind == "endpoint":
                    pending_route[tag] = d
                continue
            if tag in "+-" and func_key and _is_code(line, lang):
                k, ln, cnt, ol = body.get(func_key, (func_kind, n or o or 0, 0, o or 0))
                body[func_key] = (k, ln, cnt + 1, ol)
                body_lines.setdefault(func_key, {"-": [], "+": []})[tag].append(line[1:])

    changes: List[EntityChange] = []
    common = dict(path=path, previous_path=prev, source="patch")
    only_old = {k: d for k, d in old.items() if k not in new}
    only_new = {k: d for k, d in new.items() if k not in old}
    for k in list(only_old):    # LD-153: same path, other HTTP method
        d = only_old[k]
        if d.kind != "endpoint":
            continue
        verb = d.key.split(" ", 1)[0]
        twin = [x for x in only_new.values() if x.kind == "endpoint"
                and _path_key(x.key) == _path_key(d.key) and x.key.split(" ", 1)[0] != verb]
        if len(twin) == 1:
            t = twin[0]
            changes.append(EntityChange(kind="endpoint", name=t.key, old_name=d.key,
                                        change=EntityChangeType.signature_changed,
                                        old_signature=d.signature, new_signature=t.signature,
                                        details=[f"HTTP method: {verb} -> {t.key.split(' ', 1)[0]}"],
                                        aspects=["http_method"], breaking=True,
                                        line_start=t.line, old_line_start=d.line, **common))
            only_old.pop(k)
            only_new.pop(t.key)
    for k in list(only_old):
        d = only_old[k]
        if d.kind == "endpoint":  # same HTTP method, other path: the route was moved
            verb = d.key.split(" ", 1)[0]
            twin = [x for x in only_new.values() if x.kind == "endpoint" and x.key.split(" ", 1)[0] == verb]
            if len([x for x in only_old.values() if x.kind == "endpoint"
                    and x.key.split(" ", 1)[0] == verb]) != 1:
                twin = []
        else:
            twin = [x for x in only_new.values()
                    if x.kind == d.kind and x.contract == d.contract
                    and (d.contract.strip("|") or d.kind == "class")]
        if len(twin) == 1:
            t = twin[0]
            changes.append(EntityChange(kind=d.kind, name=t.key, change=EntityChangeType.renamed,
                                        old_name=d.key, old_signature=d.signature,
                                        new_signature=t.signature, details=[f"renamed: {d.key} -> {t.key}"],
                                        line_start=t.line, old_line_start=d.line, **common))
            only_old.pop(k)
            only_new.pop(t.key)
    for d in only_old.values():
        changes.append(EntityChange(kind=d.kind, name=d.key, change=EntityChangeType.removed,
                                    old_signature=d.signature, details=["removed"],
                                    removed_parameters=d.params, old_line_start=d.line, **common))
    for d in only_new.values():
        changes.append(EntityChange(kind=d.kind, name=d.key, change=EntityChangeType.added,
                                    new_signature=d.signature, details=["added"],
                                    added_parameters=d.params, line_start=d.line, **common))
    for k, d in new.items():
        o = old.get(k)
        if o is None:
            continue
        if o.contract != d.contract:
            removed = [p for p in o.params if p not in d.params]
            added = [p for p in d.params if p not in o.params]
            details = []
            if removed:
                details.append("removed parameter(s): " + ", ".join(removed))
            if added:
                details.append("added parameter(s): " + ", ".join(added))
            params = parameter_changes(o.param_info, d.param_info)
            aspects = []
            if d.kind == "class":
                aspects.append("kind" if lang == "java" else "bases")
            else:
                if o.contract.split("|")[0] != d.contract.split("|")[0]:
                    aspects.append("parameters")
                if o.contract.split("|")[-1] != d.contract.split("|")[-1]:
                    aspects.append("return_type")
                    details.append(f"return type: {o.contract.split('|')[-1] or '-'} -> "
                                   f"{d.contract.split('|')[-1] or '-'}")
            for c in params:
                if c.change.value == "type_changed":
                    details.append(f"parameter {c.name}: type {c.old_type} -> {c.new_type}")
                elif c.change.value.startswith("default"):
                    details.append(f"parameter {c.name}: default {c.old_default or '-'} -> "
                                   f"{c.new_default or '-'}")
            if not details:
                details.append(f"signature: {o.signature} -> {d.signature}")
            ret = "return_type" in aspects
            texts = body_lines.get(k, {"-": [], "+": []})
            signals = without_renames(extract_signals("\n".join(texts["-"]), "\n".join(texts["+"]), lang=lang),
                                      _renames(params, removed, added), removed + added)
            changes.append(EntityChange(kind=d.kind, name=k, change=EntityChangeType.signature_changed,
                                        signals=signals,
                                        old_signature=o.signature, new_signature=d.signature,
                                        details=details, removed_parameters=removed,
                                        added_parameters=added, line_start=d.line,
                                        old_line_start=o.line, aspects=aspects,
                                        parameter_changes=params,
                                        old_return_type=(o.contract.split("|")[-1] or None) if ret else None,
                                        new_return_type=(d.contract.split("|")[-1] or None) if ret else None,
                                        breaking=assess(d.kind, aspects, params), **common))
        elif k not in body:
            body[k] = (d.kind, d.line, 1, o.line)
    reported = {c.name for c in changes} | {c.old_name for c in changes if c.old_name}
    for k, (kind, ln, cnt, ol) in body.items():
        if k in reported or kind in ("class", "endpoint"):
            continue
        texts = body_lines.get(k, {"-": [], "+": []})
        if sorted(filter(None, (line_key(x, lang) for x in texts["-"]))) == \
                sorted(filter(None, (line_key(x, lang) for x in texts["+"]))):
            continue               # LD-347: only comments / whitespace / formatting changed
        changes.append(EntityChange(kind=kind, name=k, change=EntityChangeType.behavior_changed,
                                    details=[f"{cnt} changed line(s) in the body"],
                                    line_start=ln or None, old_line_start=ol or None,
                                    changed_lines=cnt,
                                    signals=extract_signals("\n".join(texts["-"]), "\n".join(texts["+"]), lang=lang),
                                    **common))
    return changes


# ---------- whole Pull Request ----------

def _usable(f: Optional[FileAnalysis]) -> bool:
    return f is not None and f.status == AnalysisStatus.ok


def analyze_file(cf: ChangedFile) -> FileChangeSummary:
    hunks = parse_patch(cf.patch)
    adds, dels = count_changes(hunks)
    prev = cf.previous_path if cf.previous_path and cf.previous_path != cf.path else None
    lang = (cf.after.language if cf.after else None) or (cf.before.language if cf.before else None) \
        or language_of(cf.path)
    summary = FileChangeSummary(path=cf.path, status=cf.status, previous_path=prev,
                                language=(lang or None), additions=adds, deletions=dels, hunks=hunks)
    status = cf.status
    if status in (ChangeStatus.unchanged, ChangeStatus.changed) and not hunks:
        return summary

    # which analyses are expected: a removed file has no `after`, an added one no `before`
    need_before = status not in (ChangeStatus.added,)
    need_after = status not in (ChangeStatus.removed,)
    has_before, has_after = _usable(cf.before), _usable(cf.after)
    for side, f in (("before", cf.before), ("after", cf.after)):
        if f is not None and f.status != AnalysisStatus.ok:
            summary.warnings.append(f"{cf.path}: '{side}' analysis is {f.status.value}"
                                    + (f" ({f.error})" if f.error else "") + "; it was not used.")
    if (has_before or not need_before) and (has_after or not need_after) and (has_before or has_after):
        summary.method = "analysis"
        summary.entity_changes = compare_analyses(cf, hunks)
    elif hunks and (lang or "").lower() in ("python", "java"):
        summary.method = "patch"
        summary.entity_changes = scan_patch(cf.path, prev, hunks, lang.lower())
        if cf.before is not None or cf.after is not None:
            summary.warnings.append(f"{cf.path}: analysis for the base or head commit is missing; "
                                    "entity changes were read from the diff only.")
    elif hunks or status in (ChangeStatus.removed, ChangeStatus.renamed):
        summary.method = "none"
        if (lang or "").lower() not in ("python", "java") and status == ChangeStatus.modified:
            summary.warnings.append(f"{cf.path}: language not analysed; only file-level changes are checked.")
        elif status not in (ChangeStatus.removed, ChangeStatus.renamed):
            summary.warnings.append(f"{cf.path}: no diff and no analysis; "
                                    "only file-level changes are checked.")
    return summary


def analyze_pull_request(pr: PullRequestInfo, files: List[ChangedFile],
                         repository: Optional[str] = None) -> PullRequestAnalysis:
    summaries = [analyze_file(cf) for cf in files]
    return PullRequestAnalysis(repository=repository, pull_request=pr, tickets=find_tickets(pr),
                               files=summaries,
                               additions=sum(s.additions for s in summaries),
                               deletions=sum(s.deletions for s in summaries),
                               entity_changes=sum(len(s.entity_changes) for s in summaries))
