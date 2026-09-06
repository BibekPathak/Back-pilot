.PHONY: setup dev test evaluate demo lint test-cov portal backend frontend up down logs format

# Copy env if missing
setup:
	@test -f .env || cp .env.example .env
	@echo "Environment ready. Edit .env if needed, then run: make dev"

# Build and start the full stack
dev:
	docker compose up --build

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

# Run backend, portal, and browser unit/integration tests
# (requires the supporting services: docker compose up -d postgres redis legacy-portal)
test:
	docker compose up -d postgres redis legacy-portal
	python3 -m pytest backend/tests -q

# Run tests with coverage
test-cov:
	docker compose up -d postgres redis legacy-portal
	python3 -m pytest backend/tests --cov=app --cov-report=term-missing -q

# Run the evaluation across all failure scenarios (requires full stack)
evaluate:
	docker compose up -d postgres redis legacy-portal backend
	python3 -m evaluator.runner

# Run the demo script (requires full stack)
demo:
	python3 scripts/demo.py

# Run the demo with a specific failure mode
demo-captcha:
	python3 scripts/demo.py --failure-mode CAPTCHA

demo-modal:
	python3 scripts/demo.py --failure-mode UNEXPECTED_MODAL

# Lint backend code
lint:
	python3 -m ruff check backend/app backend/tests evaluator scripts

# Frontend dev server (requires npm)
frontend:
	cd frontend && npm run dev

# Frontend build check
frontend-build:
	cd frontend && npm run build

format:
	python3 -m ruff format backend/app backend/tests evaluator scripts
