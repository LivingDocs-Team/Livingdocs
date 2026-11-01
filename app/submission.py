import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from app.evidence_models import GroundingEvidence, GenerationStatus, DocumentationSubmission
from app.models import FileAnalysis

STORAGE_FILE = "data_store.json"

class PersistentStore:
    """Lưu trữ dữ liệu ra file JSON để đảm bảo dữ liệu không bị mất khi Restart Service."""
    
    @staticmethod
    def _load() -> dict:
        if not os.path.exists(STORAGE_FILE):
            return {"statuses": {}, "submissions": {}, "evidences": {}}
        try:
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"statuses": {}, "submissions": {}, "evidences": {}}

    @staticmethod
    def _save(data: dict):
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def get_status(cls, doc_id: str) -> Optional[dict]:
        db = cls._load()
        return db["statuses"].get(doc_id)

    @classmethod
    def save_status(cls, doc_id: str, status_data: dict):
        db = cls._load()
        db["statuses"][doc_id] = status_data
        cls._save(db)

    @classmethod
    def get_evidences(cls, doc_id: str) -> List[dict]:
        db = cls._load()
        return db["evidences"].get(doc_id, [])

    @classmethod
    def save_evidences(cls, doc_id: str, evidences_data: List[dict]):
        db = cls._load()
        db["evidences"][doc_id] = evidences_data
        cls._save(db)

    @classmethod
    def get_submission(cls, doc_id: str) -> Optional[dict]:
        db = cls._load()
        return db["submissions"].get(doc_id)

    @classmethod
    def save_submission(cls, doc_id: str, sub_data: dict):
        db = cls._load()
        db["submissions"][doc_id] = sub_data
        cls._save(db)


class EvidenceCollector:
    @staticmethod
    def extract_from_analysis(document_id: str, analysis_files: List[FileAnalysis], commit_hash: str) -> List[GroundingEvidence]:
        evidences = []
        for file in analysis_files:
            for func in file.functions:
                # 🔴 Yêu cầu 2 của Leader: Chỉ trích xuất từ source thực tế. Nếu không có source, KHÔNG tạo chuỗi mô tả thế chỗ!
                if not func.source or not func.source.strip():
                    continue

                evidence = GroundingEvidence(
                    evidence_id=f"evi-{uuid.uuid4().hex[:8]}",
                    file_path=file.path,             # Chuẩn contract gốc
                    start_line=func.lineno,         # Chuẩn contract gốc
                    end_line=func.end_lineno,       # Chuẩn contract gốc
                    code_snippet=func.source,        # Mã nguồn thực tế
                    commit_hash=commit_hash
                )
                evidences.append(evidence)

        PersistentStore.save_evidences(document_id, [e.model_dump() for e in evidences])
        return evidences

    @staticmethod
    def get_evidences(document_id: str) -> List[GroundingEvidence]:
        data = PersistentStore.get_evidences(document_id)
        return [GroundingEvidence(**item) for item in data]


class StatusTracker:
    @staticmethod
    def update_status(document_id: str, progress: int, status_str: str = "processing", step: str = "") -> GenerationStatus:
        status_obj = GenerationStatus(
            document_id=document_id,
            status=status_str,
            progress_percentage=progress,
            current_step=step,
            updated_at=datetime.utcnow()
        )
        PersistentStore.save_status(document_id, status_obj.model_dump())
        return status_obj

    @staticmethod
    def get_status(document_id: str) -> Optional[GenerationStatus]:
        # 🔴 Yêu cầu 3 & 4 của Leader: Không tồn tại job -> Trả về None (để API bắn 404)
        data = PersistentStore.get_status(document_id)
        if not data:
            return None
        return GenerationStatus(**data)


class SubmissionWorkflow:
    @staticmethod
    def submit_documentation(document_id: str, submitted_by: str) -> DocumentationSubmission:
        status = StatusTracker.get_status(document_id)
        if not status:
            raise KeyError("Document generation job not found")  # Map 404
        if status.status != "completed" or status.progress_percentage < 100:
            raise ValueError("Cannot submit document while generation is in progress")  # Map 400

        existing_sub = PersistentStore.get_submission(document_id)
        if existing_sub:
            raise AttributeError("Document is locked and already submitted")  # Map 409

        evidences = EvidenceCollector.get_evidences(document_id)
        if not evidences:
            raise RuntimeError("Missing required source code grounding evidence")  # Map 422

        submission = DocumentationSubmission(
            submission_id=f"sub-{uuid.uuid4().hex[:8]}",
            document_id=document_id,
            submitted_by=submitted_by,
            status="submitted",
            submitted_at=datetime.utcnow(),
            evidence_ids=[e.evidence_id for e in evidences]
        )
        PersistentStore.save_submission(document_id, submission.model_dump())
        return submission

    @staticmethod
    def get_submission(document_id: str) -> Optional[DocumentationSubmission]:
        data = PersistentStore.get_submission(document_id)
        if not data:
            return None
        return DocumentationSubmission(**data)
