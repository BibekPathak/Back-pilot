"""Core data models: agent runs and the events timeline.

A ``Run`` is one end-to-end agent execution. Every state transition, action,
observation, recovery attempt, screenshot, HITL event, and final result is
recorded as an ``Event`` child row so the whole run is queryable and replayable.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def gen_id() -> str:
    return f"run_{uuid.uuid4().hex[:10]}"


class RunState(str):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    NAVIGATING = "NAVIGATING"
    FILLING_FORM = "FILLING_FORM"
    UPLOADING = "UPLOADING"
    VALIDATING = "VALIDATING"
    SUBMITTING = "SUBMITTING"
    SUCCESS = "SUCCESS"
    ACTION_FAILED = "ACTION_FAILED"
    RECOVERING = "RECOVERING"
    HUMAN_INTERVENTION = "HUMAN_INTERVENTION"
    FAILED = "FAILED"


#: Deterministic states owned by the state machine (the LLM does not drive these).
STATE_MACHINE_STATES = frozenset(
    {
        RunState.CREATED,
        RunState.PLANNING,
        RunState.NAVIGATING,
        RunState.FILLING_FORM,
        RunState.UPLOADING,
        RunState.VALIDATING,
        RunState.SUBMITTING,
        RunState.SUCCESS,
        RunState.ACTION_FAILED,
        RunState.RECOVERING,
        RunState.HUMAN_INTERVENTION,
        RunState.FAILED,
    }
)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=gen_id)
    scenario: Mapped[str] = mapped_column(String(40), default="baseline")
    task: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(40), default=RunState.CREATED)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[str | None] = mapped_column(String(40), nullable=True)

    events: Mapped[list["Event"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Event.seq"
    )
    interventions: Mapped[list["Intervention"]] = relationship(  # type: ignore[name-defined]
        back_populates="run", cascade="all, delete-orphan"
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), default="info")
    action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    result: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    run: Mapped["Run"] = relationship(back_populates="events")
