from typing import Dict, Any, List
from app.confidence import calculate_confidence_score  # Module đánh giá điểm tin cậy

def generate_drift_evidence(
    changed_code_info: Dict[str, Any],
    affected_docs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Tổng hợp bằng chứng Drift bao gồm Code diff, Doc snippet và điểm tin cậy
    """
    evidence_list = []
    
    for doc in affected_docs:
        fn_name = doc["function_name"]
        # Lấy chi tiết hàm bị thay đổi
        code_detail = next((f for f in changed_code_info.get("functions", []) if f["name"] == fn_name), {})
        
        # Đánh giá mức độ sai lệch (Drift Score)
        confidence_score = calculate_confidence_score(code_detail, doc["matched_snippet"])
        
        evidence = {
            "function_name": fn_name,
            "doc_path": doc["doc_path"],
            "code_details": code_detail,
            "doc_snippet": doc["matched_snippet"],
            "drift_detected": confidence_score > 0.6,
            "confidence_score": confidence_score,
            "explanation": f"Hàm `{fn_name}` có thay đổi về tham số hoặc logic nhưng tài liệu tại `{doc['doc_path']}` chưa cập nhật tương ứng."
        }
        evidence_list.append(evidence)
        
    return evidence_list
