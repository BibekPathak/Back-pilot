"""ActionValidator: the boundary that gates every action before execution.

LLM output (or any input) is never executed directly. Each action must:
* parse against the strict Pydantic schema (invalid => rejected),
* satisfy policy checks (e.g. goto target must be in the domain allowlist),
* reference elements that exist in the current observation (for click/type/etc.),
* use allowed file paths for uploads (demo mode).
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import Optional

from pydantic import TypeAdapter, ValidationError

from app.browser.actions import (
    AgentAction,
    Click,
    Goto,
    Select,
    Type,
    Upload,
)
from app.browser.observation import PageObservation
from app.config import settings

_TA = TypeAdapter(AgentAction)


class ActionValidationError(ValueError):
    """Raised when an action fails schema or policy validation."""


class ActionValidator:
    def __init__(
        self,
        allowed_domains: Optional[list[str]] = None,
        allowed_upload_dirs: Optional[list[str]] = None,
    ):
        self.allowed_domains = allowed_domains or [
            d.strip().lower() for d in settings.allowed_domains.split(",") if d.strip()
        ]
        self.allowed_upload_dirs = allowed_upload_dirs or [
            str(Path(__file__).resolve().parents[3] / "fixtures"),
            "/tmp",
        ]

    # ------------------------------------------------------------------ parse
    def parse(self, raw: dict) -> AgentAction:
        """Parse and validate raw dict into a typed AgentAction."""
        try:
            return _TA.validate_python(raw)
        except ValidationError as exc:
            raise ActionValidationError(
                f"Invalid action: {exc.errors()[0].get('msg', 'schema error')}"
            ) from exc

    # ------------------------------------------------------------------ policy
    def validate(
        self,
        action: AgentAction,
        observation: Optional[PageObservation] = None,
    ) -> None:
        """Policy checks beyond schema (called before execution)."""
        # Domain check for goto.
        if isinstance(action, Goto):
            self._check_domain(action.url)

        # Element-existence check for target-based actions.
        if isinstance(action, (Click, Type, Select, Upload)):
            self._check_target(action.target, observation)

        # File path check for upload.
        if isinstance(action, Upload):
            self._check_upload_path(action.filepath)

    def _check_domain(self, url: str) -> None:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        if host and not any(
            host == d or host.endswith("." + d) for d in self.allowed_domains
        ):
            raise ActionValidationError(
                f"goto to disallowed domain denied: {url}"
            )

    def _check_target(self, target, observation: Optional[PageObservation]) -> None:
        if observation is None:
            return
        label = getattr(target, "label", None)
        role = getattr(target, "role", None)
        element_id = getattr(target, "element_id", None)

        # If we have an element_id, verify it exists in the observation.
        if element_id:
            found = any(el.id == element_id for el in observation.interactive_elements)
            if not found:
                raise ActionValidationError(
                    f"element_id '{element_id}' not found in observation"
                )
            return

        # If we have a label, verify at least one element matches.
        if label:
            found = any(
                label.lower() in el.label.lower()
                for el in observation.interactive_elements
            )
            if not found:
                raise ActionValidationError(
                    f"no element with label '{label}' found in observation"
                )
            return

        # If we have a role but no label, that's OK (will be resolved later).
        # If we have nothing, that's an error.
        if not role:
            raise ActionValidationError(
                "target must have at least one of: element_id, label, role, selector"
            )

    def _check_upload_path(self, filepath: str) -> None:
        resolved = str(Path(filepath).resolve())
        if not any(
            resolved.startswith(d) or resolved == d
            for d in self.allowed_upload_dirs
        ):
            raise ActionValidationError(
                f"upload path not in allowed directories: {filepath}"
            )

    # ------------------------------------------------------------------ combined
    def check(
        self,
        raw: dict,
        observation: Optional[PageObservation] = None,
    ) -> AgentAction:
        """Parse + validate in one call."""
        action = self.parse(raw)
        self.validate(action, observation)
        return action
