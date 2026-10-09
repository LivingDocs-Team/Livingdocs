"""Turns analyzed source code into documentation.

Two backends:
- AnthropicGenerator: uses the Claude API (set ANTHROPIC_API_KEY).
- OfflineGenerator: rule-based Markdown, used when no API key is set
  (handy for local development and tests).
"""
import json
import os
from typing import Protocol

from .models import ClassInfo, Endpoint, FileAnalysis, Function, Parameter, Template


class Generator(Protocol):
    def document_file(self, f: FileAnalysis, tpl: Template, lang: str) -> str: ...
    def summarize(self, target: str, file_docs: list, tpl: Template, lang: str) -> str: ...


# ---------------- AI backend ----------------

SYSTEM_PROMPT = (
    "You are a documentation generator for the LivingDocs platform. You receive the "
    "structured analysis of source code as JSON and write Markdown documentation. "
    "Only describe what the analysis supports; if purpose is unclear, say so briefly "
    "instead of guessing. Output Markdown only, no preamble."
)


class AnthropicGenerator:
    def __init__(self) -> None:
        import anthropic  # imported lazily so offline mode needs no package

        self.client = anthropic.Anthropic()
        self.model = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    def _ask(self, prompt: str) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()

    def document_file(self, f: FileAnalysis, tpl: Template, lang: str) -> str:
        prompt = (
            f"Template instructions:\n{tpl.instructions}\n\n"
            f"Use exactly these sections (as '##' headings, in this order, skip a "
            f"section only if there is nothing for it): {', '.join(tpl.sections)}\n"
            f"Start with a '#' heading containing the file path.\n"
            f"Write the documentation in language: {lang}\n\n"
            f"Code analysis (JSON):\n```json\n{f.model_dump_json(indent=2, exclude_none=True)}\n```"
        )
        return self._ask(prompt)

    def summarize(self, target: str, file_docs: list, tpl: Template, lang: str) -> str:
        joined = "\n\n---\n\n".join(file_docs)
        prompt = (
            f"Write a short overview (one '#' heading '{target}', then 1-3 paragraphs and a "
            f"bullet list of the files with one line each) for the documentation below. "
            f"Language: {lang}.\n\n{joined[:60000]}"
        )
        return self._ask(prompt)


# ---------------- Offline backend ----------------

def _params_table(params: list) -> str:
    if not params:
        return "_No parameters._\n"
    rows = ["| Name | Type | Default | Description |", "|---|---|---|---|"]
    for p in params:
        rows.append(
            f"| `{p.name}` | {p.type or '-'} | {p.default or '-'} | {p.description or '-'} |"
        )
    return "\n".join(rows) + "\n"


def _function_md(fn: Function, level: str) -> str:
    sig = fn.signature or f"{fn.name}({', '.join(p.name for p in fn.parameters)})"
    out = [f"{level} `{fn.name}`", "", f"```\n{sig}\n```", ""]
    if fn.docstring:
        out += [fn.docstring.strip(), ""]
    out += ["**Parameters**", "", _params_table(fn.parameters)]
    out += [f"**Returns:** {fn.return_type or 'not specified'}", ""]
    return "\n".join(out)


def _class_md(c: ClassInfo) -> str:
    bases = f" (inherits {', '.join(c.bases)})" if c.bases else ""
    out = [f"### Class `{c.name}`{bases}", ""]
    if c.docstring:
        out += [c.docstring.strip(), ""]
    for m in c.methods:
        out.append(_function_md(m, "####"))
    return "\n".join(out)


def _endpoint_md(e: Endpoint) -> str:
    out = [f"### `{e.http_method.upper()} {e.path}`", ""]
    if e.handler:
        out += [f"Handler: `{e.handler}`", ""]
    out += ["**Parameters**", "", _params_table(e.parameters)]
    if e.request_body:
        out += [f"**Request body:** {e.request_body}", ""]
    out += [f"**Response:** {e.response or 'not specified'}", ""]
    return "\n".join(out)


class OfflineGenerator:
    def document_file(self, f: FileAnalysis, tpl: Template, lang: str) -> str:
        parts = [f"# {f.path}", ""]
        for section in tpl.sections:
            key = section.lower()
            body = ""
            if key == "overview":
                body = (
                    f"Language: {f.language or 'unknown'}. Module: {f.module or '-'}. "
                    f"{len(f.classes)} class(es), {len(f.functions)} function(s), "
                    f"{len(f.endpoints)} endpoint(s)."
                )
            elif key == "classes" and f.classes:
                body = "\n".join(_class_md(c) for c in f.classes)
            elif key == "functions" and f.functions:
                body = "\n".join(_function_md(fn, "###") for fn in f.functions)
            elif key == "api endpoints" and f.endpoints:
                body = "\n".join(_endpoint_md(e) for e in f.endpoints)
            if body:
                parts += [f"## {section}", "", body, ""]
        return "\n".join(parts).rstrip() + "\n"

    def summarize(self, target: str, file_docs: list, tpl: Template, lang: str) -> str:
        names = [d.splitlines()[0].lstrip("# ").strip() for d in file_docs if d.strip()]
        lines = [f"# {target}", "", f"Documentation for {len(names)} file(s):", ""]
        lines += [f"- `{n}`" for n in names]
        return "\n".join(lines) + "\n"


def get_generator() -> Generator:
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicGenerator()
    return OfflineGenerator()
