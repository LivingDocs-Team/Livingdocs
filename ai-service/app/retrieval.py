import os
import re
from typing import List, Dict, Any

def scan_markdown_docs(docs_dir: str = "Docs") -> List[Dict[str, str]]:
    """
    Quét toàn bộ tài liệu Markdown trong thư mục Docs/
    """
    documents = []
    if not os.path.exists(docs_dir):
        return documents

    for root, _, files in os.walk(docs_dir):
        for file in files:
            if file.endswith(".md"):
                full_path = os.path.join(root, file)
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                documents.append({
                    "path": full_path,
                    "content": content
                })
    return documents

def match_affected_docs(changed_functions: List[Dict[str, Any]], docs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Xác định tài liệu nào bị ảnh hưởng dựa trên tên hàm/API/tham số
    """
    affected_docs = []
    for fn in changed_functions:
        fn_name = fn["name"]
        for doc in docs:
            # Tìm kiếm tên hàm hoặc từ khóa liên quan trong file Markdown
            if re.search(r'\b' + re.escape(fn_name) + r'\b', doc["content"]):
                affected_docs.append({
                    "function_name": fn_name,
                    "doc_path": doc["path"],
                    "matched_snippet": extract_snippet(doc["content"], fn_name)
                })
    return affected_docs

def extract_snippet(text: str, keyword: str, window: int = 200) -> str:
    match = re.search(r'\b' + re.escape(keyword) + r'\b', text)
    if not match:
        return ""
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    return text[start:end]
