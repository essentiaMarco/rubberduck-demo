"""API routes for full-text search."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from rubberduck.db.sqlite import get_db
from rubberduck.jobs.manager import job_manager
from rubberduck.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchSuggestion,
)
from rubberduck.search.service import search, suggest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("/", response_model=SearchResponse)
def full_text_search(body: SearchRequest, db: Session = Depends(get_db)):
    """Run a ranked full-text search across all indexed evidence."""
    result = search(
        db,
        query=body.query,
        file_types=body.file_types,
        source_ids=body.source_ids,
        page=body.page,
        page_size=body.page_size,
    )
    return SearchResponse(
        results=[SearchResult(**r) for r in result["results"]],
        total=result["total"],
        query=result["query"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/suggest", response_model=list[SearchSuggestion])
def autocomplete(
    prefix: str = Query(..., min_length=1, description="Prefix to autocomplete"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Return autocomplete suggestions for a search prefix."""
    suggestions = suggest(db, prefix=prefix, limit=limit)
    return [SearchSuggestion(**s) for s in suggestions]


@router.post("/reindex")
def trigger_reindex(db: Session = Depends(get_db)):
    """Rebuild the full-text search index from all parsed files."""
    from rubberduck.search.indexer import bulk_reindex

    def _reindex_job(thread_db: Session, job_id: str) -> dict:
        return bulk_reindex(thread_db)

    job_id = job_manager.submit(db, "search_reindex", _reindex_job, params={})
    return {"job_id": job_id, "message": "Search reindex started"}
