.PHONY: build run test test-watch test-human report-human lint clean dev-backend dev-frontend dev seed

## Build the production Docker image
build:
	docker compose build

## Start the app + ngrok tunnel
run:
	docker compose up

## Run the full test suite inside Docker (no API keys needed)
test:
	docker compose -f docker-compose.test.yml build --quiet
	docker compose -f docker-compose.test.yml run --rm test

## Watch mode: re-run tests on file change (requires pytest-watch)
test-watch:
	docker compose -f docker-compose.test.yml run --rm test \
		sh -c "pip install pytest-watch -q && ptw tests/ app/ -- -v"

## Run human-likeness tests against the live LLM (requires Ollama running locally)
test-human:
	python -m pytest tests/test_human_likeness.py -v -s -p no:cov --tb=short

## Generate a standalone human-likeness report (no pytest needed)
report-human:
	python tests/test_human_likeness.py

## Lint with ruff (if installed)
lint:
	@command -v ruff >/dev/null 2>&1 && ruff check app/ tests/ || echo "ruff not installed — skipping"

## Seed the problems table (idempotent)
seed:
	python -m scripts.seed_problems

## Run the FastAPI backend locally (no Docker)
dev-backend:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

## Run the Next.js frontend
dev-frontend:
	cd frontend && npm run dev

## Run both (use two terminals or a process manager)
dev:
	@echo "Run 'make dev-backend' and 'make dev-frontend' in two terminals."

## Remove Docker containers and images created by this project
clean:
	docker compose down --rmi local --volumes --remove-orphans
	docker compose -f docker-compose.test.yml down --rmi local --remove-orphans
