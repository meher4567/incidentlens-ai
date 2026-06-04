.PHONY: help build up down generate detect test lint clean train-if seed seed-prod migrate \
        benchmark quick-demo demo

help:
	@echo "IncidentLens AI - Makefile Commands"
	@echo "===================================="
	@echo "make build       Build Docker images"
	@echo "make up          Start all services (docker compose up -d)"
	@echo "make down        Stop all services"
	@echo "make seed        Seed services, dependencies, and truth data"
	@echo "make seed-prod   Seed services and dependencies (no truth data)"
	@echo "make generate    Generate synthetic logs and ingest them"
	@echo "make detect      Run aggregation, detection, clustering, and RCA ranking"
	@echo "make train-if    Train Isolation Forest models on normal traffic"
	@echo "make benchmark   Run all benchmarks"
	@echo "make migrate     Run Alembic migrations"
	@echo "make test        Run backend tests"
	@echo "make lint        Run linting (ruff, mypy)"
	@echo "make clean       Stop containers and remove volumes"
	@echo "make quick-demo  Fast 1K event demo"

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
	python -m backend.scripts.import_logs --input logs.jsonl --direct-db

detect:
	python -m backend.scripts.run_pipeline --full

train-if:
	python -m backend.scripts.train_isolation_forest

benchmark:
	python -m benchmarks.ingestion_throughput
	python -m benchmarks.detection_rate
	python -m benchmarks.dedup_compression
	python -m benchmarks.rca_accuracy
	python -m benchmarks.anomaly_pr
	python -m benchmarks.api_latency

test:
	cd backend && python -m pytest tests/ -v --cov=app --cov-report=term

lint:
	ruff check backend/ worker/ generator/ benchmarks/
	mypy backend/ --ignore-missing-imports

clean:
	docker compose down -v
	rm -f logs.jsonl incidents_truth.jsonl

quick-demo:
	@echo "=== Quick 5K Event Demo ==="
	$(MAKE) migrate
	python -m generator.generate_logs --events 5000 --output logs.jsonl --truth incidents_truth.jsonl
	python -m backend.scripts.seed --truth incidents_truth.jsonl
	python -m backend.scripts.import_logs --input logs.jsonl --direct-db
	python -m backend.scripts.train_isolation_forest
	python -m backend.scripts.run_pipeline --full
	python -m backend.scripts.train_rca
	@echo "Demo complete! Open http://localhost:5173"

demo: up
	@echo "Starting demo..."
	@echo "Waiting for services to be healthy..."
	python -c "import time; time.sleep(10)"
	$(MAKE) migrate
	$(MAKE) seed
	$(MAKE) generate
	$(MAKE) train-if
	$(MAKE) detect
	python -m backend.scripts.train_rca
	@echo "Demo ready! Open http://localhost:5173"
