"""Failure injection system for the legacy ERP portal simulator.

Every failure is deterministic and reproducible. Two knobs:

* ``PORTAL_FAILURE_MODE`` — a single forced mode for the whole portal
  (e.g. ``PORTAL_FAILURE_MODE=CAPTCHA``).
* ``PORTAL_FAILURE_SEQUENCE`` — comma separated, *step-ordered* list of modes
  injected sequentially across the fixed workflow steps
  (e.g. ``UNEXPECTED_MODAL,CAPTCHA``).

Workflow steps are a fixed, ordered coordinate space. With a given
sequence/seed the injection is fully reproducible; nothing is random by
default, and with neither knob set the portal behaves ``NORMAL``.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional, Union

# Fixed ordered workflow steps used as the injection coordinate space.
WORKFLOW_STEPS: dict[str, int] = {
    "LOGIN_POST": 1,
    "LOGIN_OK": 2,
    "INVOICE_PAGE": 3,
    "FILL_FORM": 4,
    "UPLOAD": 5,
    "SUBMIT": 6,
    "RESULT": 7,
}

FAILURE_MODES: frozenset[str] = frozenset(
    {
        "NORMAL",
        "SELECTOR_CHANGE",
        "SLOW_NETWORK",
        "MISSING_ELEMENT",
        "UNEXPECTED_MODAL",
        "SESSION_EXPIRED",
        "UPLOAD_FAILURE",
        "CAPTCHA",
    }
)

# The workflow step each failure mode naturally fires at. A sequence entry
# injects its mode at this fixed step, so ordering in the list only controls
# which of multiple modes are active (not their position).
DEFAULT_STEP: dict[str, str] = {
    "SLOW_NETWORK": "LOGIN_POST",
    "SESSION_EXPIRED": "INVOICE_PAGE",
    "UNEXPECTED_MODAL": "INVOICE_PAGE",
    "SELECTOR_CHANGE": "FILL_FORM",
    "CAPTCHA": "FILL_FORM",
    "MISSING_ELEMENT": "SUBMIT",
    "UPLOAD_FAILURE": "UPLOAD",
}

StepKey = Union[int, str]


class FailureInjector:
    """Resolves which failure (if any) applies at a given workflow step."""

    def __init__(
        self,
        mode: Optional[str] = None,
        sequence: Optional[Iterable[str]] = None,
        seed: int = 42,
    ) -> None:
        self.mode = self._normalize(mode)
        self.sequence: list[str] = []
        if sequence:
            for item in sequence:
                item = self._normalize(item)
                if item and item != "NORMAL":
                    self.sequence.append(item)
        self.seed = seed

    @staticmethod
    def _normalize(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = value.strip().upper()
        if value not in FAILURE_MODES:
            raise ValueError(
                f"Unknown failure mode {value!r}. Valid: {sorted(FAILURE_MODES)}"
            )
        return value

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "FailureInjector":
        env = env or os.environ
        mode = env.get("PORTAL_FAILURE_MODE", "NORMAL")
        seq = [s for s in env.get("PORTAL_FAILURE_SEQUENCE", "").split(",") if s.strip()]
        seed = int(env.get("PORTAL_RANDOM_SEED", "42"))
        return cls(mode=mode, sequence=seq, seed=seed)

    # -- resolution ---------------------------------------------------------
    def resolve(self, step: StepKey) -> Optional[str]:
        """Effective failure mode at a step.

        * If a single ``mode`` is forced, it is active at every step (the whole
          portal runs under one behaviour) unless it is NORMAL.
        * Otherwise each mode in ``sequence`` is active only at its natural
          ``DEFAULT_STEP``.
        Returns ``None`` when behaviour at this step should be NORMAL.
        """
        if self.mode and self.mode != "NORMAL":
            return self.mode

        if not self.sequence:
            return None

        step_name = self._step_name(step)
        for mode in self.sequence:
            if DEFAULT_STEP.get(mode) == step_name:
                return mode
        return None

    def step_name(self, step: StepKey) -> str:
        return self._step_name(step)

    @staticmethod
    def _step_name(step: StepKey) -> str:
        if isinstance(step, str):
            if step not in WORKFLOW_STEPS:
                raise ValueError(f"Unknown workflow step {step!r}")
            return step
        for name, number in WORKFLOW_STEPS.items():
            if number == step:
                return name
        raise ValueError(f"Unknown workflow step {step!r}")

    def applies(self, step: StepKey, modes: Iterable[str]) -> bool:
        current = self.resolve(step)
        return current is not None and current in set(m.upper() for m in modes)


def build_injector() -> FailureInjector:
    return FailureInjector.from_env()
