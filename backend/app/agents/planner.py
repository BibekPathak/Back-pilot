"""LLM Planner: decides what action the agent takes next.

Uses the OpenAI API (via LiteLLM proxy) when an API key is configured.
Falls back to a deterministic MockPlanner for local testing without keys.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

import openai

from app.agents.schemas import PlannerInput, PlannerOutput
from app.browser.actions import (
    AgentAction,
    Click,
    Extract,
    Finish,
    Goto,
    RequestHuman,
    Select,
    Target,
    Type,
    Upload,
    Wait,
)
from app.config import settings

logger = logging.getLogger(__name__)


class BasePlanner(ABC):
    """Abstract base for all planners."""

    @abstractmethod
    async def decide(self, planner_input: PlannerInput) -> PlannerOutput:
        """Return a PlannerOutput (action + reasoning) given the current state."""


# ------------------------------------------------------------------
# MockPlanner: deterministic, no API key needed
# ------------------------------------------------------------------
class MockPlanner(BasePlanner):
    """Rule-based planner for testing.  Follows a fixed strategy:

    1. If CAPTCHA detected → request_human
    2. If URL is empty or login page → goto portal invoices page
    3. If in nav state with no failures → goto login
    4. Otherwise → finish
    """

    async def decide(self, pi: PlannerInput) -> PlannerOutput:
        if pi.captcha_detected:
            return PlannerOutput(
                reasoning="CAPTCHA detected, need human",
                action=RequestHuman(reason="CAPTCHA on page"),
            )

        if pi.state in ("SUCCESS", "CREATED") or pi.step > 15:
            return PlannerOutput(
                reasoning="Task complete or step limit reached",
                action=Finish(description="mock completion"),
            )

        url = pi.observation.url.lower()
        if not url or "/login" in url:
            if "/login" in url:
                target_url = "http://localhost:8081/invoices"
            else:
                target_url = "http://localhost:8081/login"
            return PlannerOutput(
                reasoning="Navigating to portal",
                action=Goto(url=target_url),
            )

        if pi.state == "NAVIGATING" and not pi.failure_context:
            return PlannerOutput(
                reasoning="On login page, navigating to invoices",
                action=Goto(url="http://localhost:8081/invoices"),
            )

        return PlannerOutput(
            reasoning="No specific action, finishing",
            action=Finish(description="mock finish"),
        )


# ------------------------------------------------------------------
# OpenAIPlanner: real LLM-backed planner
# ------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a browser automation agent. You operate a legacy back-office portal.

Given the current page observation, task, and action history, decide the NEXT
single action to take. You must output EXACTLY a JSON object with these fields:
{
  "reasoning": "Brief explanation of your decision",
  "action": "<action_name>",
  ... action-specific fields ...
}

Available actions (pick exactly one):

1. goto: {"action":"goto","url":"http://..."}
   Navigate to a URL.

2. click: {"action":"click","target":{"label":"Button Text"}}
   Click an element by its visible label.

3. type: {"action":"type","target":{"label":"Field Label"},"text":"value"}
   Type text into an input field.

4. select: {"action":"select","target":{"label":"Field Label"},"value":"option"}
   Select a dropdown option.

5. upload: {"action":"upload","target":{"label":"Document Upload"},"filepath":"/path/to/file"}
   Upload a file.

6. wait: {"action":"wait","ms":1000}
   Wait for milliseconds.

7. back: {"action":"back"}
   Go back in browser history.

8. extract: {"action":"extract","target":{"label":"Field Label"}}
   Extract text from an element (informational, does not change state).

9. finish: {"action":"finish","description":"what was accomplished"}
   Mark the task as complete.

10. request_human: {"action":"request_human","reason":"why human is needed"}
    Request human intervention (CAPTCHA, ambiguity, etc.).

RULES:
- Output ONLY the JSON object, no markdown, no explanation outside the JSON.
- If a CAPTCHA is detected, ALWAYS use request_human.
- If the page shows a login form, type credentials and click submit.
- If the session expired, navigate back to login.
- If an element is not found, try a different approach or request_human.
- Never navigate to disallowed domains.
- The task description tells you what to accomplish.
"""


class OpenAIPlanner(BasePlanner):
    """Planner backed by the OpenAI chat completions API (or compatible proxy)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url or settings.openai_base_url
        self.model = model or settings.openai_model

    async def decide(self, pi: PlannerInput) -> PlannerOutput:
        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        user_msg = pi.to_prompt_context()

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                max_tokens=500,
            )
            raw = response.choices[0].message.content or "{}"
            raw = raw.strip()
            # Strip markdown fences if present.
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            data = json.loads(raw)
            return self._parse_output(data)

        except Exception as exc:
            logger.warning("OpenAI planner failed: %s — falling back to finish", exc)
            return PlannerOutput(
                reasoning=f"LLM error: {exc}",
                action=Finish(description="planner error fallback"),
            )

    def _parse_output(self, data: dict) -> PlannerOutput:
        """Parse the raw LLM JSON dict into a PlannerOutput."""
        reasoning = data.pop("reasoning", "no reasoning provided")
        action_name = data.get("action", "finish")

        target_raw = data.get("target")
        target = None
        if target_raw:
            if isinstance(target_raw, str):
                target = Target(label=target_raw)
            elif isinstance(target_raw, dict):
                target = Target(**target_raw)

        if action_name == "goto":
            action = Goto(url=data.get("url", "about:blank"))
        elif action_name == "click":
            action = Click(target=target or Target(label=""))
        elif action_name == "type":
            action = Type(target=target or Target(label=""), text=data.get("text", ""))
        elif action_name == "select":
            action = Select(
                target=target or Target(label=""), value=data.get("value", "")
            )
        elif action_name == "upload":
            action = Upload(
                target=target or Target(label=""),
                filepath=data.get("filepath", ""),
            )
        elif action_name == "wait":
            action = Wait(ms=data.get("ms", 1000))
        elif action_name == "back":
            from app.browser.actions import Back
            action = Back()
        elif action_name == "extract":
            action = Extract(target=target or Target(label=""))
        elif action_name == "finish":
            action = Finish(description=data.get("description", "done"))
        elif action_name == "request_human":
            action = RequestHuman(reason=data.get("reason", "unknown"))
        else:
            action = Finish(description=f"unknown action: {action_name}")

        return PlannerOutput(reasoning=reasoning, action=action)


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------
def create_planner() -> BasePlanner:
    """Create the appropriate planner based on config."""
    if settings.openai_api_key:
        logger.info("Using OpenAI planner (model=%s)", settings.openai_model)
        return OpenAIPlanner()
    logger.info("No API key configured — using MockPlanner")
    return MockPlanner()
