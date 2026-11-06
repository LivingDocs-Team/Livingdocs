def calculate_confidence_score(code_detail: dict, doc_snippet: str) -> float:
    """
    Tính toán chỉ số tin cậy về mức độ Documentation Drift (0.0 đến 1.0)
    """
    score = 0.5
    args = code_detail.get("args", [])
    
    # Check xem các tham số mới của hàm có xuất hiện trong snippet của doc hay không
    missing_args = [arg for arg in args if arg not in doc_snippet]
    if missing_args:
        score += 0.35
    
    return min(score, 1.0)
