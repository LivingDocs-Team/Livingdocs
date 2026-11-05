"""Clean up analyzer output before documentation is generated.

1. Unique entity names. Descriptions, evidence and confidence are matched by name
   (`Class.method`), so two entities with the same name used to share one evidence id and
   one description. Java overloads become `get(Long)` / `get(String)`; any remaining
   duplicate (Python redefinition, two inner classes with the same name) gets `#2`, `#3`.
2. Module name. The analyzer does not send `module` yet; derive it from the path
   (`app/services/cart.py` -> `app.services.cart`, Java -> package folder).
"""
import posixpath
from typing import Dict, List, Optional, Sequence

from .models import AnalysisStatus, FileAnalysis, Function

_JAVA_ROOTS = ("src/main/java/", "src/test/java/", "src/")
_PY_ROOTS = ("src/",)


def module_from_path(path: str, language: Optional[str]) -> Optional[str]:
    p = path.replace("\\", "/").lstrip("./")
    stem, ext = posixpath.splitext(p)
    lang = (language or "").lower()
    if lang == "java" or ext == ".java":
        for root in _JAVA_ROOTS:
            i = p.find(root)
            if i >= 0:
                p = p[i + len(root):]
                break
        pkg = posixpath.dirname(p)
        return pkg.replace("/", ".") or None
    if lang == "python" or ext == ".py":
        for root in _PY_ROOTS:
            if stem.startswith(root):
                stem = stem[len(root):]
        parts = [x for x in stem.split("/") if x]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) or None
    return None


def _overload_name(fn: Function) -> str:
    types = ", ".join(p.type or p.name for p in fn.parameters)
    return f"{fn.name}({types})"


def _dedupe(names: Sequence[str]) -> List[str]:
    """Append #2, #3 to repeated names, keeping the first occurrence unchanged."""
    seen: Dict[str, int] = {}
    out = []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n}#{seen[n]}")
    return out


def _unique_functions(fns: List[Function]) -> None:
    counts: Dict[str, int] = {}
    for fn in fns:
        counts[fn.name] = counts.get(fn.name, 0) + 1
    names = [_overload_name(fn) if counts[fn.name] > 1 and fn.parameters is not None else fn.name
             for fn in fns]
    for fn, name in zip(fns, _dedupe(names)):
        fn.name = name


def normalize(f: FileAnalysis) -> FileAnalysis:
    if f.status != AnalysisStatus.ok:
        return f
    if not f.module:
        f.module = module_from_path(f.path, f.language)
    for c, name in zip(f.classes, _dedupe([c.name for c in f.classes])):
        c.name = name
        _unique_functions(c.methods)
    # top-level functions: Python has no overloads, a repeated name is a redefinition
    for fn, name in zip(f.functions, _dedupe([fn.name for fn in f.functions])):
        fn.name = name
    return f
