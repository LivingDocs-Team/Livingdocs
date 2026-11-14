"""Measure the quality of analyzer + ai-service output on a real code base.

Sends every .py / .java file under the given folders to the running analyzer, generates
documentation with the running ai-service, and compares both against the source files.

    ANALYZER_URL=http://localhost:8000 AI_SERVICE_URL=http://localhost:8001 \
        python ai-service/scripts/quality_report.py app ai-service services backend

Prints a Markdown summary; `--json out.json` also saves the numbers.
"""
import argparse
import ast
import collections
import json
import os
import pathlib
import re
import sys
import time

import httpx

SKIP_DIRS = {"node_modules", "__pycache__", ".venv", "venv", "target", "build", ".git", "fixtures"}
LANG = {".py": "python", ".java": "java"}
ROUTE = re.compile(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\b")
DECOS = {"get", "post", "put", "delete", "patch", "route", "api_route"}


def collect(root: pathlib.Path, folders):
    for folder in folders:
        for p in sorted((root / folder).rglob("*")):
            if p.suffix in LANG and p.is_file() and not SKIP_DIRS & set(p.parts):
                yield p


def python_truth(text):
    tree = ast.parse(text.lstrip("﻿"))
    top = tree.body
    funcs = [n for n in top if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n for n in top if isinstance(n, ast.ClassDef)]
    methods = sum(1 for c in classes for m in c.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)))
    routes = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 for d in n.decorator_list
                 if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr.lower() in DECOS)
    return {"classes": len(classes), "callables": len(funcs) + methods, "routes": routes}


def java_truth(text):
    return {"classes": len(re.findall(r"\b(class|interface|enum|record)\s+\w+", text)),
            "callables": None, "routes": len(ROUTE.findall(text)),
            "javadoc": len(re.findall(r"/\*\*", text))}


def wait(ai, job_id, timeout=300):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = httpx.get(f"{ai}/jobs/{job_id}", timeout=10).json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.5)
    raise TimeoutError(job_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json")
    a = ap.parse_args()
    analyzer, ai = os.environ["ANALYZER_URL"].rstrip("/"), os.environ["AI_SERVICE_URL"].rstrip("/")
    root = pathlib.Path(a.root).resolve()
    paths = list(collect(root, a.folders))
    files = [{"path": p.relative_to(root).as_posix(), "content": p.read_text(encoding="utf-8", errors="replace"),
              "language": LANG[p.suffix]} for p in paths]
    analysis = httpx.post(f"{analyzer}/api/v1/analyze-repo", json={"scope": "repository", "target": root.name,
                                                                    "files": files}, timeout=300).json()
    by_path = {f["path"]: f for f in analysis["files"]}
    m = collections.Counter()
    for f in files:
        out = by_path[f["path"]]
        lang = f["language"]
        m[f"{lang}_files"] += 1
        m[f"{lang}_{out['status']}"] += 1
        if out["status"] != "ok":
            err = (out.get("error") or "").strip()
            if out["status"] == "invalid" and not (err.split(":", 1)[1].strip() if ":" in err else err):
                m["invalid_without_detail"] += 1
            continue
        truth = python_truth(f["content"]) if lang == "python" else java_truth(f["content"])
        m[f"{lang}_classes_in_source"] += truth["classes"]
        m[f"{lang}_classes_found"] += len(out["classes"])
        m[f"{lang}_routes_in_source"] += truth["routes"]
        m[f"{lang}_endpoints_found"] += len(out["endpoints"])
        found = len(out["functions"]) + sum(len(c["methods"]) for c in out["classes"])
        m[f"{lang}_callables_found"] += found
        if truth["callables"] is not None:
            m[f"{lang}_callables_in_source"] += truth["callables"]
        m[f"{lang}_javadoc_blocks"] += truth.get("javadoc", 0)
        m[f"{lang}_docstrings_found"] += sum(1 for fn in out["functions"] + [x for c in out["classes"] for x in c["methods"]]
                                            if fn.get("docstring"))
        m["classes_with_lines"] += sum(1 for c in out["classes"] if c.get("lineno") or c.get("line_start"))
        m["modules_filled"] += 1 if out.get("module") else 0

    job = httpx.post(f"{ai}/generate", json=analysis, timeout=60).json()
    job = wait(ai, job["id"])
    rep = httpx.get(f"{ai}/jobs/{job['id']}/report", timeout=30).json()
    md = httpx.get(f"{ai}/jobs/{job['id']}/result", timeout=30).text
    statuses = collections.Counter(fr["status"] for fr in job["file_results"])
    levels = collections.Counter()
    for fr in rep["files"]:
        ids = []
        for e in fr["entities"]:
            m["entities"] += 1
            levels[e["level"]] += 1
            own = [ev for ev in e["evidence"] if ev["kind"] == "source"]
            if own:
                ids.append(own[0]["id"])
                m["evidence_with_lines" if own[0].get("line_start") else "evidence_file_only"] += 1
            if e["name"].split(".")[-1] not in md:
                m["entities_missing_in_markdown"] += 1
        m["shared_evidence_ids"] += len(ids) - len(set(ids))
    m["placeholder_descriptions"] = len(re.findall(r"Chưa có mô tả|No confirmed description", md))
    rows = re.findall(r"^\| `[^`]+` \|[^|]*\|[^|]*\| (.*) \|$", md, re.M)
    m["parameter_rows"] = len(rows)
    m["parameter_rows_described"] = sum(1 for r in rows if r.strip() != "-")
    rets = re.findall(r"^\*\*(?:Giá trị trả về|Returns):\*\* (.*)$", md, re.M)
    m["returns_described"] = sum(1 for r in rets if "—" in r)
    m["skipped_reason_without_detail"] = len(re.findall(r"^- `[^`]+`: .*:\s*$", md, re.M))

    lines = [f"# Quality report: {root.name}", "",
             f"Files: {len(files)} · job {job['status']} · confidence {job.get('confidence')} "
             f"({job.get('confidence_level')}) · file results {dict(statuses)}", "",
             "| Metric | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(m.items())]
    lines += [f"| confidence levels | {dict(levels)} |", ""]
    print("\n".join(lines))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps({"metrics": m, "levels": levels, "file_results": statuses},
                                                   indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())



