"""Managed documentation templates.

Three built-in templates are defined in code and cannot be changed. Templates created by users
are saved to a JSON file (TEMPLATES_FILE, default data/templates.json) so they survive a restart.

LD-227 template versions: every change of a custom template that alters its content saves a new
version (1, 2, 3 ...); earlier versions are kept unchanged and can be read or restored. Restoring
version n saves its content as a new version, so history is never rewritten. A file written
before versions existed is read as version 1 of each template.
"""
import json
import logging
import os
import pathlib
import threading
import uuid
from typing import Dict, List, Optional

from .models import Template, TemplateIn, TemplateVersion, now

log = logging.getLogger(__name__)
DEFAULT_FILE = "data/templates.json"

BUILT_IN = [
    Template(
        id="default",
        name="Standard technical docs",
        description="Overview, classes, functions and API endpoints.",
        instructions=(
            "Write clear technical documentation for developers. For every class, "
            "method, function and endpoint explain its purpose, each parameter "
            "(name, type, meaning) and the return value. Do not invent behaviour "
            "that is not supported by the code."
        ),
        sections=["Overview", "Classes", "Functions", "API Endpoints"],
        built_in=True,
    ),
    Template(
        id="api-reference",
        name="API reference",
        description="Focus on HTTP endpoints: parameters, request and response.",
        instructions=(
            "Document only the public API. For every endpoint give the HTTP method, "
            "path, purpose, a parameter table, request body, response and an example call."
        ),
        sections=["Overview", "API Endpoints"],
        built_in=True,
    ),
    Template(
        id="brief",
        name="Brief summary",
        description="Short summary for code review or onboarding.",
        instructions="Write a concise summary: at most two sentences per item.",
        sections=["Overview", "Classes", "Functions"],
        built_in=True,
    ),
]


class TemplateNameTaken(ValueError):
    """Another template already uses this name (names are unique, case-insensitive)."""


CONTENT = ("name", "description", "instructions", "sections")


def _content(t) -> dict:
    return {k: getattr(t, k) for k in CONTENT}


def _version_of(t: Template, number: int, created_at=None, restored_from: Optional[int] = None) -> TemplateVersion:
    return TemplateVersion(template_id=t.id, version=number, created_at=created_at or t.updated_at,
                           restored_from=restored_from, **_content(t))


class TemplateStore:
    def __init__(self, path: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self.path = pathlib.Path(path) if path else None
        self._items: Dict[str, Template] = {t.id: t for t in BUILT_IN}
        self._history: Dict[str, List[TemplateVersion]] = {t.id: [_version_of(t, 1)] for t in BUILT_IN}
        self._load()

    # ---------- persistence ----------

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            custom = [Template.model_validate(t) for t in raw.get("templates", [])]
            history = {k: [TemplateVersion.model_validate(v) for v in vs]
                       for k, vs in raw.get("history", {}).items()}
        except Exception as exc:  # corrupt file: keep it for inspection, start clean
            backup = self.path.with_suffix(f".corrupt-{now():%Y%m%d%H%M%S}.json")
            self.path.rename(backup)
            log.error("Could not read %s (%s); moved it to %s", self.path, exc, backup.name)
            return
        for t in custom:
            if t.id not in self._items:
                versions = history.get(t.id) or [_version_of(t, t.version, t.created_at)]
                # the current content is always the newest version
                t = t.model_copy(update={"built_in": False, "version": versions[-1].version})
                self._items[t.id] = t
                self._history[t.id] = versions

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        custom = [t.model_dump(mode="json") for t in self._items.values() if not t.built_in]
        history = {t.id: [v.model_dump(mode="json") for v in self._history[t.id]]
                   for t in self._items.values() if not t.built_in}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"templates": custom, "history": history}, ensure_ascii=False,
                                  indent=2), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: a crash never leaves a half-written file

    # ---------- queries ----------

    def list(self) -> List[Template]:
        """Built-in templates first, then custom ones by name."""
        items = list(self._items.values())
        return [t for t in items if t.built_in] + sorted(
            (t for t in items if not t.built_in), key=lambda t: t.name.lower())

    def get(self, template_id: str) -> Optional[Template]:
        return self._items.get(template_id)

    def versions(self, template_id: str) -> List[TemplateVersion]:
        """All versions, newest first. KeyError when the template does not exist."""
        if template_id not in self._items:
            raise KeyError(template_id)
        return list(reversed(self._history[template_id]))

    def version(self, template_id: str, number: int) -> TemplateVersion:
        """One version. KeyError when the template or the version does not exist."""
        for v in self.versions(template_id):
            if v.version == number:
                return v
        raise KeyError(f"{template_id} v{number}")

    def at_version(self, template_id: str, number: Optional[int]) -> Optional[Template]:
        """The template as it was at `number` (None = current), for generating documentation."""
        current = self._items.get(template_id)
        if current is None or number is None or number == current.version:
            return current
        try:
            v = self.version(template_id, number)
        except KeyError:
            return None
        return current.model_copy(update={**_content(v), "version": v.version})

    # ---------- changes ----------

    def _check_name(self, name: str, own_id: Optional[str] = None) -> None:
        for t in self._items.values():
            if t.id != own_id and t.name.lower() == name.lower():
                raise TemplateNameTaken(f"A template named '{t.name}' already exists")

    def create(self, data: TemplateIn) -> Template:
        with self._lock:
            self._check_name(data.name)
            stamp = now()
            tpl = Template(id=uuid.uuid4().hex[:8], created_at=stamp, updated_at=stamp,
                           **data.model_dump())
            self._items[tpl.id] = tpl
            self._history[tpl.id] = [_version_of(tpl, 1, stamp)]
            self._save()
            return tpl

    def _new_version(self, current: Template, content: dict,
                     restored_from: Optional[int] = None) -> Template:
        """Save `content` as the next version (nothing is saved when it equals the current one)."""
        if content == _content(current):
            return current
        stamp = now()
        tpl = Template(id=current.id, created_at=current.created_at, updated_at=stamp,
                       version=current.version + 1, **content)
        self._items[tpl.id] = tpl
        self._history[tpl.id].append(_version_of(tpl, tpl.version, stamp, restored_from))
        self._save()
        return tpl

    def restore(self, template_id: str, number: int) -> Template:
        """Make version `number` current again by saving its content as a new version."""
        with self._lock:
            current = self._items.get(template_id)
            if current is None:
                raise KeyError(template_id)
            if current.built_in:
                raise PermissionError("Built-in templates cannot be modified")
            old = self.version(template_id, number)
            self._check_name(old.name, own_id=template_id)
            return self._new_version(current, _content(old), restored_from=number)

    def update(self, template_id: str, data: TemplateIn) -> Template:
        with self._lock:
            current = self._items.get(template_id)
            if current is None:
                raise KeyError(template_id)
            if current.built_in:
                raise PermissionError("Built-in templates cannot be modified")
            self._check_name(data.name, own_id=template_id)
            return self._new_version(current, data.model_dump())

    def delete(self, template_id: str) -> None:
        with self._lock:
            current = self._items.get(template_id)
            if current is None:
                raise KeyError(template_id)
            if current.built_in:
                raise PermissionError("Built-in templates cannot be deleted")
            del self._items[template_id]
            del self._history[template_id]
            self._save()


templates = TemplateStore(os.getenv("TEMPLATES_FILE", DEFAULT_FILE) or None)
