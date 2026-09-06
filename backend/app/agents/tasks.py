"""Async agent tasks (Celery).

``run_demo`` launches the agent against the legacy portal, persists events
to the database, and updates the run state.  Importing this module registers
the tasks with the Celery worker.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.workers import celery_app

logger = logging.getLogger(__name__)


def _run_agent_sync(run_id: str, task_desc: str, failure_mode: str = "NORMAL", max_steps: int = 50) -> dict:
    """Synchronous wrapper that runs the async agent loop."""
    import os
    os.environ["PORTAL_FAILURE_MODE"] = failure_mode

    from app.agents.loop import AgentLoop
    from app.agents.planner import create_planner
    from app.browser.session import launch_session
    from app.config import settings

    async def _run():
        session = await launch_session(
            screenshot_dir=f"/app/screenshots/{run_id}",
            headless=True,
            allowed_domains=["localhost", "127.0.0.1", "legacy-portal"],
        )
        try:
            planner = create_planner()
            loop = AgentLoop(
                executor=session.executor,
                planner=planner,
                task=task_desc,
                max_steps=max_steps,
                max_retries=3,
            )
            result = await loop.run()
            return {
                "state": result.state,
                "events": [e.to_dict() for e in result.events],
                "duration_ms": result.duration_ms,
            }
        finally:
            await session.close()

    return asyncio.run(_run())


@celery_app.task(name="agent.run_demo", bind=True, max_retries=1)
def run_demo(self, run_id: str, task: str = "", failure_mode: str = "NORMAL", max_steps: int = 50) -> dict:
    """Run the agent against the legacy portal for the given run.

    Updates the Run record in the database with the final state and persists
    all events.
    """
    from app.db.session import SessionLocal
    from app.models.run import Event, Run, RunState

    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run:
            logger.error("Run %s not found", run_id)
            return {"run_id": run_id, "status": "error", "message": "run not found"}

        # Update task if provided.
        if task:
            run.task = task
        run.state = RunState.PLANNING
        db.commit()

        task_desc = run.task or task or "Complete the invoice workflow"

        logger.info("Starting agent for run %s (task=%s, failure=%s)", run_id, task_desc[:50], failure_mode)

        # Run the agent.
        result = _run_agent_sync(run_id, task_desc, failure_mode, max_steps)

        # Persist events.
        for ev_data in result.get("events", []):
            event = Event(
                run_id=run_id,
                seq=ev_data.get("seq", 0),
                state=ev_data.get("state"),
                kind=ev_data.get("kind", "info"),
                action=ev_data.get("action"),
                target=ev_data.get("target"),
                result=ev_data.get("result"),
                failure_reason=ev_data.get("failure_reason"),
                detail=ev_data.get("detail"),
                duration_ms=ev_data.get("duration_ms"),
                screenshot_path=ev_data.get("screenshot_path"),
            )
            db.add(event)

        # Update run state.
        final_state = result.get("state", "FAILED")
        run.state = final_state
        run.finished_at = datetime.now(timezone.utc)
        if final_state == "SUCCESS":
            run.result = "success"
        elif final_state == "HUMAN_INTERVENTION":
            run.result = "human_intervention"
        else:
            run.result = "failed"
        db.commit()

        logger.info("Run %s completed: state=%s", run_id, final_state)
        return {
            "run_id": run_id,
            "status": "completed",
            "state": final_state,
            "events_count": len(result.get("events", [])),
        }

    except Exception as exc:
        logger.error("Run %s failed: %s", run_id, exc)
        # Try to mark the run as FAILED.
        try:
            run = db.get(Run, run_id)
            if run:
                run.state = RunState.FAILED
                run.finished_at = datetime.now(timezone.utc)
                run.result = f"error: {exc}"
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=10)
    finally:
        db.close()


@celery_app.task(name="agent.run_scenario")
def run_scenario(scenario: str, task: str = "", max_steps: int = 50) -> dict:
    """Create a run and execute it for a given scenario."""
    from app.db.session import SessionLocal
    from app.models.run import Run

    db = SessionLocal()
    try:
        run = Run(scenario=scenario, task=task or f"Execute {scenario} scenario")
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    finally:
        db.close()

    return run_demo.delay(run_id, task=task, failure_mode=scenario.upper(), max_steps=max_steps)
