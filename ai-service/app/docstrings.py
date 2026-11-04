"""Read summary, parameter and return descriptions out of a docstring.

Used when the AI is not available (offline / fallback) and as a default when the AI
leaves a parameter or return value undescribed. Supported styles:

- Google:  ``Args:`` / ``Parameters:`` / ``Returns:`` sections, ``name (type): text``
- NumPy:   ``Parameters`` / ``Returns`` headings underlined with dashes
- reST:    ``:param name:`` / ``:param type name:`` / ``:returns:``
- Javadoc: ``@param name text`` / ``@return text``

Anything not recognised stays in the summary, so nothing written by the developer is lost.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_PARAM_HEADS = {"args", "arguments", "parameters", "params", "keyword args", "keyword arguments",
                "other parameters"}
_RETURN_HEADS = {"returns", "return", "yields", "yield"}
_OTHER_HEADS = {"raises", "raise", "exceptions", "attributes", "examples", "example", "notes", "note",
                "see also", "warnings", "warning", "references", "todo"}
_ALL_HEADS = _PARAM_HEADS | _RETURN_HEADS | _OTHER_HEADS

_GOOGLE_HEAD = re.compile(r"^\s*([A-Za-z][A-Za-z ]*):\s*$")
_NUMPY_RULE = re.compile(r"^\s*-{3,}\s*$")
_REST_PARAM = re.compile(r"^\s*:param\s+(?:[^:]*\s)?([\w*]+)\s*:\s*(.*)$")
_REST_RETURN = re.compile(r"^\s*:returns?\s*:\s*(.*)$")
_REST_OTHER = re.compile(r"^\s*:(?:type|rtype|raises?|except(?:ion)?)\b[^:]*:")
_JAVADOC_PARAM = re.compile(r"^\s*@param\s+([\w$]+)\s*(.*)$")
_JAVADOC_RETURN = re.compile(r"^\s*@returns?\s*(.*)$")
_JAVADOC_OTHER = re.compile(r"^\s*@(?:throws|exception|see|since|author|version|deprecated)\b")
_GOOGLE_ITEM = re.compile(r"^([\w*]+)\s*(?:\(([^)]*)\))?\s*:\s*(.*)$")
_NUMPY_ITEM = re.compile(r"^([\w*]+)\s*:\s*(.*)$")


@dataclass
class ParsedDoc:
    summary: str = ""
    params: Dict[str, str] = field(default_factory=dict)
    returns: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)   # "Attributes:" section of a class


def _clean(lines: List[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(x.strip() for x in lines)).strip()


def _strip_javadoc(text: str) -> str:
    """Remove `/** ... */` and leading `*` if the analyzer sent the raw comment."""
    text = re.sub(r"^\s*/\*\*+|\*+/\s*$", "", text.strip())
    return "\n".join(re.sub(r"^\s*\*\s?", "", ln) for ln in text.splitlines())


def _paragraphs(lines: List[str]) -> str:
    paras, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln)
        elif cur:
            paras.append(_clean(cur))
            cur = []
    if cur:
        paras.append(_clean(cur))
    return "\n\n".join(p for p in paras if p)


def _items(lines: List[str], numpy: bool) -> Dict[str, str]:
    """`name (type): text` items with indented continuation lines."""
    out: Dict[str, List[str]] = {}
    current: Optional[str] = None
    base = None
    for ln in lines:
        if not ln.strip():
            continue
        indent = len(ln) - len(ln.lstrip())
        if base is None:
            base = indent
        m = (_NUMPY_ITEM if numpy else _GOOGLE_ITEM).match(ln.strip())
        if indent <= base and m:
            current = m.group(1).lstrip("*")
            out[current] = [] if numpy else [m.group(3)]
        elif current is not None:
            out[current].append(ln)
    return {k: _clean(v) for k, v in out.items() if _clean(v)}


def _returns(lines: List[str], numpy: bool) -> str:
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return ""
    if numpy:
        # first line is the type (optionally "name : type"), the indented lines describe it
        rtype = lines[0].strip()
        desc = _clean(lines[1:])
        return f"{rtype}: {desc}" if desc else rtype
    m = re.match(r"^([\w\[\], .|]+):\s*(.+)$", lines[0].strip())
    first = m.group(2) if m and " " not in m.group(1).strip() else lines[0].strip()
    return _clean([first] + lines[1:])


def parse_docstring(doc: Optional[str]) -> ParsedDoc:
    if not doc or not doc.strip():
        return ParsedDoc()
    text = _strip_javadoc(doc) if doc.lstrip().startswith("/**") else doc
    lines = text.expandtabs(4).splitlines()

    summary: List[str] = []
    params: Dict[str, str] = {}
    returns = ""
    sections: Dict[str, List[str]] = {}
    kinds: Dict[str, bool] = {}
    current = None
    tag_target: Optional[tuple] = None   # ("param", name) / ("return", None) for reST / Javadoc
    tag_lines: Dict[tuple, List[str]] = {}

    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        low = s.rstrip(":").strip().lower()
        if low in _ALL_HEADS and _NUMPY_RULE.match(nxt):          # NumPy heading
            current, tag_target = low, None
            sections[current], kinds[current] = [], True
            i += 2
            continue
        g = _GOOGLE_HEAD.match(ln)
        if g and g.group(1).strip().lower() in _ALL_HEADS:        # Google heading
            current, tag_target = g.group(1).strip().lower(), None
            sections[current], kinds[current] = [], False
            i += 1
            continue
        m = _REST_PARAM.match(ln) or _JAVADOC_PARAM.match(ln)
        if m:
            tag_target = ("param", m.group(1).lstrip("*"))
            tag_lines[tag_target] = [m.group(2)]
            current = "tags"
            i += 1
            continue
        m = _REST_RETURN.match(ln) or _JAVADOC_RETURN.match(ln)
        if m:
            tag_target = ("return", None)
            tag_lines[tag_target] = [m.group(1)]
            current = "tags"
            i += 1
            continue
        if _REST_OTHER.match(ln) or _JAVADOC_OTHER.match(ln):
            tag_target, current = None, "tags"
            i += 1
            continue
        if current is None:
            summary.append(ln)
        elif current == "tags":
            if tag_target is not None and s:
                tag_lines[tag_target].append(ln)
        else:
            sections[current].append(ln)
        i += 1

    attributes: Dict[str, str] = {}
    for head, body in sections.items():
        if head == "attributes":
            attributes.update(_items(body, kinds[head]))
        elif head in _PARAM_HEADS:
            params.update(_items(body, kinds[head]))
        elif head in _RETURN_HEADS and not returns:
            returns = _returns(body, kinds[head])
    for (kind, name), body in tag_lines.items():
        text_ = _clean(body)
        if kind == "param" and text_:
            params[name] = text_
        elif kind == "return" and text_:
            returns = text_
    return ParsedDoc(summary=_paragraphs(summary), params=params, returns=returns, attributes=attributes)
