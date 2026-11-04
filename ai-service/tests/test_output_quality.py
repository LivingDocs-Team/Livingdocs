"""Output quality fixes found while checking analyzer -> ai-service on the real repository.

- docstring sections (Args/Returns, NumPy, reST, Javadoc) fill parameter and return descriptions
- overloaded / repeated names no longer share one evidence id and one description
- module is derived from the path when the analyzer does not send it
- endpoints without AI description use the handler's docstring and return type
- skipped files never show an empty reason ("JavaSyntaxError: ")
"""
import json
import os

os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402

from app.docstrings import parse_docstring  # noqa: E402
from app.doc_schema import FileDoc  # noqa: E402
from app.generator import DocGenerator  # noqa: E402
from app.jobs import jobs, run_job, skip_reason  # noqa: E402
from app.models import FileAnalysis, GenerateRequest  # noqa: E402
from app.normalize import module_from_path, normalize  # noqa: E402
from app.templates import templates  # noqa: E402

TPL = templates.get("default")


# ---------- docstrings ----------

GOOGLE = """Parse source code according to the specified programming language.

Args:
    code: Source code to parse.
    language (str): Programming language ('python' or
        'java').

Returns:
    A tuple (syntax_tree, error_message).

Raises:
    ValueError: unknown language.
"""


def test_google_docstring():
    d = parse_docstring(GOOGLE)
    assert d.summary == "Parse source code according to the specified programming language."
    assert d.params == {"code": "Source code to parse.",
                        "language": "Programming language ('python' or 'java')."}
    assert d.returns == "A tuple (syntax_tree, error_message)."


def test_numpy_docstring():
    d = parse_docstring("Sum.\n\nParameters\n----------\na : int\n    First.\n\nReturns\n-------\nint\n    Total.\n")
    assert (d.summary, d.params, d.returns) == ("Sum.", {"a": "First."}, "int: Total.")


def test_rest_and_javadoc_docstrings():
    rest = parse_docstring("Greet.\n:param str name: The name.\n:param age: Age\n   in years.\n:returns: text\n:rtype: str")
    assert rest.params == {"name": "The name.", "age": "Age in years."} and rest.returns == "text"
    jd = parse_docstring("/**\n * Get one order.\n * @param id order id\n * @return the order\n * @throws X when missing\n */")
    assert (jd.summary, jd.params, jd.returns) == ("Get one order.", {"id": "order id"}, "the order")


def test_plain_docstring_kept_whole():
    d = parse_docstring("First paragraph.\n\nSecond paragraph\ncontinues here.")
    assert d.summary == "First paragraph.\n\nSecond paragraph continues here." and not d.params


def _offline(analysis: dict, lang: str = "en"):
    f = normalize(FileAnalysis.model_validate(analysis))
    return DocGenerator(client=None).document_file(f, TPL, lang)


def test_offline_doc_uses_docstring_sections():
    r = _offline({"path": "app/analyzer.py", "language": "python", "functions": [{
        "name": "parse_code", "signature": "def parse_code(code: str, language: str)",
        "parameters": [{"name": "code", "type": "str"}, {"name": "language", "type": "str"}],
        "docstring": GOOGLE, "lineno": 8, "end_lineno": 35}]})
    md = r.markdown
    assert "| `code` | str | - | Source code to parse. |" in md
    assert "Returns:** Not specified — A tuple (syntax_tree, error_message)." in md
    assert "Args:" not in md, "docstring sections must not be pasted into the summary"


# ---------- unique names ----------

JAVA = {
    "path": "src/main/java/demo/OrderController.java", "language": "java",
    "classes": [{"name": "OrderController", "methods": [
        {"name": "get", "parameters": [{"name": "id", "type": "Long"}], "lineno": 9, "end_lineno": 9},
        {"name": "get", "parameters": [{"name": "code", "type": "String"}], "lineno": 10, "end_lineno": 10},
        {"name": "create", "parameters": [], "lineno": 12, "end_lineno": 12}]}],
}


def test_overloads_get_their_own_name_and_evidence():
    r = _offline(JAVA)
    ents = {e.name: e for e in r.report.entities}
    a, b = ents["OrderController.get(Long)"], ents["OrderController.get(String)"]
    assert a.evidence[0].id != b.evidence[0].id
    assert (a.evidence[0].line_start, b.evidence[0].line_start) == (9, 10)
    assert "`get(Long)`" in r.markdown and "`get(String)`" in r.markdown


def test_repeated_names_are_numbered():
    f = normalize(FileAnalysis.model_validate({"path": "a.py", "language": "python", "functions": [
        {"name": "load", "lineno": 3}, {"name": "load", "lineno": 7}],
        "classes": [{"name": "A"}, {"name": "A"}]}))
    assert [fn.name for fn in f.functions] == ["load", "load#2"]
    assert [c.name for c in f.classes] == ["A", "A#2"]
    # same-type overloads fall back to numbering
    g = normalize(FileAnalysis.model_validate({"path": "B.java", "classes": [{"name": "B", "methods": [
        {"name": "f", "parameters": [{"name": "x", "type": "int"}]},
        {"name": "f", "parameters": [{"name": "y", "type": "int"}]}]}]}))
    assert [m.name for m in g.classes[0].methods] == ["f(int)", "f(int)#2"]


def test_ai_descriptions_match_overloads():
    """The AI sees the normalized names, so its answer maps back to the right overload."""
    answer = {"overview": "Orders.", "classes": [{"name": "OrderController", "summary": "API.", "evidence": ["E1"],
              "methods": [{"name": "get(Long)", "summary": "By id.", "evidence": ["E2"]},
                          {"name": "get(String)", "summary": "By code.", "evidence": ["E3"]},
                          {"name": "create", "summary": "Create.", "evidence": ["E4"]}]}]}

    class Fake:
        def complete(self, system, messages):
            assert '"get(Long)"' in messages[-1]["content"]
            return json.dumps(answer)

    f = normalize(FileAnalysis.model_validate(JAVA))
    r = DocGenerator(client=Fake()).document_file(f, TPL, "en")
    assert "By id." in r.markdown and "By code." in r.markdown
    assert not [w for w in r.warnings if "no description" in w]


# ---------- module ----------

@pytest.mark.parametrize("path,lang,module", [
    ("app/services/cart.py", "python", "app.services.cart"),
    ("src/shop/__init__.py", "python", "shop"),
    ("services/x/src/main/java/com/acme/web/OrderController.java", "java", "com.acme.web"),
    ("README.md", None, None),
])
def test_module_from_path(path, lang, module):
    assert module_from_path(path, lang) == module


def test_module_is_kept_when_sent():
    f = normalize(FileAnalysis.model_validate({"path": "a/b.py", "language": "python", "module": "custom"}))
    assert f.module == "custom"


# ---------- endpoints ----------

def test_endpoint_uses_handler_docstring_and_return_type():
    r = _offline({"path": "api.py", "language": "python",
                  "functions": [{"name": "get_cart_total", "return_type": "float",
                                 "parameters": [{"name": "cart_id", "type": "int"}],
                                 "docstring": "Total price of a cart.\n\nArgs:\n    cart_id: Cart id.\n\nReturns:\n    Sum of item prices."}],
                  "endpoints": [{"http_method": "GET", "path": "/carts/{cart_id}/total", "handler": "get_cart_total",
                                 "parameters": [{"name": "cart_id", "type": "int"}]}]})
    ep = r.markdown.split("### `GET /carts/{cart_id}/total`")[1]
    assert "Total price of a cart." in ep
    assert "| `cart_id` | int | - | Cart id. |" in ep
    assert "**Response:** `float` — Sum of item prices." in ep


# ---------- skipped files ----------

def test_skip_reason_never_empty():
    assert skip_reason("JavaSyntaxError: ", "invalid") == "JavaSyntaxError (analyzer status 'invalid', no details)"
    assert skip_reason(None, "empty") == "analyzer status 'empty'"
    assert skip_reason("SyntaxError line 3: bad", "invalid") == "SyntaxError line 3: bad"


def test_job_end_to_end_with_overloads_and_skips():
    req = GenerateRequest.model_validate({"scope": "repository", "target": "demo", "files": [
        JAVA, {"path": "R.java", "language": "java", "status": "invalid", "error": "JavaSyntaxError: "}]})
    job = jobs.create(req, TPL)
    run_job(job.id, req, DocGenerator(client=None), TPL)
    job = jobs.get(job.id)
    assert job.status.value == "completed"
    assert "R.java: skipped (JavaSyntaxError (analyzer status 'invalid', no details))." in job.warnings
    rep = jobs.get_report(job.id)
    ids = [e.evidence[0].id for fr in rep.files for e in fr.entities if e.evidence]
    assert len(ids) == len(set(ids)), "every entity must have its own evidence"
