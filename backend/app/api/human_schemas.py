"""Human-takeover API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class InterventionRequest(BaseModel):
    """Payload for requesting human intervention."""

    reason: str
    assigned_to: Optional[str] = None


class InterventionOut(BaseModel):
    """Intervention record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    reason: str
    status: str
    assigned_to: Optional[str] = None
    resolution_note: Optional[str] = None
    requested_at: datetime
    notified_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class InterventionResolve(BaseModel):
    """Payload for resolving an intervention."""

    resolution_note: str
    status: str = "resolved"  # resolved | timed_out


class ResumeRequest(BaseModel):
    """Payload for resuming a run after human intervention."""

    action: str = "continue"  # continue | abort
    note: Optional[str] = None
