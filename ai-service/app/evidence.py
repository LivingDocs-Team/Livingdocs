"""Evidence catalog for one file (LD-340).

Every documented entity gets an id pointing at its own code (E1, E2, ...). Related
code and documentation passages found by retrieval keep their ids (C1.., D1..).
The AI must cite these ids for each description; the ids it cites are checked
against this catalog, so a citation always resolves to a real location.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import ClassInfo, Endpoint, Evidence, EvidenceKind, FileAnalysis, Function
from .retrieval import Retrieved

EXCERPT_CHARS = 300


@dataclass
class Entity:
    kind: str          # class | method | function | endpoint
    key: str           # Class | Class.method | function | "GET /path"
    obj: object        # ClassInfo | Function | Endpoint


def entities(f: FileAnalysis) -> List[Entity]:
    out: List[Entity] = []
    for c in f.classes:
        out.append(Entity("class", c.name, c))
        out += [Entity("method", f"{c.name}.{m.name}", m) for m in c.methods]
    out += [Entity("function", fn.name, fn) for fn in f.functions]
    out += [Entity("endpoint", f"{e.http_method} {e.path}", e) for e in f.endpoints]
    return out


def _handler(f: FileAnalysis, ep: Endpoint) -> Optional[Function]:
    """The function or method in the same file that serves an endpoint (LD-355)."""
    if not ep.handler:
        return None
    name = ep.handler.split(".")[-1].split("::")[-1].strip()
    owner = ep.handler.rsplit(".", 1)[0] if "." in ep.handler else None
    for fn in f.functions:
        if fn.name == name:
            return fn
    for c in f.classes:
        if owner and c.name != owner.split(".")[-1]:
            continue
        for m in c.methods:
            if m.name == name:
                return m
    return None


def _lines(f: FileAnalysis, obj) -> Tuple[Optional[int], Optional[int]]:
    start, end = getattr(obj, "line_start", None), getattr(obj, "line_end", None)
    if start is None and isinstance(obj, Endpoint):
        # analyzers often give no lines for a route: point at its handler instead
        fn = _handler(f, obj)
        if fn is not None:
            start, end = fn.line_start, fn.line_end
    return start, end


def _excerpt(obj, f: Optional[FileAnalysis] = None) -> Optional[str]:
    if isinstance(obj, Function):
        text = obj.source or obj.signature or obj.name
    elif isinstance(obj, ClassInfo):
        text = f"{obj.kind or 'class'} {obj.name}" + (f"({', '.join(obj.bases)})" if obj.bases else "")
        if obj.fields:
            text += "\n" + ", ".join(f"{x.name}: {x.type}" if x.type else x.name for x in obj.fields)
        if obj.docstring:
            text += "\n" + obj.docstring.strip()
    elif isinstance(obj, Endpoint):
        text = f"{obj.http_method} {obj.path}" + (f" -> {obj.handler}" if obj.handler else "")
        fn = _handler(f, obj) if f is not None else None
        if fn is not None and (fn.source or fn.signature):
            text += "\n" + (fn.source or fn.signature)
    else:
        return None
    return text[:EXCERPT_CHARS]


@dataclass
class EvidenceCatalog:
    by_id: Dict[str, Evidence] = field(default_factory=dict)
    own: Dict[str, Evidence] = field(default_factory=dict)          # entity key -> its E id
    own_ids: Dict[str, List[str]] = field(default_factory=dict)     # key -> all E ids (overloads)
    retrieved: List[Evidence] = field(default_factory=list)          # C.. and D..

    def resolve(self, ids: List[str]) -> Tuple[List[Evidence], List[str]]:
        """Split cited ids into known evidence and unknown ids (dedup, keep order)."""
        found, unknown, seen = [], [], set()
        for raw in ids or []:
            i = str(raw).strip().upper()
            if not i or i in seen:
                continue
            seen.add(i)
            (found.append(self.by_id[i]) if i in self.by_id else unknown.append(str(raw)))
        return found, unknown


def build_catalog(f: FileAnalysis, retrieved: Optional[Retrieved] = None) -> EvidenceCatalog:
    cat = EvidenceCatalog()
    for n, ent in enumerate(entities(f), start=1):
        start, end = _lines(f, ent.obj)
        ev = Evidence(id=f"E{n}", kind=EvidenceKind.source, path=f.path, name=ent.key,
                      line_start=start, line_end=end, excerpt=_excerpt(ent.obj, f))
        cat.by_id[ev.id] = ev
        cat.own.setdefault(ent.key, ev)     # overloads share a key: the first one is shown
        cat.own_ids.setdefault(ent.key, []).append(ev.id)
    if retrieved:
        for ch in retrieved.code + retrieved.docs:
            ev = Evidence(id=ch.ref, kind=EvidenceKind.code if ch.kind == "code" else EvidenceKind.doc,
                          path=ch.path, name=ch.name, line_start=ch.line_start,
                          line_end=ch.line_end, excerpt=ch.excerpt[:EXCERPT_CHARS])
            cat.by_id[ev.id] = ev
            cat.retrieved.append(ev)
    return cat


def location(ev: Evidence) -> str:
    """'src/a.py:12-20' style location for display."""
    if ev.line_start and ev.line_end and ev.line_end != ev.line_start:
        return f"{ev.path}:{ev.line_start}-{ev.line_end}"
    if ev.line_start:
        return f"{ev.path}:{ev.line_start}"
    return ev.path
