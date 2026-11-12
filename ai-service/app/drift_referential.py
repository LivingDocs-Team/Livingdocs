"""LD-152 Implement referential drift detection.

The documentation *names* something that is no longer where it says:

    entity_removed        a class / function / method the Pull Request removes        High
    endpoint_removed      an endpoint the Pull Request removes                        Critical
    entity_renamed        a renamed class / function / method (same shape)            High
    endpoint_moved        an endpoint whose path changed (same handler)                Critical
    file_removed          the section of a deleted file                                High
                          another link / mention of a deleted file                     Medium
    module_removed        `shop.cart` / `com.acme.Order` of a deleted file              Medium
    file_moved            the old path of a moved file                                 Medium
                          (Low in the moved file's own section)
    module_moved          the old module / package name of a moved file                 Medium
    line_reference_stale  `shop/cart.py:19-25` or `cart.py#L19-L25` whose lines moved   Low
                          ... or whose lines were changed by the Pull Request           Medium

Private names (`_name`) are one level lower. Line references are typical of generated
documentation (evidence locations); they are checked against the diff of the file: lines before
the first hunk keep their number, lines after a hunk move by the lines it added minus removed,
lines inside a hunk are either unchanged context (mapped exactly) or changed.
"""
import re
from typing import Dict, List, Optional, Tuple

from .drift_affected import FILE_REMOVED, FILE_RENAMED, LINE_REFS, Hit, Term, excerpt
from .drift_compare import acknowledged
from .drift_changes import numbered
from .drift_models import DiffHunk, DocMatch, DriftType, EntityChangeType
from .drift_rules import Classified, code, private

MAX_LISTED_REFS = 5


# ---------- module names of a file ----------

JAVA_ROOTS = ("src/main/java/", "src/test/java/", "src/main/kotlin/", "java/")


def module_of(path: str) -> Optional[str]:
    """Python `shop/cart.py` -> `shop.cart`; Java `src/main/java/com/acme/Order.java` ->
    `com.acme.Order`. None when the name would be a single word (too common to search)."""
    p = path.replace("\\", "/")
    if p.endswith(".py"):
        p = p[:-3]
        if p.endswith("/__init__"):
            p = p[: -len("/__init__")]
        for root in ("src/", "lib/"):
            if p.startswith(root):
                p = p[len(root):]
        name = p.replace("/", ".")
    elif p.endswith(".java"):
        rest = next((p.split(r, 1)[1] for r in JAVA_ROOTS if r in p), None)
        if rest is None:
            return None
        name = rest[:-5].replace("/", ".")
    else:
        return None
    return name if "." in name and re.fullmatch(r"[\w.]+", name) else None


def module_terms(path: str) -> List[Term]:
    name = module_of(path)
    if not name:
        return []
    pat = re.compile(r"(?<![\w./-])" + re.escape(name) + r"(?![\w/-])")
    return [Term(name, path, pat, kind="module")]


# ---------- stale line references ----------

def line_map(hunks: List[DiffHunk]):
    """old line number -> new line number, or None when the Pull Request changed that line."""
    exact: Dict[int, Optional[int]] = {}
    shifts: List[Tuple[int, int]] = []       # (first old line after the hunk, offset after it)
    offset = 0
    for h in hunks:
        for o, n, line in numbered(h):
            if o is None:
                continue
            exact[o] = n if not line.startswith("-") else None
        offset += h.new_lines - h.old_lines
        shifts.append((h.old_start + h.old_lines, offset))

    def new_line(old: int) -> Optional[int]:
        if old in exact:
            return exact[old]
        off = 0
        for first_after, o in shifts:
            if old >= first_after:
                off = o
        return old + off

    return new_line


def ref_pattern(path: str) -> "re.Pattern":
    return re.compile(r"(?<![\w./-])" + re.escape(path)
                      + r"(?::(\d+)(?:-(\d+))?|#L(\d+)(?:-L?(\d+))?)(?![\d])")


def stale_line_refs(doc, path: str, old_path: str, hunks: List[DiffHunk]) -> List[DocMatch]:
    """References `old_path:a-b` / `old_path#La-Lb` in the documentation that no longer point to
    the same lines of `path`."""
    if not hunks:
        return []
    mapping = line_map(hunks)
    pat = ref_pattern(old_path)
    out: List[DocMatch] = []
    for i, line in enumerate(doc.lines):
        for m in pat.finditer(line):
            a = int(m.group(1) or m.group(3))
            b = int(m.group(2) or m.group(4) or a)
            if b < a:
                continue
            na, nb = mapping(a), mapping(b)
            inside = [mapping(x) for x in range(a, b + 1)]
            changed = any(x is None for x in inside) or na is None or nb is None \
                or (nb - na) != (b - a)
            if not changed and na == a and path == old_path:
                continue                       # still correct
            if changed:
                note = f"lines {a}-{b} were changed by the Pull Request" if b != a \
                    else f"line {a} was changed by the Pull Request"
            else:
                note = f"now {path}:{na}" + (f"-{nb}" if nb != na else "")
            out.append(DocMatch(term=m.group(0), target=path, line=i + 1, excerpt=excerpt(line),
                                in_code=doc.in_code(i, m.start()), kind="line_ref", note=note))
    return out


# ---------- classification ----------

def _file_kind(hit: Hit, removed: bool) -> str:
    kinds = {m.kind for m in hit.matches}
    if kinds and kinds <= {"module"}:
        return "module_removed" if removed else "module_moved"
    return "file_removed" if removed else "file_moved"


def classify(hit: Hit) -> Optional[Classified]:
    t, f, c = hit.target, hit.target.file, hit.target.change
    where = "this section" if hit.documents_file else "the documentation"

    if t.file_event == LINE_REFS:
        if not hit.matches:
            return None
        changed = [m for m in hit.matches if m.note and m.note.startswith(("lines", "line "))]
        listed = "; ".join(f"`{m.term}` ({m.note})" for m in hit.matches[:MAX_LISTED_REFS])
        more = len(hit.matches) - MAX_LISTED_REFS
        return Classified(
            DriftType.referential, "line_reference_stale",
            "line_reference_changed" if changed else "line_reference_shifted", "line_reference_stale",
            f"{where.capitalize()} has {len(hit.matches)} line reference(s) to {code(f.path)} that no "
            f"longer point to the same code: {listed}" + (f" and {more} more." if more > 0 else "."),
            "Update the line numbers" + (" and check the changed lines" if changed else "")
            + " (regenerating the section does both).",
            certainty=1.0)

    if t.file_event in (FILE_REMOVED, FILE_RENAMED) and acknowledged(
            hit.doc, hit.matches, f.path if t.file_event == FILE_RENAMED else None):
        return None      # LD-347: the documentation already says it was deleted / moved
    if t.file_event == FILE_REMOVED:
        kind = _file_kind(hit, removed=True)
        if hit.documents_file:
            return Classified(DriftType.referential, "file_removed", "file_section_removed", FILE_REMOVED,
                              f"{where} documents {code(f.path)}, which the Pull Request deletes.",
                              "Remove the section or move its content to the code that replaces it.",
                              before=f.path, breaking=True)
        named = ", ".join(sorted({code(m.term) for m in hit.matches}))
        return Classified(DriftType.referential, kind, "file_reference_removed", FILE_REMOVED,
                          f"The documentation names {named} of {code(f.path)}, "
                          "which the Pull Request deletes.",
                          f"Remove or replace the reference to {code(f.path)}.", before=f.path,
                          breaking=True)

    if t.file_event == FILE_RENAMED:
        if not hit.matches:
            return None
        kind = _file_kind(hit, removed=False)
        base = "own_section_moved" if hit.documents_file else "file_reference_moved"
        if kind == "module_moved":
            old_mod, new_mod = module_of(f.previous_path or ""), module_of(f.path)
            return Classified(DriftType.referential, kind, base, FILE_RENAMED,
                              f"{where.capitalize()} still names module {code(old_mod)}; "
                              f"{code(f.previous_path)} moved to {code(f.path)}.",
                              f"Replace {code(old_mod)} with {code(new_mod or f.path)}.",
                              before=old_mod, after=new_mod or f.path, breaking=True)
        return Classified(DriftType.referential, kind, base, FILE_RENAMED,
                          f"{where.capitalize()} still names {code(f.previous_path)}, "
                          f"moved to {code(f.path)}.",
                          f"Replace {code(f.previous_path)} with {code(f.path)}.",
                          before=f.previous_path, after=f.path, breaking=True)

    if c is None or not hit.matches:
        return None
    if acknowledged(hit.doc, hit.matches, c.name if c.change == EntityChangeType.renamed else None):
        return None      # LD-347: "`x` was removed", "`a` was renamed to `b`"
    endpoint = c.kind == "endpoint"
    base = "endpoint_gone" if endpoint else "entity_gone"
    adjust = [("private_name", [])] if private(c.name) else []

    if c.change == EntityChangeType.removed:
        if f.status.value == "removed" and hit.documents_file:
            return None  # covered by the file-level finding of the deleted file
        return Classified(DriftType.referential, "endpoint_removed" if endpoint else "entity_removed",
                          base, "removed",
                          f"{where.capitalize()} describes {c.kind} {code(c.name)}, "
                          "which the Pull Request removes.",
                          f"Remove the description of {code(c.name)} or point to its replacement.",
                          before=c.old_signature or c.name, breaking=True, adjust=adjust)
    if c.change == EntityChangeType.renamed:
        return Classified(DriftType.referential, "endpoint_moved" if endpoint else "entity_renamed",
                          base, "renamed",
                          f"{where.capitalize()} names {code(c.old_name)}, renamed to {code(c.name)}.",
                          f"Replace {code(c.old_name)} with {code(c.name)}.",
                          before=c.old_name, after=c.name, breaking=True, adjust=adjust)
    return None
