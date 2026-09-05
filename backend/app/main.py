"""BackPilot backend application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import Base, engine
from app.models import run as _run_models  # noqa: F401  (register models)
from app.models import intervention as _intervention_models  # noqa: F401  (register models)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="BackPilot API",
    version="0.1.0",
    description="Computer-use back-office agent: browser automation with recovery and HITL.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# API routers are wired in as milestones land:
from app.api.runs import router as runs_router  # noqa: E402
from app.api.human import router as human_router  # noqa: E402
from app.api.dashboard import router as dashboard_router  # noqa: E402

app.include_router(runs_router, prefix="/api")
app.include_router(human_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
