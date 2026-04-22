.PHONY: build run test test-watch lint clean

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

## Lint with ruff (if installed)
lint:
	@command -v ruff >/dev/null 2>&1 && ruff check app/ tests/ || echo "ruff not installed — skipping"

## Remove Docker containers and images created by this project
clean:
	docker compose down --rmi local --volumes --remove-orphans
	docker compose -f docker-compose.test.yml down --rmi local --remove-orphans
