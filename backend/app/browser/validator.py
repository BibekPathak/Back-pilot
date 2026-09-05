"""ActionValidator: the boundary that gates every action before execution.

LLM output (or any input) is never executed directly. Each action must:
* parse against the strict Pydantic schema (invalid => rejected),
* satisfy policy checks (e.g. goto target must be in the domain allowlist).
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

from pydantic import TypeAdapter, ValidationError

from app.browser.actions import AgentAction, Goto
from app.browser.observation import PageObservation
from app.config import settings

_TA = TypeAdapter(AgentAction)


class ActionValidationError(ValueError):
    """Raised when an action fails schema or policy validation."""


class ActionValidator:
    def __init__(self, allowed_domains: Optional[list[str]] = None):
        self.allowed_domains = allowed_domains or [
            d.strip().lower() for d in settings.allowed_domains.split(",") if d.strip()
        ]

    def parse(self, raw: dict) -> AgentAction:
        """Parse and validate raw dict into a typed AgentAction."""
        try:
            return _TA.validate_python(raw)
        except ValidationError as exc:
            raise ActionValidationError(
                f"Invalid action: {exc.errors()[0].get('msg', 'schema error')}"
            ) from exc

    def validate(self, action: AgentAction, observation: Optional[PageObservation] = None) -> None:
        """Policy checks beyond schema (called before execution)."""
        if isinstance(action, Goto):
            host = (urllib.parse.urlparse(action.url).hostname or "").lower()
            if host and not any(host == d or host.endswith("." + d)
                                for d in self.allowed_domains):
                raise ActionValidationError(
                    f"goto to disallowed domain denied: {action.url}"
                )

    def check(self, raw: dict, observation: Optional[PageObservation] = None) -> AgentAction:
        action = self.parse(raw)
        self.validate(action, observation)
        return action
