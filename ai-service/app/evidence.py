from typing import List, Dict, Any
from app.doc_schema import DriftEvidence
from app.confidence import calculate_confidence_score

def build_drift_evidences(affected_docs: List[Dict[str, Any]]) -> List[DriftEvidence]:
    """
    [LD-149] Tổng hợp bằng chứng Drift và tính điểm tin cậy (Confidence Score)
    """
    evidences = []

    for item in affected_docs:
        elem_details = item.get("element_details", {})
        snippet = item.get("snippet", "")
        elem_name = item.get("element_name", "")
        doc_path = item.get("doc_path", "")

        # Tính điểm tin cậy từ confidence.py
        score = calculate_confidence_score(elem_details, snippet)
        is_drift = score > 0.6

        explanation = (
            f"Phát hiện sự lệch pha giữa code và tài liệu tại '{doc_path}'. "
            f"Thành phần '{elem_name}' có thay đổi thông số/logic nhưng tài liệu chưa cập nhật đầy đủ."
            if is_drift else "Tài liệu đồng bộ với thay đổi trong mã nguồn."
        )

        evidence = DriftEvidence(
            element_name=elem_name,
            doc_path=doc_path,
            code_summary=str(elem_details),
            doc_snippet=snippet,
            confidence_score=score,
            drift_detected=is_drift,
            explanation=explanation
        )
        evidences.append(evidence)

    return evidences
