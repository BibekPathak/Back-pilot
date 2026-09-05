"""Runs API: create, list, retrieve runs and their event timeline."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import EventOut, RunCreate, RunListOut, RunOut
from app.db.session import get_db
from app.models.run import Event, Run

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunOut, status_code=201)
def create_run(payload: RunCreate, db: Session = Depends(get_db)):
    run = Run(scenario=payload.scenario, task=payload.task)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("", response_model=RunListOut)
def list_runs(db: Session = Depends(get_db), limit: int = 100):
    runs = db.execute(
        select(Run).order_by(Run.started_at.desc()).limit(min(limit, 500))
    ).scalars().all()
    total = db.execute(select(func.count(Run.id))).scalar_one()
    return RunListOut(runs=runs, total=total)


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/events", response_model=list[EventOut])
def list_events(run_id: str, db: Session = Depends(get_db)):
    if not db.get(Run, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    events = db.execute(
        select(Event).where(Event.run_id == run_id).order_by(Event.seq)
    ).scalars().all()
    return events
