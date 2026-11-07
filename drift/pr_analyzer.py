"""Analyze pull request changes (LD-146).

Input : the unified diff of the PR plus a way to read old/new file contents.
Output: PullRequestAnalysis = changed files + entity-level changes (what code API changed).
"""
from __future__ import annotations

import difflib
from typing import Callable, Dict, List, Optional, Tuple

from .diff_parser import parse_unified_diff
from .entities import ExtractionError, extract_entities
from .models import (ChangeType, Entity, EntityChange, FileChange, FileStatus,
                     PullRequestAnalysis)

Reader = Callable[[str], Optional[str]]
MAX_FILE_BYTES = 1_000_000


def analyze_pull_request(diff_text: str, read_old: Reader, read_new: Reader,
                         base: Optional[str] = None, head: Optional[str] = None) -> PullRequestAnalysis:
    """Analyze a PR.

    read_old(path) / read_new(path) return the file content before / after the PR, or None
    when the file does not exist on that side.
    """
    analysis = PullRequestAnalysis(files=parse_unified_diff(diff_text), base=base, head=head)
    removed: List[EntityChange] = []
    added: List[EntityChange] = []

    for fc in analysis.files:
        if fc.binary or not fc.language:
            continue
        old_src = None if fc.status == FileStatus.ADDED else read_old(fc.old_path or fc.path)
        new_src = None if fc.status == FileStatus.DELETED else read_new(fc.path)
        if new_src is None and fc.status != FileStatus.DELETED:
            analysis.warnings.append(f"{fc.path}: content not available, entity changes not analysed.")
            continue
        if _too_big(old_src) or _too_big(new_src):
            analysis.warnings.append(f"{fc.path}: skipped (file larger than {MAX_FILE_BYTES // 1000} KB).")
            continue
        old_entities = _extract(fc.old_path or fc.path, old_src, fc.language, analysis, "before")
        new_entities = _extract(fc.path, new_src, fc.language, analysis, "after")
        if old_entities is None or new_entities is None:
            continue  # one side is unparseable: comparing would report every entity as added/removed
        if new_src is not None:
            analysis.head_entities[fc.path] = new_entities
        changes = compare_entities(old_entities, new_entities)
        for c in changes:
            if c.change_type == ChangeType.REMOVED:
                removed.append(c)
            elif c.change_type == ChangeType.ADDED:
                added.append(c)
            else:
                analysis.entity_changes.append(c)

    analysis.entity_changes += _pair_moves(removed, added, analysis)
    analysis.entity_changes.sort(key=lambda c: (c.file, c.before.line if c.before else c.after.line))
    return analysis


def _too_big(text: Optional[str]) -> bool:
    return text is not None and len(text) > MAX_FILE_BYTES


def _extract(path: str, source: Optional[str], language: str, analysis: PullRequestAnalysis,
             side: str) -> Optional[List[Entity]]:
    """Entities of one side of a file; [] when the file does not exist there, None when unparseable."""
    if source is None:
        return []
    try:
        return extract_entities(path, source, language)
    except ExtractionError as exc:
        analysis.warnings.append(f"{path} ({side}): cannot parse, entity changes not analysed ({exc}).")
        return None


# --------------------------------------------------------------------------- comparison

def compare_entities(old: List[Entity], new: List[Entity]) -> List[EntityChange]:
    """Entity-level diff between two versions of one file."""
    changes: List[EntityChange] = []
    old_groups = _group(old)
    new_groups = _group(new)
    only_old: List[Entity] = []
    only_new: List[Entity] = []

    for key in sorted(set(old_groups) | set(new_groups)):
        olds, news = list(old_groups.get(key, [])), list(new_groups.get(key, []))
        # overloads (same name): pair identical parameter lists first, then by position
        for o in list(olds):
            twin = next((n for n in news if _same_params(o, n)), None)
            if twin is not None:
                olds.remove(o)
                news.remove(twin)
                c = _diff(o, twin)
                if c:
                    changes.append(c)
        while olds and news and (len(olds) == len(news) or len(olds) == 1 or len(news) == 1):
            o, n = olds.pop(0), news.pop(0)
            c = _diff(o, n)
            if c:
                changes.append(c)
        only_old += olds
        only_new += news

    renames, only_old, only_new = _pair_renames(only_old, only_new)
    changes += renames
    changes += [EntityChange(ChangeType.REMOVED, e.kind, e.name, e.file, before=e,
                             details=[f"{e.kind} `{e.name}` removed"]) for e in only_old]
    changes += [EntityChange(ChangeType.ADDED, e.kind, e.name, e.file, after=e,
                             details=[f"{e.kind} `{e.name}` added"]) for e in only_new]
    return changes


def _group(entities: List[Entity]) -> Dict[Tuple[str, str], List[Entity]]:
    groups: Dict[Tuple[str, str], List[Entity]] = {}
    for e in entities:
        groups.setdefault((e.kind, e.name), []).append(e)
    return groups


def _same_params(a: Entity, b: Entity) -> bool:
    return [(p.name, p.type) for p in a.params] == [(p.name, p.type) for p in b.params]


def _diff(old: Entity, new: Entity) -> Optional[EntityChange]:
    """Describe how `new` differs from `old` (same qualified name); None when identical."""
    c = EntityChange(ChangeType.MODIFIED, new.kind, new.name, new.file, before=old, after=new)
    old_p = {p.name: p for p in old.params}
    new_p = {p.name: p for p in new.params}
    c.params_added = tuple(n for n in new_p if n not in old_p)
    c.params_removed = tuple(n for n in old_p if n not in new_p)
    c.params_changed = tuple(
        n for n in new_p if n in old_p
        and (old_p[n].type != new_p[n].type or old_p[n].has_default != new_p[n].has_default
             or old_p[n].variadic != new_p[n].variadic))
    if not (c.params_added or c.params_removed or c.params_changed) \
            and [p.name for p in old.params if p.name in new_p] != [p.name for p in new.params if p.name in old_p]:
        c.params_changed = tuple(new_p)  # same names, different order
    c.return_changed = (old.return_type or "") != (new.return_type or "")
    c.routes_added = tuple(r for r in new.routes if r not in old.routes)
    c.routes_removed = tuple(r for r in old.routes if r not in new.routes)
    c.bases_changed = old.bases != new.bases
    c.members_added = tuple(f for f in new.fields if f not in old.fields)
    c.members_removed = tuple(f for f in old.fields if f not in new.fields)
    c.body_changed = bool(old.body_digest and old.body_digest != new.body_digest)

    if c.params_added:
        c.details.append("parameters added: " + ", ".join(c.params_added))
    if c.params_removed:
        c.details.append("parameters removed: " + ", ".join(c.params_removed))
    for n in c.params_changed:
        o, p = old_p.get(n), new_p.get(n)
        if o and p:
            c.details.append(f"parameter `{n}` changed: {_param_text(o)} -> {_param_text(p)}")
    if not (c.params_added or c.params_removed) and c.params_changed and len(c.params_changed) == len(new_p) \
            and not any(old_p.get(n) and new_p.get(n) and _param_text(old_p[n]) != _param_text(new_p[n])
                        for n in c.params_changed):
        c.details.append("parameter order changed")
    if c.return_changed:
        c.details.append(f"return type: {old.return_type or '-'} -> {new.return_type or '-'}")
    if c.routes_removed:
        c.details.append("routes removed: " + ", ".join(c.routes_removed))
    if c.routes_added:
        c.details.append("routes added: " + ", ".join(c.routes_added))
    if c.bases_changed:
        c.details.append(f"bases: ({', '.join(old.bases)}) -> ({', '.join(new.bases)})")
    if c.members_removed:
        c.details.append("attributes removed: " + ", ".join(c.members_removed))
    if c.members_added:
        c.details.append("attributes added: " + ", ".join(c.members_added))
    if c.body_changed and not c.api_changed:
        c.details.append("implementation changed (signature unchanged)")

    if not (c.api_changed or c.body_changed):
        return None
    return c


def _param_text(p) -> str:
    text = f"{p.variadic}{p.name}"
    if p.type:
        text += f": {p.type}"
    if p.has_default:
        text += " = ..."
    return text


def _pair_renames(removed: List[Entity], added: List[Entity]):
    """Removed + added entity of one file with the same shape -> one RENAMED change."""
    renames: List[EntityChange] = []
    removed, added = list(removed), list(added)
    for o in list(removed):
        candidates = [n for n in added if n.kind == o.kind and _same_params(o, n)
                      and n.return_type == o.return_type and n.name.rsplit(".", 1)[0:-1] == o.name.rsplit(".", 1)[0:-1]]
        if not candidates:
            continue
        same_body = [n for n in candidates if o.body_digest and n.body_digest == o.body_digest]
        similar = [n for n in candidates
                   if difflib.SequenceMatcher(None, o.short_name, n.short_name).ratio() >= 0.7]
        only_pair = (len([x for x in removed if x.kind == o.kind]) == 1 and len(candidates) == 1
                     and len([x for x in added if x.kind == o.kind]) == 1)
        pick = (same_body or similar or (candidates if only_pair else []))
        if not pick:
            continue
        n = pick[0]
        removed.remove(o)
        added.remove(n)
        c = _diff_for_rename(o, n)
        renames.append(c)
    return renames, removed, added


def _diff_for_rename(old: Entity, new: Entity) -> EntityChange:
    c = EntityChange(ChangeType.RENAMED, new.kind, new.name, new.file, before=old, after=new,
                     renamed_from=old.name)
    c.routes_added = tuple(r for r in new.routes if r not in old.routes)
    c.routes_removed = tuple(r for r in old.routes if r not in new.routes)
    c.members_added = tuple(f for f in new.fields if f not in old.fields)
    c.members_removed = tuple(f for f in old.fields if f not in new.fields)
    c.details.append(f"{new.kind} renamed: `{old.name}` -> `{new.name}`")
    return c


def _pair_moves(removed: List[EntityChange], added: List[EntityChange],
                analysis: PullRequestAnalysis) -> List[EntityChange]:
    """An entity removed from one file and added to another under the same name was moved."""
    result: List[EntityChange] = []
    pool = list(added)
    for r in removed:
        match = next((a for a in pool if a.kind == r.kind and a.name == r.name and a.file != r.file), None)
        if match is None:
            result.append(r)
            continue
        pool.remove(match)
        moved = EntityChange(ChangeType.MOVED, r.kind, r.name, match.file, before=r.before, after=match.after,
                             moved_from=r.file)
        moved.details.append(f"{r.kind} `{r.name}` moved: {r.file} -> {match.file}")
        result.append(moved)
    result += pool
    return result
