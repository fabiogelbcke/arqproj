# Everyday commands for the new app (backend/ + frontend/). `make help` lists them.
# The current Flask site keeps its own runner: run_local.py (see README).

.DEFAULT_GOAL := help
SHELL := /bin/bash
FRONTEND := frontend

# Admin commands (staff, reset-link, tenant) take ENV=local (default) or
# ENV=staging. Staging is reached through the Cloud SQL Auth Proxy, signed in as
# your Google account (gcloud auth application-default login, once) acting as
# that environment's deploy identity, the schema's
# owner (see docs/infrastructure.md). No database password exists anywhere.
ENV ?= local
INSTANCE := arq-proj:us-east1:arqproj-db
REMOTE_PORT := 5433
DEPLOY_ACCOUNT = portal-$(ENV)-deploy@arq-proj.iam.gserviceaccount.com
REMOTE_URL = postgresql+psycopg://portal-$(ENV)-deploy%40arq-proj.iam@127.0.0.1:$(REMOTE_PORT)/arqproj_$(ENV)

define on_database
	@if [ "$(ENV)" = "local" ]; then $(1); \
	elif [ "$(ENV)" = "staging" ]; then \
	  command -v cloud-sql-proxy >/dev/null || { echo "Needs the proxy: brew install cloud-sql-proxy"; exit 2; }; \
	  log="$${TMPDIR:-/tmp}/cloud-sql-proxy-$(ENV).log"; \
	  test -f ~/.config/gcloud/application_default_credentials.json || { echo "Once per machine: gcloud auth application-default login"; exit 2; }; \
	  cloud-sql-proxy --auto-iam-authn --impersonate-service-account=$(DEPLOY_ACCOUNT) \
	    --port $(REMOTE_PORT) $(INSTANCE) >"$$log" 2>&1 & proxy=$$!; \
	  trap "kill $$proxy 2>/dev/null" EXIT; \
	  for i in $$(seq 40); do nc -z 127.0.0.1 $(REMOTE_PORT) 2>/dev/null && break; sleep 0.25; done; \
	  nc -z 127.0.0.1 $(REMOTE_PORT) >/dev/null 2>&1 || { echo "Could not reach the $(ENV) database:"; cat "$$log"; exit 1; }; \
	  MIGRATION_DATABASE_URL="$(REMOTE_URL)" $(1); \
	else echo "ENV must be local or staging"; exit 2; fi
endef

.PHONY: help setup dev serve build api-types test e2e screenshots lint format migrate staff reset-link tenant tenant-host

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

screenshots: build ## Staff app screenshots; with PR=<n>, published for that PR's description
	cd $(FRONTEND) && rm -rf screenshots && npm run screenshots
	@if [ -z "$(PR)" ]; then echo "Saved in $(FRONTEND)/screenshots (add PR=<n> to publish)"; exit 0; fi; \
	dir=$$(mktemp -d); \
	if git ls-remote --exit-code --heads origin screenshots >/dev/null 2>&1; then \
	  git fetch -q origin screenshots && git worktree add -q -B screenshots "$$dir" origin/screenshots; \
	else git worktree add -q --orphan -b screenshots "$$dir"; fi; \
	rm -rf "$$dir/pr-$(PR)" && mkdir -p "$$dir/pr-$(PR)" && cp $(FRONTEND)/screenshots/*.png "$$dir/pr-$(PR)/" && \
	git -C "$$dir" add "pr-$(PR)" && git -C "$$dir" commit -q -m "Screenshots for PR #$(PR)" && \
	git -C "$$dir" push -q origin screenshots; \
	git worktree remove --force "$$dir"; \
	echo; echo "## Screenshots"; echo; echo "| Screen | Desktop | Phone |"; echo "| --- | --- | --- |"; \
	for desktop in $(FRONTEND)/screenshots/*-desktop*.png; do \
	  name=$$(basename "$$desktop"); phone=$${name/desktop/phone}; \
	  url="https://github.com/fabiogelbcke/arqproj/blob/screenshots/pr-$(PR)"; \
	  echo "| $${name%.png} | <img src=\"$$url/$$name?raw=true\" width=\"420\"> | <img src=\"$$url/$$phone?raw=true\" width=\"160\"> |"; \
	done

lint: ## Code style checks
	uv run ruff check backend
	uv run ruff format --check backend
	cd $(FRONTEND) && npm run typecheck

format: ## Fix Python formatting
	uv run ruff format backend

migrate: ## Apply new migrations to the local dev database
	uv run alembic -c backend/alembic.ini upgrade head

staff: ## Staff account + invite link: make staff TENANT=alinea EMAIL=you@x.com NAME=You [ROLE=owner] [ENV=staging]
	@test -n "$(TENANT)" -a -n "$(EMAIL)" -a -n "$(NAME)" || { echo "Usage: make staff TENANT=alinea EMAIL=you@x.com NAME=You [ROLE=owner] [ENV=staging]"; exit 2; }
	$(call on_database,uv run python -m backend.commands.staff add --tenant "$(TENANT)" --email "$(EMAIL)" --name "$(NAME)" --role "$(or $(ROLE),member)")

reset-link: ## New password link: make reset-link TENANT=alinea EMAIL=you@x.com [ENV=staging]
	@test -n "$(TENANT)" -a -n "$(EMAIL)" || { echo "Usage: make reset-link TENANT=alinea EMAIL=you@x.com [ENV=staging]"; exit 2; }
	$(call on_database,uv run python -m backend.commands.staff reset-link --tenant "$(TENANT)" --email "$(EMAIL)")

tenant: ## New office: make tenant SLUG=alinea NAME="ALINEA ARQUITETOS" HOST=address [ENV=staging]
	@test -n "$(SLUG)" -a -n "$(NAME)" -a -n "$(HOST)" || { echo "Usage: make tenant SLUG=alinea NAME=\"Office name\" HOST=address [ENV=staging]"; exit 2; }
	$(call on_database,uv run python -m backend.commands.tenants add --slug "$(SLUG)" --name "$(NAME)" --host "$(HOST)")

tenant-host: ## Another address for an office: make tenant-host SLUG=alinea HOST=address [PRIMARY=1] [ENV=staging]
	@test -n "$(SLUG)" -a -n "$(HOST)" || { echo "Usage: make tenant-host SLUG=alinea HOST=address [PRIMARY=1] [ENV=staging]"; exit 2; }
	$(call on_database,uv run python -m backend.commands.tenants add-host --slug "$(SLUG)" --host "$(HOST)" $(if $(PRIMARY),--primary))
