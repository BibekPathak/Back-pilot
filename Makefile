.PHONY: setup dev test evaluate portal backend frontend up down logs format

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

# Run the evaluation across all failure scenarios (requires full stack)
evaluate:
	docker compose up -d postgres redis legacy-portal backend
	python3 -m evaluator.runner

# Frontend dev server (requires npm)
frontend:
	cd frontend && npm run dev

format:
	@echo "Linting target (ruff)."
