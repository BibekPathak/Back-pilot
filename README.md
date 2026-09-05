# BackPilot

Browser agents that don't give up when the real world gets messy.

BackPilot is a computer-use back-office agent that operates legacy web portals,
recovers from broken UI assumptions, and hands control to a human when
automation encounters CAPTCHA or ambiguity.

> Status: **Milestone 1** — legacy ERP portal simulator, failure-injection system,
> and the backend/database skeleton are implemented and verified.

## Quick start (Milestone 1 scope)

```bash
cp .env.example .env
docker compose up -d --build
```

| Service | URL |
| --- | --- |
| Legacy ERP portal | http://localhost:8081 |
| Backend API | http://localhost:8002/api |
| Postgres | localhost:5433 |
| Redis | localhost:6380 |

## Tests

```bash
pip install -r backend/requirements-dev.txt
pytest backend/tests
```

The full README (architecture, demo, evaluation, replay) lands as features are
completed in later milestones.
