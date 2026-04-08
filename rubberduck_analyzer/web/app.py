"""FastAPI application — serves API + Jinja2 templates."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from rubberduck_analyzer.web.routes import analysis, sessions, synthesis, context, jobs

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="RubberDuck Interview Analyzer", version="0.1.0")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include route modules
app.include_router(analysis.router, prefix="/analyze", tags=["analysis"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(synthesis.router, prefix="/synthesis", tags=["synthesis"])
app.include_router(context.router, prefix="/context", tags=["context"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/")
async def dashboard(request: Request):
    """Main dashboard — session overview and quick stats."""
    from rubberduck_analyzer.web.models import list_jobs
    import json

    # Load existing sessions
    sessions_dir = Path("data/sessions")
    session_files = sorted(sessions_dir.glob("*.json"), reverse=True) if sessions_dir.exists() else []
    session_list = []
    for f in session_files[:20]:
        try:
            data = json.loads(f.read_text())
            session_list.append({
                "file": f.name,
                "tester": data.get("tester", {}).get("name", "Unknown"),
                "date": data.get("tester", {}).get("date", ""),
                "milestone": data.get("milestone", "M1"),
                "trust_score": data.get("observations", {}).get("trust", {}).get("trust_score"),
                "m3_rating": data.get("m3_candidacy", {}).get("rating"),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    recent_jobs = list_jobs(limit=10)

    return templates.TemplateResponse(request, "dashboard.html", {
        "sessions": session_list,
        "jobs": recent_jobs,
        "session_count": len(session_files),
    })
