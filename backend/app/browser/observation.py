"""Structured, semantics-based observations extracted from the browser.

The agent reasons over this compact representation instead of raw DOM. Each
interactive element is described by an accessible role, a label/name, and a
stable selector — the atomic unit the executor and recovery engine operate on.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class InteractiveElement(BaseModel):
    """A single interactive control on the page, in semantic terms."""

    id: str = Field(..., description="Stable observation id, e.g. 'e17'")
    role: str = Field(..., description="ARIA-style role: textbox, button, etc.")
    label: str = Field("", description="Accessible name / visible label")
    value: Optional[str] = Field(None, description="Current value, for inputs")
    selector: str = Field("", description="Best CSS selector known for the element")
    placeholder: Optional[str] = Field(None)


class PageObservation(BaseModel):
    """A snapshot of the current page state sent to the planner."""

    url: str
    title: str = ""
    visible_text: str = ""
    interactive_elements: list[InteractiveElement] = Field(default_factory=list)
    # Extra signals the recovery engine needs.
    modal_present: bool = False
    captcha_present: bool = False
    session_expired: bool = False
    screenshot_path: Optional[str] = None

    def find(self, **attrs) -> Optional[InteractiveElement]:
        for el in self.interactive_elements:
            if all(getattr(el, k) == v for k, v in attrs.items()):
                return el
        return None
