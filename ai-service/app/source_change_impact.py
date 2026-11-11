"""LD-122 Affected documentation of a source change (LD-116).

GitHub Integration sends the files and code entities that a commit or Pull Request changed
(LD-116) and the ids of the repository's saved documents; the answer says which parts of those
documents may now be outdated. The matching rules are the ones of LD-148 (app/drift_affected.py).

LD-123  map the change to the documentation: every part generated from a changed file, and every
        part that names a changed entity, endpoint or file path (with the lines where it does);
LD-124  affected documents: those parts, per document and section;
LD-125  documentation dependencies: a part is `direct` when it documents a changed file itself,
        `dependent` when it documents other code but refers to the changed code.
"""
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .drift_affected import collect_docs, find_affected
from .drift_models import (AffectedDocument, ChangeStatus, EntityChange, EntityChangeType,
                           FileChangeSummary, PullRequestAnalysis)

FILE_STATUS = {"ADDED": ChangeStatus.added, "MODIFIED": ChangeStatus.modified,
               "REMOVED": ChangeStatus.removed, "RENAMED": ChangeStatus.renamed}
# LD-116 tells only that an entity was added, removed or modified, not how it was modified
ENTITY_CHANGE = {"ADDED": EntityChangeType.added, "MODIFIED": EntityChangeType.behavior_changed,
                 "REMOVED": EntityChangeType.removed}


def _upper(value):
    return value.upper() if isinstance(value, str) else value


class ChangedEntity(BaseModel):
    """Code entity of LD-116: `kind` CLASS | METHOD | FUNCTION | ENDPOINT | ..., `name` such as
    `Class.method`, `function` or `GET /path`."""
    kind: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=500)
    change: Literal["ADDED", "MODIFIED", "REMOVED"]

    @field_validator("change", mode="before")
    @classmethod
    def _case(cls, value):
        return _upper(value)


class ChangedFile(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    previous_path: Optional[str] = Field(default=None, max_length=1000)
    change: Literal["ADDED", "MODIFIED", "REMOVED", "RENAMED"]
    language: Optional[str] = Field(default=None, max_length=40)
    entities: List[ChangedEntity] = Field(default_factory=list, max_length=2000)

    @field_validator("change", mode="before")
    @classmethod
    def _case(cls, value):
        return _upper(value)


class AffectedDocumentsRequest(BaseModel):
    repository: Optional[str] = Field(default=None, max_length=300)   # "owner/name"
    files: List[ChangedFile] = Field(min_length=1, max_length=1000)   # GitHub lists up to 1000 PR files
    document_ids: List[str] = Field(default_factory=list, max_length=1000)
    """Saved documents to check. No default to "every document": the caller sends only the
    repository's own documents, so another repository's documentation is never read."""


class Dependency(str, Enum):
    direct = "direct"           # the part was generated from a changed file
    dependent = "dependent"     # the part documents other code but refers to the changed code


class AffectedPart(AffectedDocument):
    dependency: Dependency


class AffectedDocumentsResult(BaseModel):
    documents: List[AffectedPart] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


def _analysis(req: AffectedDocumentsRequest) -> PullRequestAnalysis:
    files = [FileChangeSummary(
        path=f.path, status=FILE_STATUS[f.change], previous_path=f.previous_path,
        language=f.language,
        entity_changes=[EntityChange(path=f.path, previous_path=f.previous_path,
                                     kind=e.kind.lower(), name=e.name,
                                     change=ENTITY_CHANGE[e.change]) for e in f.entities])
        for f in req.files]
    # A commit has no Pull Request; find_affected reads only `files`.
    return PullRequestAnalysis.model_construct(repository=req.repository, files=files)


def find_for_source_change(req: AffectedDocumentsRequest, store) -> AffectedDocumentsResult:
    docs, warnings = collect_docs(store, req.document_ids, [])
    affected, _ = find_affected(_analysis(req), docs)
    changed = {p for f in req.files for p in (f.path, f.previous_path) if p}
    found = {(a.source, a.document_id, a.path) for a in affected}
    for doc in docs:  # LD-123: the part of a changed file is affected even when no entity is known
        if doc.documents_file in changed and doc.key() not in found:
            affected.append(AffectedDocument(
                source=doc.source, path=doc.path, document_id=doc.document_id, title=doc.title,
                version=doc.version, documents_file=doc.documents_file,
                reasons=[f"documents changed file {doc.documents_file}"]))
    parts = [AffectedPart(**a.model_dump(),
                          dependency=Dependency.direct if a.documents_file in changed
                          else Dependency.dependent)
             for a in affected]
    parts.sort(key=lambda p: (p.dependency != Dependency.direct, p.title or "", p.path))
    return AffectedDocumentsResult(documents=parts, warnings=warnings)
