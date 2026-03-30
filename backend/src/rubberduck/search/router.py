"""API routes for full-text search."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from rubberduck.db.sqlite import get_db
from rubberduck.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchSuggestion,
)
from rubberduck.search.service import search, suggest

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
