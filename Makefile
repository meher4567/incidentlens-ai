.PHONY: help build up down generate aggregate detect score test lint clean train-if \
        train-rca seed seed-prod migrate benchmark quick-demo demo verify prod-up prod-down

help:
	@echo "IncidentLens AI - Makefile Commands"
	@echo "===================================="
	@echo "make build       Build Docker images"
	@echo "make up          Start all services (docker compose up -d)"
	@echo "make down        Stop all services"
	@echo "make seed        Seed services, dependencies, and truth data"
	@echo "make seed-prod   Seed services and dependencies (no truth data)"
	@echo "make generate    Generate synthetic logs and ingest them"
	@echo "make aggregate   Aggregate logs into ML feature windows"
	@echo "make detect      Detect anomalies and create incidents"
	@echo "make train-if    Train Isolation Forest models on normal traffic"
	@echo "make train-rca   Train and evaluate the RCA ranker"
	@echo "make score       Score incidents using the trained RCA ranker"
	@echo "make benchmark   Run all benchmarks"
	@echo "make migrate     Run Alembic migrations"
	@echo "make test        Run backend tests"
	@echo "make lint        Run linting (ruff, mypy)"
	@echo "make clean       Stop containers and remove volumes"
	@echo "make quick-demo  Fast 5K event demo"
	@echo "make verify      Run local code/test/dependency gates"
	@echo "make prod-up     Build and start the hardened production stack"
	@echo "make prod-down   Stop the production stack"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

seed:
	python -m backend.scripts.seed --truth incidents_truth.jsonl

seed-prod:
	python -m backend.scripts.seed --skip-truth

migrate:
	python -m alembic upgrade head

generate:
	python -m generator.generate_logs --events 100000 --output logs.jsonl --truth incidents_truth.jsonl
	python -m backend.scripts.seed --truth incidents_truth.jsonl
	python -m backend.scripts.import_logs --input logs.jsonl --direct-db

aggregate:
	python -m backend.scripts.run_pipeline --aggregate-only

detect:
	python -m backend.scripts.run_pipeline --process-only

score:
	python -m backend.scripts.run_pipeline --score-only

train-if:
	python -m backend.scripts.train_isolation_forest

train-rca:
	python -m backend.scripts.train_rca

benchmark:
	python -m benchmarks.ingestion_throughput
	python -m benchmarks.quality_gate
	python -m benchmarks.api_latency

test:
	python -m pytest backend/tests/ -v --cov=backend.app --cov=generator \
		--cov-report=term-missing --cov-fail-under=80

lint:
	ruff check backend/ worker/ generator/ benchmarks/
	ruff format --check backend/ worker/ generator/ benchmarks/
	mypy backend/ --ignore-missing-imports

verify: lint test
	pip-audit -r backend/requirements.txt
	cd frontend && npm test && npm run lint && npm run build && npm audit --audit-level=moderate

prod-up:
	docker compose -f compose.prod.yml up -d --build

prod-down:
	docker compose -f compose.prod.yml down

clean:
	docker compose down -v
	rm -f logs.jsonl incidents_truth.jsonl

quick-demo:
	@echo "=== Quick 5K Event Demo ==="
	$(MAKE) migrate
	python -m generator.generate_logs --events 5000 --output logs.jsonl --truth incidents_truth.jsonl
	python -m backend.scripts.seed --truth incidents_truth.jsonl
	python -m backend.scripts.import_logs --input logs.jsonl --direct-db
	$(MAKE) aggregate
	$(MAKE) train-if
	$(MAKE) detect
	$(MAKE) train-rca
	$(MAKE) score
	@echo "Demo complete! Open http://localhost:5173"

demo: up
	@echo "Starting demo..."
	@echo "Waiting for services to be healthy..."
	python -c "import time; time.sleep(10)"
	$(MAKE) migrate
	$(MAKE) generate
	$(MAKE) aggregate
	$(MAKE) train-if
	$(MAKE) detect
	$(MAKE) train-rca
	$(MAKE) score
	@echo "Demo ready! Open http://localhost:5173"
