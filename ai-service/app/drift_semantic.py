"""LD-154 Implement semantic drift detection.

An entity keeps its name and signature but *behaves* differently, so the documentation may now
describe the old behaviour. LD-146 only knew "the body changed"; this module says what changed,
from the entity's source before / after (analyzer `source`) or, without it, from the diff lines
inside the entity:

    exceptions     raise X / throw new X / throws X              added or no longer raised
    status_codes   status_code=201, HTTPException(404), abort(404), HttpStatus.NOT_FOUND,
                   status.HTTP_404_NOT_FOUND, ResponseEntity.status(...)
    values         number and string literals (timeouts, limits, rates, currency codes, ...)
    docstring      the entity's own description changed

Kinds (most specific first): status_codes_changed, exceptions_changed, values_changed,
docstring_changed, implementation_changed; undocumented_entity for new code that its file's
section does not describe.

The documentation is checked for what it still says, within PARAM_WINDOW lines after a mention
of the entity: a removed exception name, an old status code, an old value, a sentence of the old
docstring. Such a passage is strong evidence that the text is outdated.

Severity (rules in app/drift_severity.py, LD-157): base `behaviour_changed` (Low); +1
`contract_behaviour` (status codes, exceptions or docstring changed); +1 `doc_states_old_detail`;
+1 `large_change` (>= 15 changed lines); -1 `private_name`; semantic drift is capped at High.
"""
import re
from typing import Dict, List, Optional, Sequence, Set

from .drift_models import DRIFT_KINDS, DocMatch, SemanticSignal

KIND_ORDER = DRIFT_KINDS["semantic"]
SIGNAL_KIND = {"status_codes": "status_codes_changed", "exceptions": "exceptions_changed",
               "values": "values_changed", "docstring": "docstring_changed"}

HTTP_STATUS = {
    "OK": "200", "CREATED": "201", "ACCEPTED": "202", "NO_CONTENT": "204",
    "MOVED_PERMANENTLY": "301", "FOUND": "302", "NOT_MODIFIED": "304",
    "BAD_REQUEST": "400", "UNAUTHORIZED": "401", "PAYMENT_REQUIRED": "402", "FORBIDDEN": "403",
    "NOT_FOUND": "404", "METHOD_NOT_ALLOWED": "405", "CONFLICT": "409", "GONE": "410",
    "PRECONDITION_FAILED": "412", "PAYLOAD_TOO_LARGE": "413", "UNSUPPORTED_MEDIA_TYPE": "415",
    "UNPROCESSABLE_ENTITY": "422", "UNPROCESSABLE_CONTENT": "422", "TOO_MANY_REQUESTS": "429",
    "INTERNAL_SERVER_ERROR": "500", "NOT_IMPLEMENTED": "501", "BAD_GATEWAY": "502",
    "SERVICE_UNAVAILABLE": "503", "GATEWAY_TIMEOUT": "504",
}
STATUS_PATTERNS = [
    re.compile(r"status_code\s*=\s*([1-5]\d\d)\b"),
    re.compile(r"\bstatus\s*=\s*([1-5]\d\d)\b"),
    re.compile(r"HTTPException\(\s*([1-5]\d\d)\b"),
    re.compile(r"\babort\(\s*([1-5]\d\d)\b"),
    re.compile(r"ResponseEntity\s*\.\s*status\(\s*([1-5]\d\d)\b"),
    re.compile(r"\bHTTP_([1-5]\d\d)_[A-Z_]+"),
    re.compile(r"\bHttpStatus\.([A-Z_]+)"),
    re.compile(r"\bHTTPStatus\.([A-Z_]+)"),
]
RAISE = re.compile(r"\braise\s+([A-Z][\w.]*)")
THROW = re.compile(r"\bthrow\s+new\s+([A-Z][\w.]*)")
THROWS = re.compile(r"\)\s*throws\s+([\w.,\s]+?)\s*[{;]")
NUMBER = re.compile(r"(?<![\w.$])-?\d+(?:\.\d+)?(?![\w.])")
STRING = re.compile(r"\"([^\"\\\n]{2,40})\"|'([^'\\\n]{2,40})'")
TRIPLE = re.compile(r"(\"\"\"|''')[\s\S]*?\1")
COMMENT = re.compile(r"(^|\s)(#|//).*$", re.M)
BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
TRIVIAL_VALUES = {"0", "1", "-1", "0.0", "1.0", "2", "utf-8", "UTF-8"}


# ---------- signals from code ----------

def _strip_line_comment(line: str, lang: Optional[str] = None) -> str:
    """The line without its trailing comment, quotes respected: `#` in Python, `//` in Java
    (`//` is integer division in Python); unknown language: `#`, and `//` only at the start."""
    if lang is None and line.lstrip().startswith("//"):
        return ""
    marker = "//" if lang == "java" else "#"
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif line.startswith(marker, i):
            return line[:i]
        i += 1
    return line


def _code_only(text: str, lang: Optional[str] = None) -> str:
    """Code without docstrings and comments."""
    text = TRIPLE.sub(" ", text or "") if lang != "java" else (text or "")
    if lang != "python":
        text = BLOCK_COMMENT.sub(" ", text)
    return "\n".join(_strip_line_comment(line, lang) for line in text.splitlines())


def code_key(text: Optional[str], lang: Optional[str] = None) -> str:
    """LD-347: what must differ for a real code change - comments, docstrings, blank lines and
    whitespace / formatting are ignored."""
    return re.sub(r"\s+", "", _code_only(text or "", lang))


def line_key(line: str, lang: Optional[str] = None) -> str:
    """One diff line without its comment and whitespace; docstring text is kept (a docstring
    change is a real change, LD-154)."""
    return re.sub(r"\s+", "", _strip_line_comment(line, lang))


HEADER = re.compile(r"^\s*(?:@[\w.]+(?:\([^)]*\))?\s*)*(?:async\s+)?def\s+\w+\s*\(.*?\)\s*(?:->[^:]*)?:",
                    re.S)
JAVA_HEADER = re.compile(r"^\s*(?:@[\w.]+(?:\([^)]*\))?\s*)*[\w<>\[\],.?\s]*\(.*?\)\s*(?:throws[\w.,\s]+)?\{",
                         re.S)


def _body_only(text: str) -> str:
    """The code without its declaration (decorators, parameters and defaults belong to the
    signature, LD-153, not to the behaviour)."""
    for pat in (HEADER, JAVA_HEADER):
        m = pat.match(text)
        if m:
            return text[m.end():]
    return text


def _docstring_in(text: Optional[str]) -> Optional[str]:
    m = TRIPLE.search(text or "")
    if not m:
        return None
    body = m.group(0)[3:-3]
    return re.sub(r"\s+", " ", body).strip() or None


def exceptions_of(text: str) -> Set[str]:
    found = {m.rsplit(".", 1)[-1] for m in RAISE.findall(text) + THROW.findall(text)}
    for group in THROWS.findall(text):
        found |= {x.strip().rsplit(".", 1)[-1] for x in group.split(",") if x.strip()}
    return found


def status_codes_of(text: str) -> Set[str]:
    out: Set[str] = set()
    for pat in STATUS_PATTERNS:
        for value in pat.findall(text):
            code = value if value.isdigit() else HTTP_STATUS.get(value)
            if code:
                out.add(code)
    return out


def values_of(text: str, status_codes: Set[str]) -> Set[str]:
    out = {n for n in NUMBER.findall(text) if n not in status_codes}
    for a, b in STRING.findall(text):
        s = a or b
        if s.strip() and not re.fullmatch(r"[\W_]+", s):
            out.add(s)
    return {v for v in out if v not in TRIVIAL_VALUES}


def extract_signals(old_code: Optional[str], new_code: Optional[str],
                    old_doc: Optional[str] = None, new_doc: Optional[str] = None,
                    lang: Optional[str] = None) -> List[SemanticSignal]:
    """What differs between the old and the new code of one entity (whole source, or only the
    removed / added diff lines)."""
    out: List[SemanticSignal] = []
    old_c, new_c = _code_only(old_code or "", lang), _code_only(new_code or "", lang)
    old_status, new_status = status_codes_of(old_c), status_codes_of(new_c)

    def add(kind: str, old: Set[str], new: Set[str]) -> None:
        removed, added = sorted(old - new), sorted(new - old)
        if removed or added:
            out.append(SemanticSignal(kind=kind, removed=removed, added=added))

    add("status_codes", old_status, new_status)
    add("exceptions", exceptions_of(old_c) - {"HTTPException"}, exceptions_of(new_c) - {"HTTPException"})
    add("values", values_of(_body_only(old_c), old_status), values_of(_body_only(new_c), new_status))
    if old_doc is None and new_doc is None:      # diff only: docstrings among the changed lines
        old_doc, new_doc = _docstring_in(old_code), _docstring_in(new_code)
    if (old_doc or None) != (new_doc or None):
        out.append(SemanticSignal(kind="docstring", removed=[old_doc] if old_doc else [],
                                  added=[new_doc] if new_doc else []))
    return out


def without_renames(signals: List[SemanticSignal], renames: Sequence[tuple],
                    names: Sequence[str] = ()) -> List[SemanticSignal]:
    """Drop value changes that only follow the signature change: a renamed parameter or entity
    ("quantity must be positive" -> "qty must be positive") or the name of a parameter that was
    added or removed ({"timeout": timeout} -> {}, LD-347)."""
    if not renames and not names:
        return signals
    out = []
    for s in signals:
        if s.kind == "values":
            added = set(s.added)
            explained = {v for v in list(s.removed) + list(s.added) if v in set(names)}
            for v in s.removed:
                for old, new in renames:
                    w = re.sub(r"(?<![\w$])" + re.escape(old) + r"(?![\w$])", new, v)
                    if w != v and w in added:
                        explained |= {v, w}
            s = SemanticSignal(kind="values", removed=[v for v in s.removed if v not in explained],
                               added=[v for v in s.added if v not in explained])
            if not s.removed and not s.added:
                continue
        out.append(s)
    return out


def semantic_kind(signals: Sequence[SemanticSignal]) -> str:
    kinds = {SIGNAL_KIND[s.kind] for s in signals if s.kind in SIGNAL_KIND}
    for k in KIND_ORDER:
        if k in kinds:
            return k
    return "implementation_changed"


# ---------- what the documentation still says ----------

def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) >= 15]


def stale_details(doc, near: List[DocMatch], signals: Sequence[SemanticSignal],
                  window: int) -> List[DocMatch]:
    """Passages after a mention of the entity that state the old behaviour."""
    lines = doc.lines
    rows: Set[int] = set()
    for m in near:
        rows.update(doc.section(m.line - 1, window))       # LD-347: stay in the section
    rows_sorted = sorted(rows)
    out: Dict[tuple, DocMatch] = {}

    def look(pattern: "re.Pattern", term: str, kind: str, note: str, flags_ci: bool = False) -> None:
        for i in rows_sorted:
            text = re.sub(r"\s+", " ", lines[i]) if kind == "docstring" else lines[i]
            m = pattern.search(text)
            if m:
                out.setdefault((i, term), DocMatch(
                    term=term, target=term, line=i + 1, excerpt=lines[i].strip()[:200],
                    in_code=doc.in_code(i, m.start()) if kind != "docstring" else False,
                    kind=kind, note=note))
                return

    for s in signals:
        new = ", ".join(f"`{a}`" for a in s.added) or "none"
        if s.kind == "exceptions":
            for e in s.removed:
                look(re.compile(r"(?<![\w$])" + re.escape(e) + r"(?![\w$])"), e, "exception",
                     f"`{e}` is no longer raised (now: {new})")
        elif s.kind == "status_codes":
            for code in s.removed:
                names = [n for n, c in HTTP_STATUS.items() if c == code]
                alt = "|".join([re.escape(code)] + [re.escape(n.replace("_", " ")) for n in names])
                look(re.compile(r"(?<![\w.])(?:" + alt + r")(?![\w.])", re.I), code, "status_code",
                     f"status `{code}` is no longer returned (now: {new})")
        elif s.kind == "values":
            for v in s.removed:
                if re.fullmatch(r"-?\d", v):
                    continue      # single digits are too common in prose
                look(re.compile(r"(?<![\w.$])" + re.escape(v) + r"(?![\w$]|\.\d)"), v, "value",
                     f"value `{v}` changed (now: {new})")
        elif s.kind == "docstring" and s.removed:
            new_text = re.sub(r"\s+", " ", " ".join(s.added)).lower()
            for sentence in _sentences(s.removed[0]):
                if sentence.lower() in new_text:
                    continue      # this sentence is still true
                look(re.compile(re.escape(sentence), re.I), sentence, "docstring",
                     "the code's docstring no longer says this")
    return sorted(out.values(), key=lambda m: m.line)


def documented_as_new(doc, near: List[DocMatch], signals: Sequence[SemanticSignal],
                      window: int) -> List[DocMatch]:
    """LD-347: passages in the entity's section that already state the *new* behaviour (a new
    status code, exception, value or docstring sentence)."""
    lines = doc.lines
    rows = sorted({i for m in near for i in doc.section(m.line - 1, window)})
    out: List[DocMatch] = []

    def look(pattern: "re.Pattern", term: str, kind: str, normalize: bool = False) -> None:
        for i in rows:
            text = re.sub(r"\s+", " ", lines[i]) if normalize else lines[i]
            if pattern.search(text):
                out.append(DocMatch(term=term, target=term, line=i + 1,
                                    excerpt=lines[i].strip()[:200], kind=kind, note="new behaviour"))
                return

    for s in signals:
        for a in s.added:
            if s.kind == "exceptions":
                look(re.compile(r"(?<![\w$])" + re.escape(a) + r"(?![\w$])"), a, "exception")
            elif s.kind == "status_codes":
                look(re.compile(r"(?<![\w.])" + re.escape(a) + r"(?![\w.])"), a, "status_code")
            elif s.kind == "values" and not re.fullmatch(r"-?\d", a):
                look(re.compile(r"(?<![\w.$])" + re.escape(a) + r"(?![\w$]|\.\d)"), a, "value")
            elif s.kind == "docstring":
                old_text = re.sub(r"\s+", " ", " ".join(s.removed)).lower()
                for sentence in _sentences(a):
                    if sentence.lower() not in old_text:
                        look(re.compile(re.escape(sentence), re.I), sentence, "docstring", normalize=True)
    return out


def classify(hit):
    """LD-154: a hit on an entity whose behaviour changed (EntityChangeType.behavior_changed)."""
    from .drift_models import DriftType
    from .drift_rules import BIG_CHANGE_LINES, PARAM_WINDOW, Classified, code, private

    c = hit.target.change
    where = "this section" if hit.documents_file else "the documentation"
    kind = semantic_kind(c.signals)
    details = stale_details(hit.doc, hit.matches, c.signals, PARAM_WINDOW)
    if not details and documented_as_new(hit.doc, hit.matches, c.signals, PARAM_WINDOW):
        return None      # LD-347: the documentation already describes the new behaviour
    adjust = []
    contract = {s.kind for s in c.signals} & {"status_codes", "exceptions", "docstring"}
    if contract or "docstring changed" in c.details:
        adjust.append(("contract_behaviour", []))
    if details:
        adjust.append(("doc_states_old_detail", details))
    if c.changed_lines >= BIG_CHANGE_LINES:
        adjust.append(("large_change", []))
    if private(c.name):
        adjust.append(("private_name", []))

    what = "; ".join(c.details) if c.change.value == "behavior_changed" else "body changed"
    for s in c.signals:
        if s.kind == "docstring":
            continue
        parts = ([f"no longer {', '.join(s.removed)}"] if s.removed else []) + \
                ([f"now {', '.join(s.added)}"] if s.added else [])
        what += f"; {s.kind.replace('_', ' ')}: " + ", ".join(parts)
    stated = ""
    if details:
        stated = " It still says " + "; ".join(
            f"{code(m.term if len(m.term) < 60 else m.term[:57] + '...')} ({m.note})"
            for m in details) + "."
    return Classified(DriftType.semantic, kind, "behaviour_changed", "behavior_changed",
                      f"Behaviour of {c.kind} {code(c.name)} changed ({what}); "
                      f"{where} may describe the old behaviour.{stated}",
                      f"Check the description of {code(c.name)} against the new code"
                      + (" and update the passages listed as evidence." if details else "."),
                      before=c.old_signature, after=c.new_signature,
                      certainty=0.9 if details else 0.7,
                      breaking=kind == "status_codes_changed", adjust=adjust, details=details)


def classify_added(hit):
    """LD-154: new code in a documented file that its section does not describe."""
    from .drift_affected import entity_terms, search
    from .drift_models import DriftType
    from .drift_rules import Classified, code, private

    c, f = hit.target.change, hit.target.file
    if not hit.documents_file or private(c.name) or f.status.value == "added":
        return None
    if search(hit.doc, entity_terms(c.kind, c.name), own_file=True):
        return None  # already described (e.g. the section was edited by hand)
    return Classified(DriftType.semantic, "undocumented_entity", "undocumented_entity", "added",
                      f"New {c.kind} {code(c.name)} in {code(f.path)} is not described in this section.",
                      f"Document {code(c.new_signature or c.name)}.", after=c.new_signature or c.name,
                      certainty=0.8)
