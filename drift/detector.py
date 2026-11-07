"""Detect documentation drift (LD-147).

Takes the references found by `affected.py` and decides, rule by rule, whether the documentation
still agrees with the code of the pull request. Every finding carries a confidence in 0..1.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .affected import AffectedReference, identify_affected_documentation
from .doc_scanner import DocFile, DocIndex
from .entities import _match, _split_top
from .models import ChangeType, Entity, EntityChange, FileChange, FileStatus, PullRequestAnalysis

HIGH, MEDIUM = 0.8, 0.5

# rule id -> (drift type, short description)
RULES: Dict[str, Tuple[str, str]] = {
    "DRIFT001": ("removed_entity", "Documentation mentions code that was removed"),
    "DRIFT002": ("renamed_entity", "Documentation uses the old name of renamed code"),
    "DRIFT003": ("signature_changed", "Documentation shows an outdated signature or parameter list"),
    "DRIFT004": ("return_type_changed", "Documentation states an outdated return type"),
    "DRIFT005": ("route_changed", "Documentation lists an HTTP route that changed or was removed"),
    "DRIFT006": ("members_changed", "Documentation of a class does not match its attributes"),
    "DRIFT007": ("file_removed", "Documentation references a file that was deleted"),
    "DRIFT008": ("file_renamed", "Documentation references the old path of a renamed file"),
    "DRIFT009": ("undocumented_endpoint", "New endpoint is missing from documentation that lists its siblings"),
    "DRIFT010": ("entity_moved", "Documentation points to the old file of moved code"),
}


@dataclass
class DriftFinding:
    rule_id: str
    confidence: float
    entity: str
    kind: str
    change_type: str
    code_file: str
    doc_path: str
    doc_line: int
    doc_text: str
    section_title: str
    reasons: List[str]
    suggestion: str
    ref: Optional[AffectedReference] = None
    change: Optional[EntityChange] = None
    file_change: Optional[FileChange] = None
    doc_updated_in_pr: bool = False
    section_level: bool = False

    @property
    def drift_type(self) -> str:
        return RULES[self.rule_id][0]

    @property
    def severity(self) -> str:
        return "high" if self.confidence >= HIGH else "medium" if self.confidence >= MEDIUM else "low"

    @property
    def id(self) -> str:
        key = "|".join([self.rule_id, self.doc_path, self.entity, re.sub(r"\s+", " ", self.doc_text).strip()])
        return "DD-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


@dataclass
class _Candidate:
    rule_id: str
    base: float
    reasons: List[str]
    suggestion: str
    strength: Optional[float] = None   # overrides the strength of the reference (exact evidence)
    section: bool = False              # derived from the section around the reference, not the reference itself


def score(base: float, strength: float) -> float:
    return round(min(1.0, base * (max(strength, 0.0) ** 0.7)), 2)


# --------------------------------------------------------------------------- entry point

def detect_drift(index: DocIndex, analysis: PullRequestAnalysis,
                 min_confidence: float = 0.0) -> List[DriftFinding]:
    affected = identify_affected_documentation(index, analysis)
    head_names = {e.name for ents in analysis.head_entities.values() for e in ents}
    findings: List[DriftFinding] = []

    for doc in affected:
        for aref in doc.references:
            doc_file = index.docs[aref.reference.doc_path]
            cands = _evaluate(aref, doc_file, analysis, head_names)
            if not cands:
                continue
            findings.append(_to_finding(aref, cands, doc.updated_in_pr))

    findings += _undocumented_endpoints(index, analysis)
    findings = _dedupe(findings)
    findings = [f for f in findings if f.confidence >= min_confidence]
    findings.sort(key=lambda f: (-f.confidence, f.doc_path, f.doc_line, f.entity))
    return findings


def _to_finding(aref: AffectedReference, cands: List[_Candidate], updated: bool) -> DriftFinding:
    best = max(cands, key=lambda c: c.base)
    reasons: List[str] = []
    for c in cands:
        reasons += [r for r in c.reasons if r not in reasons]
    ref, change = aref.reference, aref.change
    strength = best.strength if best.strength is not None else aref.strength
    return DriftFinding(
        rule_id=best.rule_id, confidence=score(best.base, strength),
        entity=aref.subject, kind=change.kind if change else "file",
        change_type=change.change_type.value if change else (aref.file_change.status.value if aref.file_change else ""),
        code_file=(change.file if change else (aref.file_change.path if aref.file_change else "")),
        doc_path=ref.doc_path, doc_line=ref.line, doc_text=ref.text, section_title=ref.section_title,
        reasons=reasons, suggestion=best.suggestion, ref=aref, change=change,
        file_change=aref.file_change, doc_updated_in_pr=updated,
        section_level=all(c.section for c in cands))


# --------------------------------------------------------------------------- rules per reference

def _evaluate(aref: AffectedReference, doc: DocFile, analysis: PullRequestAnalysis,
              head_names: Set[str]) -> List[_Candidate]:
    if aref.via == "name" and aref.change is not None:
        return _name_rules(aref, doc, head_names)
    if aref.via == "route" and aref.change is not None:
        return _route_rules(aref)
    if aref.via == "path" and aref.file_change is not None:
        return _path_rules(aref)
    return []


def _name_rules(aref: AffectedReference, doc: DocFile, head_names: Set[str]) -> List[_Candidate]:
    change, ref = aref.change, aref.reference
    name = aref.matched_name
    line_text = ref.text

    if change.change_type == ChangeType.REMOVED:
        if change.name in head_names:
            return []  # still defined somewhere else
        return [_Candidate("DRIFT001", 0.95,
                           [f"`{change.name}` ({change.kind}) was removed in `{change.file}` but is still documented."],
                           f"Remove the documentation of `{change.name}` or describe its replacement.")]

    if change.change_type == ChangeType.RENAMED:
        old, new = change.old_name or "", change.new_name or ""
        old_short, new_short = old.rsplit(".", 1)[-1], new.rsplit(".", 1)[-1]
        if name not in (old, old_short) or name in (new, new_short):
            return []
        if re.search(r"(?<![\w$])" + re.escape(new_short) + r"(?![\w$])", line_text):
            return []  # the line mentions the new name too: probably a "renamed from" note
        return [_Candidate("DRIFT002", 0.95,
                           [f"`{old}` was renamed to `{new}` in `{change.file}`."],
                           f"Replace `{old}` with `{new}`.")]

    if change.change_type == ChangeType.MOVED:
        old_file = change.moved_from or ""
        if old_file and old_file in doc.section_text(ref.line):
            return [_Candidate("DRIFT010", 0.75,
                               [f"`{change.name}` moved from `{old_file}` to `{change.file}`."],
                               f"Point the documentation to `{change.file}`.")]
        return []

    if change.change_type == ChangeType.MODIFIED and aref.strength >= 0.55:
        return _modified_rules(aref, doc)
    return []


def _modified_rules(aref: AffectedReference, doc: DocFile) -> List[_Candidate]:
    change, ref = aref.change, aref.reference
    old, new = change.before, change.after
    cands: List[_Candidate] = []
    window = _window(doc, ref)

    # 1. the old signature written out verbatim
    if change.signature_changed or change.bases_changed:
        compatible = _only_optional_params_added(change)
        old_forms = _signature_forms(old, declarations_only=compatible)
        new_forms = _signature_forms(new)
        norm_window = _squash(window)
        hit = next((f for f in old_forms if f and _squash(f) in norm_window), None)
        if hit and not any(_squash(f) in norm_window for f in new_forms if f):
            cands.append(_Candidate("DRIFT003", 0.97,
                                    [f"Documentation still shows the old signature `{hit}`.",
                                     *change.details],
                                    f"Update the signature to `{new.signature}`.", strength=0.95))

    # 2. an argument list written after the name: `add(item)` / `add(self, item)`
    if change.signature_changed and not cands:
        args = _doc_args(doc, ref)
        if args is not None:
            cand = _check_args(change, args)
            if cand:
                cands.append(cand)

    # 3. parameters / attributes listed in the section of the reference
    if ref.kind in ("heading", "code_span", "code_block") and aref.strength >= 0.7:
        for c in _section_rules(change, doc.code_identifiers(ref.line), doc.section_text(ref.line)):
            c.section = True
            cands.append(c)
    return cands


def _field_name(member: str) -> str:
    return member.split(":", 1)[0].strip()


def _section_rules(change: EntityChange, idents: Set[str], section_text: str) -> List[_Candidate]:
    """Checks on what the section around the reference lists: parameters, return type, attributes."""
    cands: List[_Candidate] = []
    old, new = change.before, change.after
    new_names = set(new.param_names)

    gone = [n for n in change.params_removed if len(n) > 2 and n in idents and n not in new_names]
    if gone:
        cands.append(_Candidate("DRIFT003", 0.7,
                                [f"Documentation lists removed parameter(s): {', '.join(gone)}."],
                                f"Remove {', '.join('`' + g + '`' for g in gone)} from the documentation of `{new.name}`."))
    listed = [n for n in old.param_names if n in new_names and len(n) > 2 and n in idents]
    fresh = [n for n in change.params_added if n not in idents]
    if listed and fresh and len(fresh) == len(change.params_added):
        cands.append(_Candidate("DRIFT003", 0.5,
                                [f"New parameter(s) not documented: {', '.join(fresh)}."],
                                f"Document {', '.join('`' + f + '`' for f in fresh)} for `{new.name}`."))

    if change.return_changed and old.return_type and len(old.return_type) > 1:
        pattern = r"(?:->\s*|[Rr]eturns?\s+`?|[Tt]rả về\s+`?)" + re.escape(old.return_type) + r"(?![\w])"
        if re.search(pattern, section_text) and not (
                new.return_type and re.search(r"(?<![\w])" + re.escape(new.return_type) + r"(?![\w])", section_text)):
            cands.append(_Candidate("DRIFT004", 0.65,
                                    [f"Documentation says it returns `{old.return_type}`, "
                                     f"the code now returns `{new.return_type or 'nothing'}`."],
                                    f"Update the return type to `{new.return_type or 'None'}`."))

    if change.kind == "class" and (change.members_removed or change.members_added):
        removed = [_field_name(m) for m in change.members_removed]
        kept = [_field_name(m) for m in old.fields if m not in change.members_removed]
        gone_fields = [n for n in removed if len(n) > 2 and n in idents]
        if gone_fields:
            cands.append(_Candidate("DRIFT006", 0.7,
                                    [f"Documentation lists removed attribute(s): {', '.join(gone_fields)}."],
                                    f"Remove {', '.join('`' + g + '`' for g in gone_fields)} from `{new.name}`."))
        added = [_field_name(m) for m in change.members_added]
        if any(k in idents and len(k) > 2 for k in kept) and added and not any(a in idents for a in added):
            cands.append(_Candidate("DRIFT006", 0.5,
                                    [f"New attribute(s) not documented: {', '.join(added)}."],
                                    f"Document {', '.join('`' + a + '`' for a in added)} for `{new.name}`."))
    return cands


def _check_args(change: EntityChange, args: str) -> Optional[_Candidate]:
    old, new = change.before, change.after
    mode, items = _classify_args(args)
    if mode == "names":
        names = [n for n in items if n not in ("self", "cls")]
        if _consistent(names, new):
            return None
        if _consistent(names, old):
            return _Candidate("DRIFT003", 0.9,
                              [f"Documentation shows parameters ({', '.join(names)}) of the old signature.",
                               *change.details],
                              f"Update the parameters to `{new.signature}`.")
        return _Candidate("DRIFT003", 0.6,
                          [f"Documented arguments ({', '.join(names)}) match neither the old nor the new signature.",
                           *change.details],
                          f"Check the example against `{new.signature}`.")
    n = len(items)
    if _arity_ok(n, new):
        return None
    if _arity_ok(n, old):
        return _Candidate("DRIFT003", 0.8,
                          [f"Example calls it with {n} argument(s), valid only for the old signature.",
                           *change.details],
                          f"Update the example to `{new.signature}`.")
    return _Candidate("DRIFT003", 0.5,
                      [f"Example passes {n} argument(s) but the new signature is `{new.signature}`."],
                      f"Check the example against `{new.signature}`.")


def _consistent(names: Sequence[str], ent: Entity) -> bool:
    all_names = {p.name for p in ent.params}
    required = {p.name for p in ent.params if p.required}
    if any(p.variadic for p in ent.params):
        return required <= set(names)
    return set(names) <= all_names and required <= set(names)


def _arity_ok(n: int, ent: Entity) -> bool:
    required = sum(1 for p in ent.params if p.required)
    maximum = float("inf") if any(p.variadic for p in ent.params) else len(ent.params)
    return required <= n <= maximum


_NAME_ITEM = re.compile(r"^\*{0,2}([A-Za-z_]\w*)\s*(?::[^=]+)?(?:=.*)?$", re.S)
_JAVA_ITEM = re.compile(r"^(?:final\s+)?[A-Za-z_][\w<>\[\],.? ]*?\s+\*?([A-Za-z_]\w*)$", re.S)


def _classify_args(args: str) -> Tuple[str, list]:
    items = _split_top(args)
    names: List[str] = []
    for raw in items:
        m = _NAME_ITEM.match(raw.strip()) or _JAVA_ITEM.match(raw.strip())
        if not m:
            return "values", items
        names.append(m.group(1))
    return "names", names


def _doc_args(doc: DocFile, ref) -> Optional[str]:
    line = doc.lines[ref.line - 1]
    if ref.col_end >= len(line) or line[ref.col_end] != "(":
        return None
    text = line[ref.col_end:]
    extra = 0
    while _match(text, 0, "(", ")") == len(text) - 1 and not text.rstrip().endswith(")") and extra < 6 \
            and ref.line + extra < len(doc.lines):
        extra += 1
        text += "\n" + doc.lines[ref.line - 1 + extra]
    close = _match(text, 0, "(", ")")
    if close <= 0 or text[close] != ")":
        return None
    return text[1:close]


def _window(doc: DocFile, ref) -> str:
    """The referenced line, plus the next lines when inside a code block (multi-line signatures)."""
    if ref.kind == "code_block":
        return "\n".join(doc.lines[ref.line - 1:ref.line + 3])
    return ref.text


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _only_optional_params_added(change: EntityChange) -> bool:
    """True when old calls are still valid: the only change is new parameters that have defaults."""
    if change.params_removed or change.params_changed or change.return_changed or not change.params_added:
        return False
    new = {p.name: p for p in change.after.params}
    return all(not new[n].required for n in change.params_added)


def _signature_forms(ent: Entity, declarations_only: bool = False) -> List[str]:
    """Ways documentation usually writes a signature: full, `name(args)`, and with `self`.

    declarations_only keeps only forms that clearly are declarations (`def f(a)`), not call-like
    `f(a)` text, which stays valid when only optional parameters were added.
    """
    sig = ent.signature
    if declarations_only and ent.language == "python":
        forms = [sig]
        p = sig.find("(")
        if p > 0 and ent.kind == "method":
            close = _match(sig, p, "(", ")")
            inner = sig[p + 1:close]
            for receiver in ("self", "cls"):
                forms.append(sig[:p + 1] + (f"{receiver}, {inner}" if inner else receiver) + sig[close:])
        return forms
    forms = [sig]
    p = sig.find("(")
    if p > 0:
        close = _match(sig, p, "(", ")")
        inner = sig[p + 1:close]
        call = ent.short_name + sig[p:close + 1]
        forms.append(call)
        if sig.startswith(("def ", "async def ")):
            forms.append(sig.split(" ", 1)[1] if sig.startswith("def ") else sig.split(" ", 2)[2])
            if ent.kind == "method":
                for receiver in ("self", "cls"):
                    args = f"{receiver}, {inner}" if inner else receiver
                    forms.append(sig[:p + 1] + args + sig[close:])
                    forms.append(f"{ent.short_name}({args})")
    return forms


# --------------------------------------------------------------------------- routes and paths

def removed_routes(change: EntityChange) -> List[str]:
    if change.change_type == ChangeType.REMOVED and change.before:
        return list(change.before.routes)
    return list(change.routes_removed)


def _route_path(route: str) -> str:
    return route.partition(" ")[2] or route


def _route_rules(aref: AffectedReference) -> List[_Candidate]:
    change, ref = aref.change, aref.reference
    route = aref.matched_name
    if route not in removed_routes(change):
        return []
    method, _, path = route.partition(" ")
    new_routes = list(change.after.routes) if change.after else []
    if any(_route_path(r) in ref.text or _route_text_matches(r, ref.text) for r in new_routes
           if _route_path(r) != path):
        return []  # the line also mentions a new route: migration note or already updated
    same_path = [r for r in new_routes if _route_path(r) == path]
    if same_path:
        # only the HTTP method changed
        new_methods = {r.partition(" ")[0] for r in same_path}
        if ref.doc_method and ref.doc_method == method and ref.doc_method not in new_methods:
            return [_Candidate("DRIFT005", 0.9,
                               [f"HTTP method of `{path}` changed: {method} -> {', '.join(sorted(new_methods))}."],
                               f"Document `{', '.join(sorted(new_methods))} {path}`.")]
        return []
    if change.after is None or not new_routes:
        return [_Candidate("DRIFT005", 0.95,
                           [f"Endpoint `{route}` no longer exists (handler `{change.name}`)."],
                           f"Remove `{route}` from the documentation.")]
    return [_Candidate("DRIFT005", 0.95 if ref.doc_method in (None, method) else 0.8,
                       [f"Route `{route}` changed to `{', '.join(new_routes)}`."],
                       f"Replace `{path}` with `{', '.join(_route_path(r) for r in new_routes)}`.")]


def _route_text_matches(route: str, text: str) -> bool:
    path = _route_path(route)
    seg = re.sub(r"\\\{[^}]+\\\}|\\:\w+|<[^>]+>", r"[^/\\s]+", re.escape(path))
    return re.search(seg + r"(?![\w/\-])", text) is not None


def _path_rules(aref: AffectedReference) -> List[_Candidate]:
    fc, ref = aref.file_change, aref.reference
    if fc.status == FileStatus.DELETED:
        return [_Candidate("DRIFT007", 0.9, [f"`{fc.path}` was deleted in this pull request."],
                           f"Remove or update the reference to `{fc.path}`.")]
    if fc.status == FileStatus.RENAMED and fc.old_path:
        if fc.path in ref.text:
            return []
        return [_Candidate("DRIFT008", 0.9, [f"`{fc.old_path}` was renamed to `{fc.path}`."],
                           f"Replace `{fc.old_path}` with `{fc.path}`.")]
    return []


# --------------------------------------------------------------------------- undocumented endpoints

def _is_documented(index: DocIndex, route: str) -> bool:
    """Documented when some reference names the same path with no method, or the same method."""
    method = route.partition(" ")[0]
    return any(r.doc_method in (None, method) or method == "ANY" for r in index.find_route(route))


def _undocumented_endpoints(index: DocIndex, analysis: PullRequestAnalysis) -> List[DriftFinding]:
    findings: List[DriftFinding] = []
    touched = set(analysis.doc_files_changed)
    for change in analysis.entity_changes:
        if change.after is None:
            continue
        if change.change_type in (ChangeType.ADDED,):
            new_routes = list(change.after.routes)
        elif change.change_type in (ChangeType.MODIFIED, ChangeType.RENAMED):
            new_routes = list(change.routes_added)
        else:
            continue
        for route in new_routes:
            if _route_path(route).strip("/") == "" or _is_documented(index, route):
                continue
            siblings = [e for e in analysis.head_entities.get(change.file, [])
                        if e.name != change.after.name and e.routes]
            first_ref: Dict[str, object] = {}
            for sib in siblings:
                for sr in sib.routes:
                    for ref in index.find_route(sr):
                        first_ref.setdefault(ref.doc_path, (ref, sr))
            for doc_path, (ref, sibling_route) in first_ref.items():
                findings.append(DriftFinding(
                    rule_id="DRIFT009", confidence=0.4, entity=change.name, kind=change.kind,
                    change_type=change.change_type.value, code_file=change.file, doc_path=doc_path,
                    doc_line=ref.line, doc_text=ref.text, section_title=ref.section_title,
                    reasons=[f"`{route}` is new, but this document lists other endpoints of `{change.file}` "
                             f"(e.g. `{sibling_route}`)."],
                    suggestion=f"Document `{route}` next to `{sibling_route}`.",
                    change=change, doc_updated_in_pr=doc_path in touched))
    return findings


# --------------------------------------------------------------------------- post-processing

def _dedupe(findings: List[DriftFinding]) -> List[DriftFinding]:
    best: Dict[Tuple[str, int, str, str], DriftFinding] = {}
    for f in findings:
        key = (f.doc_path, f.doc_line, f.entity, f.rule_id)
        if key not in best or f.confidence > best[key].confidence:
            best[key] = f
    result = list(best.values())
    # a section-level observation is redundant once a direct finding exists in the same section
    direct = {(f.doc_path, f.ref.reference.section_start if f.ref else 0, f.entity)
              for f in result if not f.section_level}
    result = [f for f in result
              if not (f.section_level and f.ref
                      and (f.doc_path, f.ref.reference.section_start, f.entity) in direct)]
    # a removed/renamed class already explains the findings of its own members on the same line
    parents = {(f.doc_path, f.doc_line, f.entity) for f in result
               if f.kind == "class" and f.rule_id in ("DRIFT001", "DRIFT002")}
    return [f for f in result
            if not any(f.doc_path == p and f.doc_line == l and f.entity.startswith(e + ".")
                       for p, l, e in parents)]
