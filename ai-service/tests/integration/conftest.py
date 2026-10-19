"""Shared fixtures for the LD-390 integration tests.

`analyzer_output.json` is real output of the analyzer service (LD-328) for the small repository
in `fixtures/shop/`; refresh it with `python ai-service/scripts/capture_analyzer_output.py`.
"""
import copy
import json
import os
import pathlib
import re

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: needs running services (ANALYZER_URL, AI_SERVICE_URL)")
    config.addinivalue_line("markers", "llm: calls the real Claude API (RUN_LLM_TESTS=1 + ANTHROPIC_API_KEY)")


@pytest.fixture(autouse=True)
def _offline_by_default(monkeypatch, request):
    """Integration tests never call the real API unless marked `llm`."""
    if "llm" not in request.keywords:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(scope="session")
def _analysis():
    return json.loads((FIXTURES / "analyzer_output.json").read_text(encoding="utf-8"))


@pytest.fixture
def analysis(_analysis):
    """Fresh copy of the analyzer response: {scope, target, files}."""
    return copy.deepcopy(_analysis)


@pytest.fixture(scope="session")
def shop_readme():
    text = (FIXTURES / "README_shop.md").read_text(encoding="utf-8")
    return {"path": "README.md", "title": "Shop", "content": text}


# ---------- a well-behaved fake model, driven only by the prompt ----------

_OWN = re.compile(r"^- (E\d+): (.+?) \(", re.M)
_RETRIEVED = re.compile(r"^- ([CD]\d+): ", re.M)


class PromptDrivenModel:
    """Answers like a good model: describes every entity listed in the evidence catalog of the
    prompt and cites its own E id plus the retrieved C/D ids. Can be told to fail."""

    def __init__(self, fail_paths=(), garbage_paths=()):
        self.fail_paths, self.garbage_paths = set(fail_paths), set(garbage_paths)
        self.prompts = []

    def complete(self, system, messages):
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        path = re.search(r"Code analysis of file '([^']+)'", prompt).group(1)
        if path in self.fail_paths:
            raise TimeoutError("simulated API timeout")
        if path in self.garbage_paths:
            return "Sorry, I cannot answer in JSON."
        catalog = prompt.split("Evidence catalog:", 1)[1]
        own = _OWN.findall(catalog)
        extra = _RETRIEVED.findall(catalog)[:2]
        return json.dumps(self._answer(path, own, extra), ensure_ascii=False)

    @staticmethod
    def _answer(path, own, extra):
        classes, functions, endpoints = {}, [], []
        first = own[0][0] if own else None
        for eid, name in own:
            item = {"summary": f"Mô tả {name}.", "evidence": [eid, *extra], "confidence": 0.8}
            if " /" in name:                                   # "GET /carts/{id}"
                method, p = name.split(" ", 1)
                endpoints.append({"method": method, "path": p, **item})
            elif "." in name:                                  # "Class.method"
                cls, m = name.split(".", 1)
                classes.setdefault(cls, {"name": cls, "summary": f"Lớp {cls}.", "evidence": [],
                                         "methods": []})
                classes[cls]["methods"].append({"name": m, "returns": "Kết quả.", **item})
            elif name[:1].isupper():                           # class
                classes.setdefault(name, {"name": name, "methods": []}).update(item)
            else:
                functions.append({"name": name, "returns": "Kết quả.", **item})
        return {"overview": f"Tổng quan {path}.", "overview_evidence": [first] if first else [],
                "classes": list(classes.values()), "functions": functions, "endpoints": endpoints}


@pytest.fixture
def use_model(monkeypatch):
    """Route the API's background jobs through a fake model: use_model(PromptDrivenModel())."""
    from app import jobs
    from app.generator import DocGenerator

    def install(model, max_attempts=2):
        gen = DocGenerator(model, max_attempts=max_attempts, backoff_seconds=0)
        monkeypatch.setattr(jobs, "get_generator", lambda: gen)
        return model

    return install


def live_url(name):
    return (os.getenv(name) or "").rstrip("/")
