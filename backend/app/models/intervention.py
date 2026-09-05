"""Intervention model: tracks human-takeover requests and resolutions.

When a run enters HUMAN_INTERVENTION state, an Intervention row is created
to track who was notified, what the human needs to do, and when it was
resolved.  The human-takeover API reads and writes these rows.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Intervention(Base):
    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | notified | resolved | timed_out
    assigned_to: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["Run"] = relationship(back_populates="interventions")  # type: ignore[name-defined]
