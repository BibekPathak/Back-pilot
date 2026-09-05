"""Evaluator runner: orchestrates scenario evaluation.

Runs each scenario against the agent (MockPlanner by default) and scores
the results.  Can be invoked via ``python -m evaluator`` or
``make evaluate``.

Usage::

    # Run all scenarios with MockPlanner (no API key needed)
    python -m evaluator

    # Run a specific scenario
    python -m evaluator --scenario happy_path

    # Run with OpenAI planner (requires API key)
    python -m evaluator --planner openai
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure the repo root is on sys.path so we can import app.* and evaluator.*
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))
sys.path.insert(0, str(_REPO_ROOT))

from app.agents.loop import AgentLoop  # noqa: E402
from app.agents.planner import MockPlanner, OpenAIPlanner, create_planner  # noqa: E402
from app.browser.session import launch_session  # noqa: E402
from app.config import settings  # noqa: E402
from evaluator.scoring import (  # noqa: E402
    ScenarioSpec,
    ScoreCard,
    load_all_scenarios,
    load_scenario,
    score_run,
    summarize,
)

logger = logging.getLogger(__name__)


async def run_scenario(
    spec: ScenarioSpec,
    portal_url: str,
    planner=None,
    headless: bool = True,
) -> tuple[ScoreCard, dict]:
    """Run a single scenario and return (ScoreCard, raw_events)."""

    # Set the portal failure mode via environment.
    os.environ["PORTAL_FAILURE_MODE"] = spec.portal_failure_mode
    if spec.portal_failure_sequence:
        os.environ["PORTAL_FAILURE_SEQUENCE"] = ",".join(spec.portal_failure_sequence)

    session = await launch_session(
        screenshot_dir=str(_REPO_ROOT / "screenshots" / spec.name),
        headless=headless,
        allowed_domains=["localhost", "127.0.0.1", "legacy-portal"],
    )

    try:
        agent_planner = planner or create_planner()
        loop = AgentLoop(
            executor=session.executor,
            planner=agent_planner,
            task=spec.task,
            max_steps=50,
            max_retries=3,
        )
        result = await loop.run()
        card = score_run(result, spec)
        return card, {"events": [e.to_dict() for e in result.events]}
    finally:
        await session.close()


async def run_all(
    scenarios: Optional[list[str]] = None,
    portal_url: str = "http://localhost:8081",
    planner=None,
    headless: bool = True,
) -> dict:
    """Run all (or specified) scenarios and return the summary report."""

    if scenarios:
        specs = [load_scenario(s) for s in scenarios]
    else:
        specs = load_all_scenarios()

    cards = []
    raw_results = {}

    for spec in specs:
        logger.info("Running scenario: %s", spec.name)
        t0 = time.monotonic()
        try:
            card, raw = await run_scenario(
                spec, portal_url, planner=planner, headless=headless
            )
            dt = time.monotonic() - t0
            logger.info(
                "  %s: %s (score=%.2f, grade=%s, %.1fs)",
                spec.name,
                "PASS" if card.passed else "FAIL",
                card.overall_score,
                card.grade,
                dt,
            )
        except Exception as exc:
            logger.error("  %s: ERROR — %s", spec.name, exc)
            card = ScoreCard(
                scenario=spec.name,
                passed=False,
                details={"error": str(exc)},
            )
            raw = {"error": str(exc)}
        cards.append(card)
        raw_results[spec.name] = raw

    summary = summarize(cards)
    summary["raw"] = raw_results
    return summary


def main():
    parser = argparse.ArgumentParser(description="BackPilot evaluator runner")
    parser.add_argument(
        "--scenario", "-s",
        help="Run a specific scenario (default: all)",
    )
    parser.add_argument(
        "--planner", "-p",
        choices=["mock", "openai"],
        default="mock",
        help="Planner to use (default: mock)",
    )
    parser.add_argument(
        "--portal-url",
        default="http://localhost:8081",
        help="Legacy portal URL",
    )
    parser.add_argument(
        "--output", "-o",
        help="Write JSON report to file",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (visible)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.planner == "openai" and not settings.openai_api_key:
        logger.error("OpenAI planner requested but no API key configured.")
        sys.exit(1)

    planner = None
    if args.planner == "openai":
        planner = OpenAIPlanner()

    scenarios = [args.scenario] if args.scenario else None

    summary = asyncio.run(
        run_all(
            scenarios=scenarios,
            portal_url=args.portal_url,
            planner=planner,
            headless=not args.headed,
        )
    )

    # Print summary.
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total: {summary['total']}  Passed: {summary['passed']}  "
          f"Failed: {summary['failed']}  Pass rate: {summary.get('pass_rate', 0)}%")
    print(f"Average score: {summary['avg_score']:.3f}")
    print(f"Grades: {summary['grades']}")
    print("-" * 60)
    for ps in summary.get("per_scenario", []):
        status = "PASS" if ps["passed"] else "FAIL"
        print(f"  [{status}] {ps['scenario']}: "
              f"score={ps['overall_score']:.2f} grade={ps['grade']}")
    print("=" * 60)

    # Write output if requested.
    if args.output:
        Path(args.output).write_text(json.dumps(summary, indent=2))
        logger.info("Report written to %s", args.output)

    sys.exit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
