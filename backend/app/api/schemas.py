"""API schemas (Pydantic) for runs and events."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RunCreate(BaseModel):
    scenario: str = "baseline"
    task: str = ""


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scenario: str
    task: str
    state: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    result: Optional[str] = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    seq: int
    timestamp: datetime
    state: Optional[str] = None
    kind: str
    action: Optional[str] = None
    target: Optional[str] = None
    result: Optional[str] = None
    failure_reason: Optional[str] = None
    detail: Optional[str] = None
    duration_ms: Optional[int] = None
    screenshot_path: Optional[str] = None


class RunListOut(BaseModel):
    runs: list[RunOut]
    total: int = Field(..., description="Total run count")
