"""LD-153 Implement signature drift detection.

The documentation describes how to *call* the code: parameters, their types and defaults, the
return type, the fields of a class, the HTTP method and contract of an endpoint. A signature
drift is a change of that contract while the documented name stays the same.

1. Structured comparison (`parameter_changes`, `assess`) - used by LD-146 when entity changes
   are built - turns "signature changed" into exact parameter changes and decides whether the
   change is *breaking* (documented usage no longer works):

       removed parameter / field                    breaking
       renamed (same position and type)             breaking
       added, required (no default)                 breaking
       added, optional (has a default, *args)       not breaking
       type changed                                 breaking
       default removed (optional -> required)       breaking
       default added (required -> optional)        not breaking
       default changed                              not breaking
       order of the remaining parameters changed    breaking
       return type changed                          breaking
       HTTP method / request body / response        breaking
       class kind or bases changed                  breaking

2. Classification (`classify`): the finding's `kind` is the most important change, in the order
   of DRIFT_KINDS["signature"]. The documentation is then checked for what it still says
   (within PARAM_WINDOW lines after a mention of the entity):

       a removed / renamed parameter name          (in code)
       a parameter with its old type               (same line, e.g. a table row `| discount | float |`)
       a parameter with its old default            (same line)

Severity (rules in app/drift_severity.py, LD-157): base `breaking_signature` (Medium) or
`compatible_signature` (Low); +1 `public_endpoint`; +1 `doc_states_old_detail` when the documentation
still shows a stale parameter, type or default; -1 `private_name`.
"""
import re
from typing import List, Optional, Sequence, Tuple

from .drift_models import DRIFT_KINDS, DocMatch, ParameterChange, ParameterChangeKind

Param = Tuple[str, Optional[str], Optional[str]]    # name, type, default

KIND_ORDER = DRIFT_KINDS["signature"]


# ---------- 1. structured comparison ----------

def _norm(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _variadic(name: str) -> bool:
    return name.startswith("*") or name.endswith("...")


def _clean(name: str) -> str:
    return name.lstrip("*").rstrip(".")


def parameter_changes(old: Sequence[Param], new: Sequence[Param]) -> List[ParameterChange]:
    """Exact changes between two parameter (or field) lists."""
    old = [(_clean(n), _norm(t), _norm(d), _variadic(n)) for n, t, d in old if n and _clean(n)]
    new = [(_clean(n), _norm(t), _norm(d), _variadic(n)) for n, t, d in new if n and _clean(n)]
    old_names, new_names = [p[0] for p in old], [p[0] for p in new]
    removed = [p for p in old if p[0] not in new_names]
    added = [p for p in new if p[0] not in old_names]
    out: List[ParameterChange] = []

    # renamed: a removed and an added parameter at the same position with the same known type
    for o in list(removed):
        i = old.index(o)
        twin = [a for a in added if new.index(a) == i and o[1] is not None and a[1] == o[1]]
        if len(twin) == 1:
            a = twin[0]
            out.append(ParameterChange(name=a[0], old_name=o[0], change=ParameterChangeKind.renamed,
                                       old_type=o[1], new_type=a[1], old_default=o[2],
                                       new_default=a[2], breaking=True))
            removed.remove(o)
            added.remove(a)
    for o in removed:
        out.append(ParameterChange(name=o[0], change=ParameterChangeKind.removed, old_type=o[1],
                                   old_default=o[2], breaking=True))
    for a in added:
        optional = a[2] is not None or a[3]
        out.append(ParameterChange(name=a[0], change=ParameterChangeKind.added, new_type=a[1],
                                   new_default=a[2], breaking=not optional))

    by_new = {p[0]: p for p in new}
    for o in old:
        n = by_new.get(o[0])
        if n is None:
            continue
        if o[1] and n[1] and o[1] != n[1]:
            out.append(ParameterChange(name=o[0], change=ParameterChangeKind.type_changed,
                                       old_type=o[1], new_type=n[1], breaking=True))
        if o[2] is not None and n[2] is None and not n[3]:
            out.append(ParameterChange(name=o[0], change=ParameterChangeKind.default_removed,
                                       old_default=o[2], breaking=True))
        elif o[2] is None and n[2] is not None:
            out.append(ParameterChange(name=o[0], change=ParameterChangeKind.default_added,
                                       new_default=n[2]))
        elif o[2] is not None and n[2] is not None and o[2] != n[2]:
            out.append(ParameterChange(name=o[0], change=ParameterChangeKind.default_changed,
                                       old_default=o[2], new_default=n[2]))

    kept_old = [p[0] for p in old if p[0] in by_new]
    kept_new = [p[0] for p in new if p[0] in kept_old]
    if kept_old != kept_new:
        out.append(ParameterChange(name=", ".join(kept_new), change=ParameterChangeKind.reordered,
                                   breaking=True))
    return out


def parse_python_param(text: str) -> Param:
    """'quantity: int = 1' -> ('quantity', 'int', '1');  '*args' -> ('*args', None, None)."""
    name, _, default = text.partition("=")
    name, _, type_ = name.partition(":")
    return name.strip(), (type_.strip() or None), (default.strip() if _ else None)


def parse_java_param(text: str) -> Param:
    """'@PathVariable Long id' -> ('id', 'Long', None);  'String... tags' -> ('tags...', ...)."""
    t = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", text).replace("final ", "").strip()
    parts = t.rsplit(None, 1)
    if len(parts) != 2:
        return t, None, None
    type_, name = parts
    if type_.endswith("..."):
        return name + "...", type_[:-3], None
    return name, type_, None


def assess(kind: str, aspects: Sequence[str], changes: Sequence[ParameterChange]) -> bool:
    """Is a signature change breaking for documented usage?"""
    if any(c.breaking for c in changes):
        return True
    contract = {"return_type", "http_method", "request_body", "response", "kind", "bases"}
    if contract & set(aspects):
        return True
    # a contract change we could not read in detail (e.g. only the signature text differs)
    return not changes and "parameters" in aspects


# ---------- 2. classification ----------

def finding_kind(entity_kind: str, aspects: Sequence[str], changes: Sequence[ParameterChange]) -> str:
    if entity_kind == "class":   # fields, kind and bases: the class is used, not called
        return "class_contract_changed"
    kinds = set()
    if "http_method" in aspects:
        kinds.add("endpoint_method_changed")
    for c in changes:
        kinds.add({
            ParameterChangeKind.removed: "parameter_removed",
            ParameterChangeKind.renamed: "parameter_renamed",
            ParameterChangeKind.type_changed: "parameter_type_changed",
            ParameterChangeKind.reordered: "parameter_order_changed",
            ParameterChangeKind.default_removed: "parameter_default_changed",
            ParameterChangeKind.default_added: "parameter_default_changed",
            ParameterChangeKind.default_changed: "parameter_default_changed",
            ParameterChangeKind.added: "parameter_added",
        }[c.change])
    if "return_type" in aspects:
        kinds.add("return_type_changed")
    if {"request_body", "response"} & set(aspects):
        kinds.add("endpoint_contract_changed")
    for k in KIND_ORDER:
        if k in kinds:
            return k
    return "signature_changed"


def stale_details(doc, near: List[DocMatch], changes: Sequence[ParameterChange],
                  window: int) -> List[DocMatch]:
    """What the documentation still shows after the entity is mentioned: removed / renamed
    parameter names, parameters with their old type or default (on the same line)."""
    out: List[DocMatch] = []
    lines = doc.lines
    starts = sorted({m.line - 1 for m in near})

    def scan(name: str, extra: Optional[str], kind: str, note: str) -> None:
        pat = re.compile(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])")
        xpat = re.compile(r"(?<![\w$.])" + re.escape(extra) + r"(?![\w$])") if extra else None
        for start in starts:
            for i in range(start, min(len(lines), start + window)):
                m = pat.search(lines[i])
                if not m or not doc.in_code(i, m.start()):
                    continue
                if xpat is not None and not xpat.search(lines[i][m.end():]):
                    continue
                out.append(DocMatch(term=name if extra is None else f"{name} {extra}", target=name,
                                    line=i + 1, excerpt=lines[i].strip()[:200], in_code=True,
                                    kind=kind, note=note))
                return

    for c in changes:
        if c.change in (ParameterChangeKind.removed, ParameterChangeKind.renamed):
            old = c.old_name or c.name
            scan(old, None, "parameter",
                 f"`{old}` was renamed to `{c.name}`" if c.old_name else f"`{old}` was removed")
        elif c.change == ParameterChangeKind.type_changed and c.old_type:
            scan(c.name, c.old_type, "type", f"type is now `{c.new_type}`")
        elif c.change in (ParameterChangeKind.default_changed, ParameterChangeKind.default_removed) \
                and c.old_default:
            scan(c.name, c.old_default, "default",
                 f"default is now `{c.new_default}`" if c.new_default else "no default any more")
    return sorted({(m.line, m.term): m for m in out}.values(), key=lambda m: m.line)


def describe(c: ParameterChange) -> str:
    if c.change == ParameterChangeKind.renamed:
        return f"`{c.old_name}` renamed to `{c.name}`"
    if c.change == ParameterChangeKind.removed:
        return f"`{c.name}` removed"
    if c.change == ParameterChangeKind.added:
        return f"`{c.name}` added ({'optional' if not c.breaking else 'required'})"
    if c.change == ParameterChangeKind.type_changed:
        return f"`{c.name}` type `{c.old_type}` -> `{c.new_type}`"
    if c.change == ParameterChangeKind.default_removed:
        return f"`{c.name}` is now required (default `{c.old_default}` removed)"
    if c.change == ParameterChangeKind.default_added:
        return f"`{c.name}` is now optional (default `{c.new_default}`)"
    if c.change == ParameterChangeKind.default_changed:
        return f"`{c.name}` default `{c.old_default}` -> `{c.new_default}`"
    return f"order is now {c.name}"


def classify(hit):
    """LD-153: a hit on an entity whose signature changed (EntityChangeType.signature_changed)."""
    from .drift_models import DriftType
    from .drift_rules import PARAM_WINDOW, Classified, code, private

    c = hit.target.change
    endpoint = c.kind == "endpoint"
    breaking = True if c.breaking is None else c.breaking
    kind = finding_kind(c.kind, c.aspects, c.parameter_changes)
    seen = {(m.line, m.term) for m in hit.param_matches}
    details = [m for m in stale_details(hit.doc, hit.matches, c.parameter_changes, PARAM_WINDOW)
               if (m.line, m.term) not in seen]
    stale = hit.param_matches + details

    adjust = []
    if endpoint:
        adjust.append(("public_endpoint", []))
    if stale:
        adjust.append(("doc_states_old_detail", stale))
    if private(c.name):
        adjust.append(("private_name", []))

    renamed = "; ".join(describe(p) for p in c.parameter_changes if p.change == ParameterChangeKind.renamed)
    named = f" Parameter {renamed}." if renamed else ""
    if hit.param_matches:
        named += " It still names removed parameter(s) " + ", ".join(
            code(m.term) for m in hit.param_matches) + "."
    if details:
        named += " It still shows " + ", ".join(f"{code(m.term)} ({m.note})" for m in details) + "."
    name = c.old_name if "http_method" in c.aspects and c.old_name else c.name
    return Classified(DriftType.signature, kind,
                      "breaking_signature" if breaking else "compatible_signature", "signature_changed",
                      f"Signature of {c.kind} {code(name)} changed ({'; '.join(c.details)})." + named,
                      f"Update the documented signature to {code(c.new_signature)}.",
                      before=c.old_signature, after=c.new_signature, breaking=breaking,
                      adjust=adjust, details=details)
