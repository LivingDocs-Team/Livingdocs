import json
import sys
import os

# Thêm ai-service và code-analyzer vào PYTHONPATH
sys.path.append(os.path.abspath("ai-service"))
sys.path.append(os.path.abspath("code-analyzer"))

from app.extractor import analyze_code_diff
from app.retrieval import DocRetriever
from app.evidence import build_drift_evidences

def run_drift_check(code_file_path: str, docs_dir: str = "Docs"):
    print(f"=== [LD-146] Analyzing PR Changes: {code_file_path} ===")
    if not os.path.exists(code_file_path):
        print(f"File {code_file_path} không tồn tại.")
        return

    with open(code_file_path, "r", encoding="utf-8") as f:
        code_content = f.read()

    analysis_res = analyze_code_diff(code_file_path, code_content)
    changed_functions = analysis_res.get("functions", [])
    print(f"-> Tìm thấy {len(changed_functions)} hàm bị thay đổi.")

    print("\n=== [LD-147 & LD-148] Matching Affected Docs ===")
    retriever = DocRetriever(docs_dir=docs_dir)
    affected_docs = retriever.find_affected_docs(changed_functions)
    print(f"-> Tìm thấy {len(affected_docs)} tài liệu liên quan bị ảnh hưởng.")

    print("\n=== [LD-149] Generating Drift Evidence ===")
    evidences = build_drift_evidences(affected_docs)
    
    report = {
        "status": "SUCCESS",
        "total_drifts": len([e for e in evidences if e.drift_detected]),
        "evidences": [e.__dict__ if hasattr(e, '__dict__') else e for e in evidences]
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report

if __name__ == "__main__":
    target_code = sys.argv[1] if len(sys.argv) > 1 else "code-analyzer/app/extractor.py"
    run_drift_check(target_code)
