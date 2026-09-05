"""Dashboard placeholder API: basic run statistics."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.intervention import Intervention
from app.models.run import Run

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total_runs = db.execute(select(func.count(Run.id))).scalar_one()
    success = db.execute(
        select(func.count(Run.id)).where(Run.state == "SUCCESS")
    ).scalar_one()
    failed = db.execute(
        select(func.count(Run.id)).where(Run.state == "FAILED")
    ).scalar_one()
    human_intervention = db.execute(
        select(func.count(Run.id)).where(Run.state == "HUMAN_INTERVENTION")
    ).scalar_one()
    pending_interventions = db.execute(
        select(func.count(Intervention.id)).where(Intervention.status == "pending")
    ).scalar_one()
    return {
        "total_runs": total_runs,
        "success": success,
        "failed": failed,
        "human_intervention": human_intervention,
        "success_rate": round(success / total_runs * 100, 1) if total_runs else 0.0,
        "pending_interventions": pending_interventions,
    }


@router.get("/runs/active")
def get_active_runs(db: Session = Depends(get_db)):
    active_states = ["CREATED", "PLANNING", "NAVIGATING", "FILLING_FORM", "UPLOADING", "VALIDATING", "SUBMITTING", "HUMAN_INTERVENTION", "RECOVERING"]
    runs = db.execute(
        select(Run).where(Run.state.in_(active_states)).order_by(Run.started_at.desc())
    ).scalars().all()
    return {"runs": [{"id": r.id, "state": r.state, "task": r.task} for r in runs]}
