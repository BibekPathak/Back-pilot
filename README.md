# BackPilot

Browser agents that don't give up when the real world gets messy.

BackPilot is a computer-use back-office agent that operates legacy web portals,
recovers from broken UI assumptions, and hands control to a human when
automation encounters CAPTCHA or ambiguity.

> Status: **Milestone 8** — full stack with frontend dashboard, evaluator,
> recovery engine, and human-takeover workflow.

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

| Service | URL |
| --- | --- |
| Frontend Dashboard | http://localhost:3001 |
| Legacy ERP portal | http://localhost:8081 |
| Backend API | http://localhost:8002/api |
| Postgres | localhost:5433 |
| Redis | localhost:6380 |

## Tests

```bash
pip install -r backend/requirements-dev.txt
pytest backend/tests
```

## Evaluation

```bash
make evaluate
```

Runs all failure scenarios (happy_path, selector_change, slow_network,
missing_element, unexpected_modal, session_expired, upload_failure, captcha)
and scores the agent's performance.
