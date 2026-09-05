"""Async agent tasks (Celery).

``run_demo`` / ``run_scenario`` are wired in later milestones once the agent
planner + browser executor land. Importing this module registers the tasks.
"""

from __future__ import annotations

from app.workers import celery_app


@celery_app.task(name="agent.run_demo")
def run_demo(run_id: str) -> dict:
    """Canonical demo workflow (filled in when the agent is implemented)."""
    return {"run_id": run_id, "status": "pending_agent_milestone"}
