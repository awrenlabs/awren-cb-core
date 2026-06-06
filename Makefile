.PHONY: help install lint typecheck test test-unit test-integration test-e2e
.PHONY: clean build docs infra-up infra-down migrate api-dev dashboard-dev

help:
	@echo "Awren Core Development Commands"
	@echo "==============================="
	@echo "make install        - Install all dependencies"
	@echo "make lint           - Run ruff linter"
	@echo "make typecheck      - Run mypy type checker"
	@echo "make test           - Run all tests"
	@echo "make test-unit      - Run unit tests only"
	@echo "make test-integration - Run integration tests"
	@echo "make clean          - Clean build artifacts"
	@echo "make build          - Build all packages"
	@echo "make docs           - Build documentation"
	@echo "make infra-up       - Start Docker infrastructure"
	@echo "make infra-down     - Stop Docker infrastructure"
	@echo "make migrate        - Run database migrations"
	@echo "make api-dev        - Start API development server"
	@echo "make dashboard-dev  - Start dashboard development server"
	@echo "make precommit      - Run all pre-commit checks"

install:
	poetry install
	cd apps/dashboard && npm install

lint:
	poetry run ruff check packages/ apps/ domains/ tests/
	poetry run ruff format --check packages/ apps/ domains/ tests/

typecheck:
	poetry run mypy packages/ apps/ domains/

test:
	poetry run pytest tests/ -v

test-unit:
	poetry run pytest tests/ -v -m "unit"

test-integration:
	poetry run pytest tests/ -v -m "integration"

test-e2e:
	poetry run pytest tests/ -v -m "e2e"

clean:
	rm -rf dist/ build/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

build:
	poetry build

docs:
	cd docs && mkdocs build

infra-up:
	docker compose -f infrastructure/docker/docker-compose.yml up -d

infra-down:
	docker compose -f infrastructure/docker/docker-compose.yml down

migrate:
	poetry run alembic upgrade head

api-dev:
	poetry run uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

dashboard-dev:
	cd apps/dashboard && npm run dev

precommit: lint typecheck test
	@echo "All checks passed!"
