from typing import Dict, Any

def calculate_confidence_score(code_details: Dict[str, Any], doc_snippet: str) -> float:
    """
    [LD-149] Thuật toán đánh giá độ tin cậy Documentation Drift (0.0 -> 1.0)
    """
    score = 0.5
    args = code_details.get("args", [])

    # Nếu tham số trong code mới không xuất hiện trong tài liệu -> Tăng độ nghi ngờ Drift
    missing_args = [arg for arg in args if arg not in doc_snippet]
    if missing_args:
        score += 0.35

    # Kiểm tra docstring hoặc loại thay đổi
    if code_details.get("docstring_changed", False):
        score += 0.15

    return min(score, 1.0)
