import json
import sys
from app.extractor import analyze_code_diff
from app.retrieval import scan_markdown_docs, match_affected_docs
from app.evidence import generate_drift_evidence

def run_drift_detection(sample_code_path: str, docs_dir: str = "Docs"):
    print("=== [LD-146] Analyzing PR Code Changes ===")
    with open(sample_code_path, "r", encoding="utf-8") as f:
        code_content = f.read()
    
    analysis_result = analyze_code_diff(sample_code_path, code_content)
    print(f"Detected Functions: {[f['name'] for f in analysis_result.get('functions', [])]}")

    print("\n=== [LD-147 & LD-148] Scanning Docs & Matching Affected Files ===")
    docs = scan_markdown_docs(docs_dir)
    affected_docs = match_affected_docs(analysis_result.get("functions", []), docs)
    print(f"Found {len(affected_docs)} documentation matches.")

    print("\n=== [LD-149] Generating Drift Evidence ===")
    evidences = generate_drift_evidence(analysis_result, affected_docs)
    
    report = {
        "status": "SUCCESS",
        "total_drifts": len([e for e in evidences if e["drift_detected"]]),
        "evidences": evidences
    }
    
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report

if __name__ == "__main__":
    target_code = sys.argv[1] if len(sys.argv) > 1 else "code-analyzer/app/extractor.py"
    run_drift_detection(target_code)
