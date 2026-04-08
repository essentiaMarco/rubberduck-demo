"""Routes for browsing and viewing analysis sessions."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

SESSIONS_DIR = Path("data/sessions")


@router.get("/", response_class=HTMLResponse)
async def list_sessions(request: Request):
    """List all analyzed sessions."""
    files = sorted(SESSIONS_DIR.glob("*.json"), reverse=True) if SESSIONS_DIR.exists() else []
    sessions = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            sessions.append({
                "id": f.stem,
                "file": f.name,
                "tester": data.get("tester", {}).get("name") or data.get("tester_name") or "Unknown",
                "date": data.get("tester", {}).get("date") or data.get("date", ""),
                "milestone": data.get("milestone", "M1"),
                "trust_score": data.get("observations", {}).get("trust", {}).get("trust_score"),
                "m3_rating": data.get("m3_candidacy", {}).get("rating"),
                "ide": data.get("tester", {}).get("ide", ""),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    return templates.TemplateResponse(request, "sessions_list.html", {
        "sessions": sessions,
    })


@router.get("/{session_id}", response_class=HTMLResponse)
async def view_session(request: Request, session_id: str):
    """View a single session's full analysis."""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return HTMLResponse("<h1>Session not found</h1>", status_code=404)

    data = json.loads(session_file.read_text())
    return templates.TemplateResponse(request, "session.html", {
        "session": data,
        "session_id": session_id,
    })


@router.get("/{session_id}/json")
async def session_json(session_id: str):
    """Return raw session JSON."""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(json.loads(session_file.read_text()))
