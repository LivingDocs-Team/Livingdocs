import pytest
from app.submission import EvidenceCollector, EvidenceDisplayService, StatusTracker, SubmissionWorkflow

def test_ld107_collect_evidence():
    """LD-107 & LD-111: Kiểm thử trích xuất bằng chứng code"""
    code = "def process():\n    return True"
    evidence = EvidenceCollector.collect_evidence("app/main.py", 1, 2, code)
    assert evidence.file_path == "app/main.py"
    assert "return True" in evidence.code_snippet

def test_ld108_display_evidence():
    """LD-108 & LD-111: Kiểm thử hiển thị bằng chứng trên UI"""
    code = "x = 10"
    evidence = EvidenceCollector.collect_evidence("app/models.py", 1, 1, code)
    display_data = EvidenceDisplayService.format_evidence_for_display(evidence)
    assert "app/models.py" in display_data["display_title"]
    assert display_data["is_highlighted"] is True

def test_ld109_generation_status():
    """LD-109 & LD-111: Kiểm thử trạng thái sinh tài liệu"""
    status_obj = StatusTracker.get_generation_status("DOC-123", is_done=True)
    assert status_obj.status == "completed"
    assert status_obj.progress_percentage == 100

def test_ld110_submit_documentation():
    """LD-110 & LD-111: Kiểm thử quy trình gửi phê duyệt tài liệu"""
    code = "async def run(): pass"
    evidence = EvidenceCollector.collect_evidence("app/api.py", 1, 1, code)
    submission = SubmissionWorkflow.submit_documentation("DOC-123", [evidence])
    assert submission.status == "submitted"
    assert len(submission.evidences) == 1
