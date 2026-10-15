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


def _excerpt(obj) -> Optional[str]:
    if isinstance(obj, Function):
        text = obj.source or obj.signature or obj.name
    elif isinstance(obj, ClassInfo):
        text = f"class {obj.name}" + (f"({', '.join(obj.bases)})" if obj.bases else "")
        if obj.docstring:
            text += "\n" + obj.docstring.strip()
    elif isinstance(obj, Endpoint):
        text = f"{obj.http_method} {obj.path}" + (f" -> {obj.handler}" if obj.handler else "")
    else:
        return None
    return text[:EXCERPT_CHARS]


@dataclass
class EvidenceCatalog:
    by_id: Dict[str, Evidence] = field(default_factory=dict)
    own: Dict[str, Evidence] = field(default_factory=dict)          # entity key -> its E id
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
        ev = Evidence(id=f"E{n}", kind=EvidenceKind.source, path=f.path, name=ent.key,
                      line_start=getattr(ent.obj, "line_start", None),
                      line_end=getattr(ent.obj, "line_end", None),
                      excerpt=_excerpt(ent.obj))
        cat.by_id[ev.id] = ev
        cat.own[ent.key] = ev
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
