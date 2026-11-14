"""HTTP API of documentation suggestions (LD-353)."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from . import suggestions as sg
from .suggestions import Suggestion, SuggestionBatch, UpdateSuggestionRequest, suggestion_store
from .versions import documents

router = APIRouter(tags=["suggestions"])


@router.post("/suggestions/updates", response_model=SuggestionBatch, status_code=201)
def create_update_suggestions(req: UpdateSuggestionRequest):
    """LD-353: proposed edits to the documentation (saved documents and Markdown files of the
    request) that describes the code changed by a Pull Request. Same body as /drift/context,
    plus `output_language` and `use_ai`. The batch is kept for review."""
    return sg.update_suggestions(req, documents, sg.get_client(req.use_ai))


@router.get("/suggestions", response_model=List[Suggestion])
def list_suggestions(batch_id: Optional[str] = Query(None, max_length=64),
                     status: Optional[sg.SuggestionStatus] = None,
                     document_id: Optional[str] = Query(None, max_length=64)):
    """Suggestions, newest batch first; filter by batch, status or saved document."""
    return suggestion_store.list(batch_id, status.value if status else None, document_id)


@router.get("/suggestions/batches/{batch_id}", response_model=SuggestionBatch)
def get_suggestion_batch(batch_id: str):
    batch = suggestion_store.batch(batch_id)
    if batch is None:
        raise HTTPException(404, "Suggestion batch not found")
    return batch


@router.get("/suggestions/{suggestion_id}", response_model=Suggestion)
def get_suggestion(suggestion_id: str):
    s = suggestion_store.get(suggestion_id)
    if s is None:
        raise HTTPException(404, "Suggestion not found")
    return s
