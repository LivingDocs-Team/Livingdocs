import os
import re
from typing import List, Dict, Any
from app.doc_schema import DocSchema

class DocRetriever:
    def __init__(self, docs_dir: str = "Docs"):
        self.docs_dir = docs_dir

    def scan_docs(self) -> List[DocSchema]:
        """
        Quét toàn bộ tài liệu Markdown trong thư mục Docs/
        """
        documents = []
        if not os.path.exists(self.docs_dir):
            return documents

        for root, _, files in os.walk(self.docs_dir):
            for file in files:
                if file.endswith(".md"):
                    full_path = os.path.join(root, file)
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    documents.append(DocSchema(path=full_path, content=content))
        return documents

    def find_affected_docs(self, changed_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        [LD-148] Tìm các file và đoạn tài liệu bị ảnh hưởng bởi code thay đổi
        """
        all_docs = self.scan_docs()
        affected = []

        for elem in changed_elements:
            elem_name = elem.get("name", "")
            if not elem_name:
                continue

            for doc in all_docs:
                pattern = r'\b' + re.escape(elem_name) + r'\b'
                match = re.search(pattern, doc.content)
                if match:
                    # Trích xuất đoạn text xung quanh keyword (window 200 ký tự)
                    start = max(0, match.start() - 200)
                    end = min(len(doc.content), match.end() + 200)
                    snippet = doc.content[start:end]

                    affected.append({
                        "element_name": elem_name,
                        "doc_path": doc.path,
                        "snippet": snippet,
                        "element_details": elem
                    })
        return affected
