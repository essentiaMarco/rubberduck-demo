"""API routes for OSINT research."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from rubberduck.db.models import ResearchCapture, ResearchPlan
from rubberduck.db.sqlite import get_db

router = APIRouter(prefix="/api/osint", tags=["osint"])


@router.post("/plans")
def create_plan(
    case_id: str,
    title: str,
    description: str | None = None,
    targets: str | None = None,
    rationale: str | None = None,
    db: Session = Depends(get_db),
):
    plan = ResearchPlan(
        case_id=case_id,
        title=title,
        description=description,
        targets=targets,
        rationale=rationale,
        status="draft",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, "status": plan.status}


@router.get("/plans")
def list_plans(case_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ResearchPlan)
    if case_id:
        query = query.filter(ResearchPlan.case_id == case_id)
    return [
        {"id": p.id, "title": p.title, "status": p.status, "created_at": str(p.created_at)}
        for p in query.order_by(ResearchPlan.created_at.desc()).all()
    ]


@router.patch("/plans/{plan_id}/approve")
def approve_plan(plan_id: str, db: Session = Depends(get_db)):
    plan = db.query(ResearchPlan).get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    from datetime import datetime, timezone
    plan.status = "approved"
    plan.approved_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": plan.id, "status": "approved"}


@router.get("/captures")
def list_captures(plan_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ResearchCapture)
    if plan_id:
        query = query.filter(ResearchCapture.plan_id == plan_id)
    return [
        {
            "id": c.id, "url": c.url, "page_title": c.page_title,
            "capture_timestamp": str(c.capture_timestamp), "http_status": c.http_status,
        }
        for c in query.order_by(ResearchCapture.capture_timestamp.desc()).all()
    ]
