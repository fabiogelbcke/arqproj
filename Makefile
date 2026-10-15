# Everyday commands for the new app (backend/ + frontend/). `make help` lists them.
# The current Flask site keeps its own runner: run_local.py (see README).

.DEFAULT_GOAL := help
SHELL := /bin/bash
FRONTEND := frontend

.PHONY: help setup dev serve build api-types test e2e lint format migrate staff

help: ## List the commands
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

setup: ## Once (and after pulling): packages, local databases, migrations, access, test offices
	uv sync
	cd $(FRONTEND) && npm ci
	uv run python -m backend.commands.local_db setup
	uv run alembic -c backend/alembic.ini upgrade head
	uv run python -m backend.commands.provision
	uv run python -m backend.commands.seed
	$(MAKE) api-types

dev: api-types ## Backend + staff app with live reload → http://alinea.localhost:5173/painel
	@trap 'kill 0' EXIT; \
	uv run uvicorn backend.app:create_app --factory --reload --port 8000 & \
	(cd $(FRONTEND) && npm run dev) & \
	wait

serve: build ## The built app, as deployed → http://alinea.localhost:8000/painel
	uv run uvicorn backend.app:create_app --factory --port 8000

build: ## Build the staff app into frontend/dist
	cd $(FRONTEND) && npm run build

api-types: ## Regenerate the staff app's API types from the backend
	uv run python -m backend.commands.openapi $(FRONTEND)/src/api/openapi.json
	cd $(FRONTEND) && npm run api-types

test: ## All fast tests: backend, staff app, and API types up to date
	uv run pytest -q
	cd $(FRONTEND) && npm run api-types:check && npm run typecheck && npm test

e2e: build ## Browser tests against the built app on a fresh local database
	cd $(FRONTEND) && npm run test:e2e

lint: ## Code style checks
	uv run ruff check backend
	uv run ruff format --check backend
	cd $(FRONTEND) && npm run typecheck

format: ## Fix Python formatting
	uv run ruff format backend

migrate: ## Apply new migrations to the local dev database
	uv run alembic -c backend/alembic.ini upgrade head

staff: ## Create a staff account: make staff TENANT=alinea EMAIL=you@x.com NAME=You [ROLE=owner]
	@test -n "$(TENANT)" -a -n "$(EMAIL)" -a -n "$(NAME)" || { echo "Usage: make staff TENANT=alinea EMAIL=you@x.com NAME=You [ROLE=owner]"; exit 2; }
	uv run python -m backend.commands.staff add --tenant "$(TENANT)" --email "$(EMAIL)" --name "$(NAME)" --role "$(or $(ROLE),member)"
