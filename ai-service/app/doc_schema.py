"""Structured documentation returned by the AI (LD-340).

The AI never writes Markdown directly. It returns JSON matching `FileDoc`, which
is validated and then rendered by `renderer.py`. Names, types and structure always
come from the analyzer output; the AI only supplies descriptions. This keeps the
output format identical for every file and prevents invented classes/functions.
"""
import json
import re
from typing import List

from pydantic import BaseModel, Field, ValidationError


class ParamDoc(BaseModel):
    name: str
    description: str = ""


class FunctionDoc(BaseModel):
    name: str
    summary: str = ""
    parameters: List[ParamDoc] = Field(default_factory=list)
    returns: str = ""


class ClassDoc(BaseModel):
    name: str
    summary: str = ""
    methods: List[FunctionDoc] = Field(default_factory=list)


class EndpointDoc(BaseModel):
    method: str
    path: str
    summary: str = ""


class FileDoc(BaseModel):
    overview: str = ""
    classes: List[ClassDoc] = Field(default_factory=list)
    functions: List[FunctionDoc] = Field(default_factory=list)
    endpoints: List[EndpointDoc] = Field(default_factory=list)


class InvalidAIOutput(ValueError):
    """The AI response could not be parsed into a FileDoc."""


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_file_doc(text: str) -> FileDoc:
    """Parse the AI response into a FileDoc or raise InvalidAIOutput."""
    if not text or not text.strip():
        raise InvalidAIOutput("empty response")
    cleaned = _FENCE.sub("", text.strip()).strip()
    # tolerate prose around the JSON object
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise InvalidAIOutput("no JSON object found")
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as e:
        raise InvalidAIOutput(f"invalid JSON: {e.msg} (line {e.lineno})") from e
    if not isinstance(data, dict):
        raise InvalidAIOutput("top-level JSON value must be an object")
    try:
        return FileDoc.model_validate(data)
    except ValidationError as e:
        first = e.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise InvalidAIOutput(f"schema mismatch at '{loc}': {first['msg']}") from e


EXAMPLE_JSON = json.dumps(
    {
        "overview": "1-3 sentences about the purpose of the file.",
        "classes": [{
            "name": "ClassName",
            "summary": "What the class represents / is responsible for.",
            "methods": [{
                "name": "method_name",
                "summary": "What the method does.",
                "parameters": [{"name": "param", "description": "Meaning of the parameter."}],
                "returns": "Meaning of the return value.",
            }],
        }],
        "functions": [{
            "name": "function_name",
            "summary": "...",
            "parameters": [{"name": "param", "description": "..."}],
            "returns": "...",
        }],
        "endpoints": [{"method": "GET", "path": "/items/{id}", "summary": "..."}],
    },
    indent=2,
)
