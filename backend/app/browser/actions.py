"""Strict, typed action schema.

The LLM never calls raw browser APIs: it emits one of these structured actions,
which the ActionValidator gates and the BrowserExecutor performs. ``finish`` and
``request_human`` are terminal/control actions handled by the agent loop.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union  # noqa: F401 (Annotated kept for API docs)

from pydantic import BaseModel, Field

ActionName = Literal[
    "goto", "click", "type", "select", "upload", "extract",
    "wait", "back", "finish", "request_human",
]


class Target(BaseModel):
    """How an action locates its element. Resolved by semantic resolution."""

    element_id: Optional[str] = Field(None, description="Observation id, e.g. 'e17'")
    role: Optional[str] = Field(None, description="ARIA role to match")
    label: Optional[str] = Field(None, description="Accessible name / text to match")
    selector: Optional[str] = Field(None, description="Explicit CSS selector")


class BaseAction(BaseModel):
    action: ActionName
    description: str = Field("", description="Human/semantic description of intent")


class Goto(BaseAction):
    action: Literal["goto"] = "goto"
    url: str


class Click(BaseAction):
    action: Literal["click"] = "click"
    target: Target


class Type(BaseAction):
    action: Literal["type"] = "type"
    target: Target
    text: str


class Select(BaseAction):
    action: Literal["select"] = "select"
    target: Target
    value: str


class Upload(BaseAction):
    action: Literal["upload"] = "upload"
    target: Target
    filepath: str


class Extract(BaseAction):
    action: Literal["extract"] = "extract"
    target: Optional[Target] = None


class Wait(BaseAction):
    action: Literal["wait"] = "wait"
    ms: int = 500


class Back(BaseAction):
    action: Literal["back"] = "back"


class Finish(BaseAction):
    action: Literal["finish"] = "finish"


class RequestHuman(BaseAction):
    action: Literal["request_human"] = "request_human"
    reason: str = ""


AgentAction = Union[
    Goto, Click, Type, Select, Upload, Extract, Wait, Back, Finish, RequestHuman
]


# Convenience constructors for the deterministic mock planner and tests.
def goto(url: str) -> Goto:
    return Goto(url=url, description=f"navigate to {url}")


def click(label: str) -> Click:
    return Click(target=Target(label=label), description=f"click {label}")


def type_text(label: str, text: str) -> Type:
    return Type(target=Target(label=label), text=text, description=f"type into {label}")


def upload(label: str, filepath: str) -> Upload:
    return Upload(target=Target(label=label), filepath=filepath, description=f"upload to {label}")


def wait(ms: int = 500) -> Wait:
    return Wait(ms=ms, description=f"wait {ms}ms")


def finish(reason: str = "workflow complete") -> Finish:
    return Finish(description=reason)
