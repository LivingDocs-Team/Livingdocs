"""Evidence & submission storage (PR #108, fixed in LD-402).

PR #108 kept evidences and submissions in two module dictionaries: a restart of the service
lost every evidence and submission (submit -> 404, reuse an evidence -> 400) and nothing could
be read back. This store keeps them in a JSON file so they survive a restart:

    SUBMISSIONS_FILE   path of the file (default data/submissions.json; in Docker Compose
                       /app/data/submissions.json on the `analyzer-data` volume).
                       Set it to an empty value to keep everything in memory (tests).

Writes are atomic (temporary file + rename), so a crash never leaves a half-written file. A file
that cannot be read is moved aside (`*.corrupt-<time>.json`) and the service starts empty
instead of failing, like the documents of the AI service.
"""
import json
import logging
import os
import pathlib
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models import (EvidenceCreate, EvidenceResponse, SubmissionCreate, SubmissionRecord,
                        SubmissionResponse, SubmissionStatus)

log = logging.getLogger(__name__)
DEFAULT_FILE = "data/submissions.json"


class SubmissionError(Exception):
    """An operation that cannot be done; `status` is the HTTP status to return."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SubmissionStore:
    def __init__(self, path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self.path = pathlib.Path(path) if path else None
        self._evidences: Dict[str, EvidenceResponse] = {}
        self._submissions: Dict[str, SubmissionRecord] = {}
        self._load()

    # ---------- persistence ----------

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            evidences = {e["id"]: EvidenceResponse.model_validate(e) for e in raw.get("evidences", [])}
            submissions = {s["id"]: SubmissionRecord.model_validate(s) for s in raw.get("submissions", [])}
        except Exception as exc:  # corrupt file: keep it for inspection, start clean
            backup = self.path.with_suffix(f".corrupt-{_now():%Y%m%d%H%M%S}.json")
            self.path.rename(backup)
            log.error("Could not read %s (%s); moved it to %s", self.path, exc, backup.name)
            return
        self._evidences, self._submissions = evidences, submissions

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"evidences": [e.model_dump(mode="json") for e in self._evidences.values()],
                "submissions": [s.model_dump(mode="json") for s in self._submissions.values()]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---------- evidences ----------

    def add_evidence(self, payload: EvidenceCreate) -> EvidenceResponse:
        with self._lock:
            evidence = EvidenceResponse(id=f"ev-{uuid.uuid4().hex[:12]}", created_at=_now(),
                                        **payload.model_dump())
            self._evidences[evidence.id] = evidence
            self._save()
            return evidence

    def evidence(self, evidence_id: str) -> EvidenceResponse:
        found = self._evidences.get(evidence_id)
        if found is None:
            raise SubmissionError(404, "Evidence không tồn tại")
        return found

    # ---------- submissions ----------

    def _response(self, record: SubmissionRecord) -> SubmissionResponse:
        evidences = [self._evidences[i] for i in record.evidence_ids if i in self._evidences]
        return SubmissionResponse(**record.model_dump(exclude={"evidence_ids"}), evidences=evidences)

    def add_submission(self, payload: SubmissionCreate) -> SubmissionResponse:
        with self._lock:
            ids = list(dict.fromkeys(payload.evidence_ids))
            missing = [i for i in ids if i not in self._evidences]
            if missing:
                raise SubmissionError(400, f"Các Evidence ID sau không tồn tại: {missing}")
            record = SubmissionRecord(id=f"sub-{uuid.uuid4().hex[:12]}", task_id=payload.task_id,
                                      title=payload.title, notes=payload.notes,
                                      status=SubmissionStatus.DRAFT, evidence_ids=ids,
                                      created_at=_now())
            self._submissions[record.id] = record
            self._save()
            return self._response(record)

    def submission(self, submission_id: str) -> SubmissionResponse:
        record = self._submissions.get(submission_id)
        if record is None:
            raise SubmissionError(404, "Submission không tồn tại")
        return self._response(record)

    def submissions(self, task_id: Optional[str] = None) -> List[SubmissionResponse]:
        rows = [r for r in self._submissions.values() if task_id is None or r.task_id == task_id]
        return [self._response(r) for r in sorted(rows, key=lambda r: r.created_at, reverse=True)]

    def submit(self, submission_id: str) -> SubmissionResponse:
        with self._lock:
            record = self._submissions.get(submission_id)
            if record is None:
                raise SubmissionError(404, "Submission không tồn tại")
            if record.status == SubmissionStatus.SUBMITTED:
                return self._response(record)          # retry of the same request: no change
            if record.status != SubmissionStatus.DRAFT:
                raise SubmissionError(409, f"Submission đang ở trạng thái {record.status.value}, không thể submit")
            if not record.evidence_ids:
                raise SubmissionError(400, "Cần ít nhất 1 evidence để thực hiện submit")
            record.status = SubmissionStatus.SUBMITTED
            record.submitted_at = _now()
            self._save()
            return self._response(record)


submissions = SubmissionStore(os.getenv("SUBMISSIONS_FILE", DEFAULT_FILE) or None)
