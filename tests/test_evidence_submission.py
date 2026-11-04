import pytest
from app.models import SubmissionRequest, GroundingEvidence
from app.submission import SubmissionWorkflow, EvidenceCollector, SUBMISSION_STORE, EVIDENCE_STORE

def test_submission_workflow():
    job_id = "job-test-106"
    ev = GroundingEvidence(file_path="app/main.py", start_line=1, end_line=10, code_snippet="def health(): pass")
    EvidenceCollector.add_evidence(job_id, ev)
    
    req = SubmissionRequest(doc_id="doc-106", job_id=job_id, submitted_by="Lâm Gia Huy", evidences=[ev])
    sub = SubmissionWorkflow.create_submission(req)
    
    assert sub.doc_id == "doc-106"
    assert sub.status == "submitted"
    assert len(sub.evidences) == 1
