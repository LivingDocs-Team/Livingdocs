"""Prompt design for documentation generation (LD-340)."""
import json

from .doc_schema import EXAMPLE_JSON
from .models import FileAnalysis, Template

MAX_SOURCE_CHARS = 1500       # per function/method snippet
MAX_ANALYSIS_CHARS = 40000    # whole analysis JSON in one prompt

LANGUAGE_NAMES = {"vi": "Vietnamese (tiếng Việt)", "en": "English"}

SYSTEM_PROMPT = """You are the documentation engine of LivingDocs.
You receive the structured analysis of ONE source file (produced by a static code
analyzer) and write documentation for it.

Rules:
1. Respond with ONE JSON object only. No Markdown, no code fences, no text before or after it.
2. The JSON must follow exactly the shape given by the user. Use the exact names of
   classes, methods, functions, parameters and endpoints from the analysis.
3. Document only entities that appear in the analysis. Never invent new ones.
4. Base every description on the analysis (signature, types, docstring, source snippet).
   If the purpose cannot be determined, say so briefly instead of guessing.
5. Keep each description short and factual: 1-2 sentences for summaries,
   one sentence for parameters and return values.
6. Write all descriptions in the language requested by the user."""


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n... (truncated)"


def compact_analysis(f: FileAnalysis) -> str:
    """Analysis as JSON for the prompt: drop empty fields, cut long source snippets."""
    data = f.model_dump(exclude_none=True, exclude={"status", "error"})
    for fn in data.get("functions", []):
        if "source" in fn:
            fn["source"] = _truncate(fn["source"], MAX_SOURCE_CHARS)
    for cls in data.get("classes", []):
        for m in cls.get("methods", []):
            if "source" in m:
                m["source"] = _truncate(m["source"], MAX_SOURCE_CHARS)
    text = json.dumps(data, ensure_ascii=False, indent=1)
    if len(text) > MAX_ANALYSIS_CHARS:
        # still too large: drop all source snippets, keep the structure
        for fn in data.get("functions", []):
            fn.pop("source", None)
        for cls in data.get("classes", []):
            for m in cls.get("methods", []):
                m.pop("source", None)
        text = json.dumps(data, ensure_ascii=False, indent=1)
    return text


def build_file_prompt(f: FileAnalysis, tpl: Template, lang: str) -> str:
    return (
        f"Language for all descriptions: {LANGUAGE_NAMES.get(lang, lang)}\n\n"
        f"Documentation style (from template '{tpl.name}'):\n{tpl.instructions}\n\n"
        f"Return JSON with exactly this shape (lists may be empty):\n{EXAMPLE_JSON}\n\n"
        f"Code analysis of file '{f.path}':\n{compact_analysis(f)}"
    )


def build_repair_prompt(error: str) -> str:
    return (
        f"Your previous response could not be used: {error}.\n"
        "Reply again with ONLY the JSON object in the required shape, nothing else."
    )
