"""Managed documentation templates.

Three built-in templates are defined in code and cannot be changed. Templates created by users
are saved to a JSON file (TEMPLATES_FILE, default data/templates.json) so they survive a restart.
"""
import json
import logging
import os
import pathlib
import threading
import uuid
from typing import Dict, List, Optional

from .models import Template, TemplateIn, now

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


class TemplateStore:
    def __init__(self, path: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self.path = pathlib.Path(path) if path else None
        self._items: Dict[str, Template] = {t.id: t for t in BUILT_IN}
        self._load()

    # ---------- persistence ----------

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            custom = [Template.model_validate(t) for t in raw.get("templates", [])]
        except Exception as exc:  # corrupt file: keep it for inspection, start clean
            backup = self.path.with_suffix(f".corrupt-{now():%Y%m%d%H%M%S}.json")
            self.path.rename(backup)
            log.error("Could not read %s (%s); moved it to %s", self.path, exc, backup.name)
            return
        for t in custom:
            if t.id not in self._items:
                self._items[t.id] = t.model_copy(update={"built_in": False})

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        custom = [t.model_dump(mode="json") for t in self._items.values() if not t.built_in]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"templates": custom}, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: a crash never leaves a half-written file

    # ---------- queries ----------

    def list(self) -> List[Template]:
        """Built-in templates first, then custom ones by name."""
        items = list(self._items.values())
        return [t for t in items if t.built_in] + sorted(
            (t for t in items if not t.built_in), key=lambda t: t.name.lower())

    def get(self, template_id: str) -> Optional[Template]:
        return self._items.get(template_id)

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
            self._save()
            return tpl

    def update(self, template_id: str, data: TemplateIn) -> Template:
        with self._lock:
            current = self._items.get(template_id)
            if current is None:
                raise KeyError(template_id)
            if current.built_in:
                raise PermissionError("Built-in templates cannot be modified")
            self._check_name(data.name, own_id=template_id)
            tpl = Template(id=template_id, created_at=current.created_at, updated_at=now(),
                           **data.model_dump())
            self._items[template_id] = tpl
            self._save()
            return tpl

    def delete(self, template_id: str) -> None:
        with self._lock:
            current = self._items.get(template_id)
            if current is None:
                raise KeyError(template_id)
            if current.built_in:
                raise PermissionError("Built-in templates cannot be deleted")
            del self._items[template_id]
            self._save()


templates = TemplateStore(os.getenv("TEMPLATES_FILE", DEFAULT_FILE) or None)
