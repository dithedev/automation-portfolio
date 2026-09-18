.PHONY: test lint typecheck security coverage test-integration docker-check migrate db-check seed

PYTHON ?= python

test:
	$(PYTHON) -m pytest tests/unit -q

lint:
	$(PYTHON) -m ruff check app tests
	$(PYTHON) -m ruff format --check app tests

typecheck:
	$(PYTHON) -m mypy app

security:
	$(PYTHON) -m bandit -q -r app -c pyproject.toml
	$(PYTHON) -m pip_audit

coverage:
	$(PYTHON) -m pytest tests/unit --cov=app --cov-report=term-missing -q

test-integration:
	$(PYTHON) -m pytest tests/integration -q

docker-check:
	docker build -t news-intelligence-pipeline:local .
	docker compose config

migrate:
	$(PYTHON) -m alembic upgrade head

db-check:
	$(PYTHON) -m app.infrastructure.db.check

seed:
	$(PYTHON) -m app.infrastructure.feeds.seed
