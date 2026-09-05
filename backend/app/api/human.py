"""Human-takeover API: request, list, resolve interventions; resume runs."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.human_schemas import (
    InterventionOut,
    InterventionRequest,
    InterventionResolve,
    ResumeRequest,
)
from app.db.session import get_db
from app.models.intervention import Intervention
from app.models.run import Run, RunState

router = APIRouter(prefix="/runs", tags=["human-takeover"])


# ------------------------------------------------------------------ request
@router.post("/{run_id}/intervention", response_model=InterventionOut, status_code=201)
def request_intervention(
    run_id: str,
    payload: InterventionRequest,
    db: Session = Depends(get_db),
):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    intervention = Intervention(
        run_id=run_id,
        reason=payload.reason,
        assigned_to=payload.assigned_to,
        status="pending",
    )
    db.add(intervention)

    # Transition run to HUMAN_INTERVENTION if not already there.
    if run.state != RunState.HUMAN_INTERVENTION:
        run.state = RunState.HUMAN_INTERVENTION

    db.commit()
    db.refresh(intervention)
    return intervention


# ------------------------------------------------------------------ list
@router.get("/{run_id}/interventions", response_model=list[InterventionOut])
def list_interventions(run_id: str, db: Session = Depends(get_db)):
    if not db.get(Run, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    from sqlalchemy import select
    stmt = (
        select(Intervention)
        .where(Intervention.run_id == run_id)
        .order_by(Intervention.requested_at.desc())
    )
    return db.execute(stmt).scalars().all()


# ------------------------------------------------------------------ resolve
@router.put(
    "/{run_id}/intervention/{intervention_id}",
    response_model=InterventionOut,
)
def resolve_intervention(
    run_id: str,
    intervention_id: int,
    payload: InterventionResolve,
    db: Session = Depends(get_db),
):
    intervention = db.get(Intervention, intervention_id)
    if not intervention or intervention.run_id != run_id:
        raise HTTPException(status_code=404, detail="Intervention not found")

    intervention.status = payload.status
    intervention.resolution_note = payload.resolution_note
    intervention.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(intervention)
    return intervention


# ------------------------------------------------------------------ resume
@router.post("/{run_id}/resume", response_model=InterventionOut)
def resume_run(
    run_id: str,
    payload: ResumeRequest,
    db: Session = Depends(get_db),
):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.state != RunState.HUMAN_INTERVENTION:
        raise HTTPException(
            status_code=400,
            detail=f"Run is in state '{run.state}', not HUMAN_INTERVENTION",
        )

    if payload.action == "abort":
        run.state = RunState.FAILED
        run.finished_at = datetime.now(timezone.utc)
        run.result = "aborted_by_human"
        db.commit()
        # Return the latest intervention.
        from sqlalchemy import select
        stmt = (
            select(Intervention)
            .where(Intervention.run_id == run_id)
            .order_by(Intervention.requested_at.desc())
            .limit(1)
        )
        intervention = db.execute(stmt).scalar_one_or_none()
        if intervention:
            intervention.status = "resolved"
            intervention.resolution_note = payload.note or "aborted by human"
            intervention.resolved_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(intervention)
            return intervention
        # No intervention found — create a synthetic one.
        iv = Intervention(
            run_id=run_id,
            reason="aborted by human",
            status="resolved",
            resolution_note=payload.note or "aborted by human",
            resolved_at=datetime.now(timezone.utc),
        )
        db.add(iv)
        db.commit()
        db.refresh(iv)
        return iv

    # action == "continue"
    run.state = RunState.RECOVERING
    db.commit()

    from sqlalchemy import select
    stmt = (
        select(Intervention)
        .where(Intervention.run_id == run_id)
        .order_by(Intervention.requested_at.desc())
        .limit(1)
    )
    intervention = db.execute(stmt).scalar_one_or_none()
    if not intervention:
        raise HTTPException(status_code=404, detail="No intervention found to resume from")
    intervention.status = "resolved"
    intervention.resolution_note = payload.note or "resolved"
    intervention.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(intervention)
    return intervention
