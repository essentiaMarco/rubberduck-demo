"""API routes for report generation."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports():
    return {"items": [], "message": "Report generation module — Phase 2"}
