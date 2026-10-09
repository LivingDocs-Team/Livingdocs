"""Managed documentation templates (in-memory store with built-in defaults)."""
import threading
import uuid
from typing import Dict, List, Optional

from .models import Template, TemplateIn

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


class TemplateStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: Dict[str, Template] = {t.id: t for t in BUILT_IN}

    def list(self) -> List[Template]:
        return list(self._items.values())

    def get(self, template_id: str) -> Optional[Template]:
        return self._items.get(template_id)

    def create(self, data: TemplateIn) -> Template:
        tpl = Template(id=uuid.uuid4().hex[:8], **data.model_dump())
        with self._lock:
            self._items[tpl.id] = tpl
        return tpl

    def update(self, template_id: str, data: TemplateIn) -> Template:
        with self._lock:
            current = self._items.get(template_id)
            if current is None:
                raise KeyError(template_id)
            if current.built_in:
                raise PermissionError("Built-in templates cannot be modified")
            tpl = Template(id=template_id, **data.model_dump())
            self._items[template_id] = tpl
            return tpl

    def delete(self, template_id: str) -> None:
        with self._lock:
            current = self._items.get(template_id)
            if current is None:
                raise KeyError(template_id)
            if current.built_in:
                raise PermissionError("Built-in templates cannot be deleted")
            del self._items[template_id]


templates = TemplateStore()
