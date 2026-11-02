import ast
from pathlib import Path
from typing import Any, Dict, List

try:
    import javalang
except ImportError:  
    javalang = None

SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "target", "build", "dist"}
MAX_FILE_BYTES = 1_000_000


def _item(rel: str, start: int, end: int, commit: str, lines: List[str]) -> Dict[str, Any]:
    return {
        "file_path": rel,
        "start_line": start,
        "end_line": end,
        "commit_hash": commit,
        "source_code": "\n".join(lines[start - 1:end]),
    }


def _extract_python(text: str, rel: str, commit: str) -> List[Dict[str, Any]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            end = getattr(node, "end_lineno", None)
            if end:
                out.append(_item(rel, start, end, commit, lines))
    return out


def _java_end(lines: List[str], start: int) -> int:
    """Tìm dòng kết thúc bằng cách đếm dấu ngoặc nhọn (đơn giản, không xử lý chuỗi/comment chứa ngoặc)."""
    depth, opened = 0, False
    for idx in range(start - 1, len(lines)):
        for ch in lines[idx]:
            if ch == "{":
                depth += 1
                opened = True
            elif ch == "}":
                depth -= 1
            elif ch == ";" and not opened:
                return idx + 1          # method abstract / khai báo không có thân
        if opened and depth <= 0:
            return idx + 1
    return len(lines)


def _extract_java(text: str, rel: str, commit: str) -> List[Dict[str, Any]]:
    if javalang is None:
        return []
    try:
        tree = javalang.parse.parse(text)
    except Exception:
        return []
    lines = text.splitlines()
    kinds = (
        javalang.tree.ClassDeclaration,
        javalang.tree.InterfaceDeclaration,
        javalang.tree.EnumDeclaration,
        javalang.tree.MethodDeclaration,
        javalang.tree.ConstructorDeclaration,
    )
    out = []
    for _, node in tree.filter(kinds):
        if node.position is None:
            continue
        start = node.position.line
        out.append(_item(rel, start, _java_end(lines, start), commit, lines))
    return out


def extract_evidence(repo_root: Path, commit_hash: str) -> List[Dict[str, Any]]:
    """Trích evidence từ source code thật. Không bao giờ sinh text giả:
    không có gì trích được thì trả về danh sách rỗng."""
    results: List[Dict[str, Any]] = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.suffix not in (".py", ".java"):
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(repo_root).as_posix()
        if path.suffix == ".py":
            results.extend(_extract_python(text, rel, commit_hash))
        else:
            results.extend(_extract_java(text, rel, commit_hash))
    results.sort(key=lambda e: (e["file_path"], e["start_line"], e["end_line"]))
    return results
