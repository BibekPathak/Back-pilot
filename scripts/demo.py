#!/usr/bin/env python3
"""BackPilot demo: run the agent against the legacy portal and print results.

Usage:
    # With the full Docker stack running:
    python scripts/demo.py

    # With a specific failure mode:
    python scripts/demo.py --failure-mode CAPTCHA

    # With the OpenAI planner:
    python scripts/demo.py --planner openai
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))
sys.path.insert(0, str(_REPO_ROOT))

from app.agents.loop import AgentLoop  # noqa: E402
from app.agents.planner import MockPlanner, OpenAIPlanner  # noqa: E402
from app.browser.session import launch_session  # noqa: E402
from app.config import settings  # noqa: E402

# Color codes for terminal output.
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"


def print_header(text: str) -> None:
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}  {text}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")


def print_event(ev, index: int) -> None:
    kind_colors = {
        "action": GREEN,
        "observation": CYAN,
        "recovery": YELLOW,
        "state_change": BLUE,
        "error": RED,
        "planner_decision": CYAN,
    }
    color = kind_colors.get(ev.kind, "")
    action_str = f" → {ev.action}" if ev.action else ""
    target_str = f"({ev.target})" if ev.target else ""
    result_str = f" [{ev.result}]" if ev.result else ""
    detail_str = f" — {ev.detail[:80]}" if ev.detail else ""
    duration_str = f" ({ev.duration_ms}ms)" if ev.duration_ms else ""

    print(
        f"  {color}{ev.seq:3d} {ev.kind:20s}{action_str} {target_str}"
        f"{result_str}{duration_str}{RESET}{detail_str}"
    )


async def run_demo(failure_mode: str, planner_type: str, task: str, max_steps: int):
    """Run the demo."""
    print_header("BackPilot Demo")

    # Configure failure mode.
    if failure_mode != "NORMAL":
        os.environ["PORTAL_FAILURE_MODE"] = failure_mode
        print(f"  {YELLOW}Failure mode: {failure_mode}{RESET}")
    else:
        os.environ.pop("PORTAL_FAILURE_MODE", None)
        print(f"  {GREEN}Failure mode: NORMAL (no injection){RESET}")

    # Select planner.
    if planner_type == "openai" and settings.openai_api_key:
        planner = OpenAIPlanner()
        print(f"  Planner: {CYAN}OpenAI ({settings.openai_model}){RESET}")
    else:
        planner = MockPlanner()
        print(f"  Planner: {CYAN}MockPlanner (deterministic){RESET}")

    print(f"  Task: {task[:80]}...")
    print(f"  Max steps: {max_steps}")
    print()

    # Launch browser session.
    print(f"  {YELLOW}Launching browser...{RESET}")
    session = await launch_session(
        screenshot_dir=str(_REPO_ROOT / "screenshots" / "demo"),
        headless=True,
        allowed_domains=["localhost", "127.0.0.1", "legacy-portal"],
    )

    try:
        # Create and run the agent loop.
        loop = AgentLoop(
            executor=session.executor,
            planner=planner,
            task=task,
            max_steps=max_steps,
            max_retries=3,
        )

        print(f"  {YELLOW}Agent running...{RESET}\n")
        t0 = time.monotonic()
        result = await loop.run()
        dt = time.monotonic() - t0

        # Print results.
        print_header("Results")

        state_color = GREEN if result.state == "SUCCESS" else RED
        if result.state == "HUMAN_INTERVENTION":
            state_color = YELLOW

        print(f"  Final state: {state_color}{result.state}{RESET}")
        print(f"  Duration: {result.duration_ms}ms (wall: {dt:.1f}s)")
        print(f"  Total events: {len(result.events)}")

        # Print timeline.
        print_header("Event Timeline")
        for i, ev in enumerate(result.events):
            print_event(ev, i)

        # Print summary.
        print_header("Summary")
        actions = [e for e in result.events if e.kind == "action"]
        recoveries = [e for e in result.events if e.kind == "recovery"]
        errors = [e for e in result.events if e.kind == "error"]
        human = [e for e in result.events if e.action == "request_human"]

        print(f"  Actions executed: {len(actions)}")
        print(f"  Recovery attempts: {len(recoveries)}")
        print(f"  Errors: {len(errors)}")
        print(f"  Human interventions requested: {len(human)}")

        if result.state == "SUCCESS":
            print(f"\n  {GREEN}Demo completed successfully!{RESET}")
        elif result.state == "HUMAN_INTERVENTION":
            print(f"\n  {YELLOW}Agent escalated to human intervention (expected for CAPTCHA).{RESET}")
        else:
            print(f"\n  {RED}Demo did not reach SUCCESS state.{RESET}")

        print(f"\n  Dashboard: {settings.dashboard_base_url}")
        print(f"  Screenshots: {_REPO_ROOT / 'screenshots' / 'demo'}")

        return 0 if result.state in ("SUCCESS", "HUMAN_INTERVENTION") else 1

    finally:
        await session.close()


def main():
    parser = argparse.ArgumentParser(description="BackPilot demo runner")
    parser.add_argument(
        "--failure-mode", "-f",
        default="NORMAL",
        choices=["NORMAL", "SELECTOR_CHANGE", "SLOW_NETWORK", "MISSING_ELEMENT",
                 "UNEXPECTED_MODAL", "SESSION_EXPIRED", "UPLOAD_FAILURE", "CAPTCHA"],
        help="Failure mode to inject (default: NORMAL)",
    )
    parser.add_argument(
        "--planner", "-p",
        default="mock",
        choices=["mock", "openai"],
        help="Planner to use (default: mock)",
    )
    parser.add_argument(
        "--task", "-t",
        default="Log in to the ACME ERP portal, fill in invoice INV-29381 for vendor ACME Corp with amount 1250.00, upload the invoice PDF, and submit.",
        help="Task description",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=50,
        help="Maximum agent steps (default: 50)",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(run_demo(args.failure_mode, args.planner, args.task, args.max_steps)))


if __name__ == "__main__":
    main()
