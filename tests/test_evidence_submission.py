import pytest
from app.submission import EvidenceCollector, SubmissionWorkflow

def test_collect_grounding_evidence():
    """LD-107 & LD-111: Kiểm thử trích xuất bằng chứng mã nguồn"""
    code = "def hello():\n    print('Hello World')\n    return True"
    evidence = EvidenceCollector.collect_evidence("app/main.py", 1, 2, code)
    
    assert evidence.file_path == "app/main.py"
    assert evidence.start_line == 1
    assert "print('Hello World')" in evidence.code_snippet

def test_submit_documentation_workflow():
    """LD-110 & LD-111: Kiểm thử quy trình gửi phê duyệt tài liệu"""
    code = "async def fetch(): pass"
    evidence = EvidenceCollector.collect_evidence("app/api.py", 1, 1, code)
    submission = SubmissionWorkflow.submit_documentation("DOC-001", [evidence])
    
    assert submission.doc_id == "DOC-001"
    assert submission.status == "submitted"
    assert len(submission.evidences) == 1
