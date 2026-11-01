import pytest
from app.evidence_models import GroundingEvidence, GenerationStatus, DocumentationSubmission
from app.models import FileAnalysis, Function
from app.submission import (
    EvidenceCollector,
    StatusTracker,
    SubmissionWorkflow,
    STATUS_STORE,
    SUBMISSION_STORE,
    EVIDENCE_STORE
)


@pytest.fixture(autouse=True)
def reset_stores():
    """Xóa dữ liệu bộ nhớ trước mỗi bài test."""
    STATUS_STORE.clear()
    SUBMISSION_STORE.clear()
    EVIDENCE_STORE.clear()


def test_evidence_extraction_from_real_analysis():
    """Test 1: Evidence phải trích xuất từ dữ liệu AST thực tế, không hardcode."""
    doc_id = "doc-106-real"
    mock_files = [
        FileAnalysis(
            file_path="app/submission.py",
            functions=[Function(name="submit_documentation", start_line=45, end_line=65)]
        )
    ]
    
    evidences = EvidenceCollector.extract_from_analysis(doc_id, mock_files, commit_hash="git-hash-12345")
    
    assert len(evidences) == 1
    assert evidences[0].file_path == "app/submission.py"
    assert evidences[0].start_line == 45
    assert evidences[0].end_line == 65
    assert evidences[0].commit_hash == "git-hash-12345"
    assert "submit_documentation" in evidences[0].code_snippet


def test_status_tracking_persistence():
    """Test 2: Status phản ánh đúng tiến độ job thực tế và được lưu trữ lại."""
    doc_id = "doc-106-status"
    
    # Khởi tạo job
    status_1 = StatusTracker.update_status(doc_id, progress=50, status_str="processing", step="Extracting Evidence")
    assert status_1.progress_percentage == 50
    
    # Query lại xem có lưu trữ đúng không
    retrieved_status = StatusTracker.get_status(doc_id)
    assert retrieved_status.progress_percentage == 50
    assert retrieved_status.status == "processing"
    
    # Hoàn tất job
    StatusTracker.update_status(doc_id, progress=100, status_str="completed", step="Done")
    assert StatusTracker.get_status(doc_id).progress_percentage == 100


def test_full_submission_e2e_flow_and_persistence():
    """Test 3: Luồng nộp tài liệu thành công E2E và dữ liệu được lưu trữ bền vững."""
    doc_id = "doc-106-e2e"
    user_id = "lamgiahuy"
    
    # Step 1: Tạo Evidence từ AST
    mock_files = [FileAnalysis(file_path="app/models.py", functions=[Function(name="test", start_line=1, end_line=5)])]
    EvidenceCollector.extract_from_analysis(doc_id, mock_files, commit_hash="hash-abc")
    
    # Step 2: Cập nhật Job hoàn thành 100%
    StatusTracker.update_status(doc_id, progress=100, status_str="completed", step="Finished")
    
    # Step 3: Thực hiện Nộp tài liệu
    submission = SubmissionWorkflow.submit_documentation(doc_id, submitted_by=user_id)
    
    assert submission.document_id == doc_id
    assert submission.submitted_by == user_id
    assert submission.status == "submitted"
    assert len(submission.evidence_ids) == 1
    
    # Step 4: Kiểm tra dữ liệu được lưu lại trong DB/Store (Persistence Check)
    saved_sub = SubmissionWorkflow.get_submission(doc_id)
    assert saved_sub is not None
    assert saved_sub.submission_id == submission.submission_id


def test_submission_validation_errors():
    """Test 4: Bắt các lỗi nghiệp vụ nghiêm ngặt (Incomplete, Missing Evidence, Duplicate Submit)."""
    doc_id = "doc-106-invalid"
    
    # Case A: Nộp khi job chưa hoàn tất (< 100%) -> Báo lỗi
    StatusTracker.update_status(doc_id, progress=80, status_str="processing")
    with pytest.raises(ValueError, match="Cannot submit document while generation is in progress"):
        SubmissionWorkflow.submit_documentation(doc_id, "lamgiahuy")
        
    # Cho job completed nhưng THIẾU Evidence
    StatusTracker.update_status(doc_id, progress=100, status_str="completed")
    
    # Case B: Nộp khi thiếu Evidence -> Báo lỗi
    with pytest.raises(ValueError, match="Missing grounding evidence"):
        SubmissionWorkflow.submit_documentation(doc_id, "lamgiahuy")
        
    # Thêm Evidence hợp lệ
    mock_files = [FileAnalysis(file_path="main.py", functions=[Function(name="main", start_line=1, end_line=10)])]
    EvidenceCollector.extract_from_analysis(doc_id, mock_files, commit_hash="hash-xyz")
    
    # Nộp lần đầu -> Thành công
    SubmissionWorkflow.submit_documentation(doc_id, "lamgiahuy")
    
    # Case C: Nộp trùng lần thứ 2 (Tài liệu đã bị khóa) -> Báo lỗi
    with pytest.raises(ValueError, match="Document is locked and already submitted"):
        SubmissionWorkflow.submit_documentation(doc_id, "lamgiahuy")
