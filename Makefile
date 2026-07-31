# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Makefile
# Centralized task runner for development, testing, and deployment
# ═══════════════════════════════════════════════════════════════════════════════

# Recipes use `source venv/bin/activate`, which requires bash (not the default
# /bin/sh on Debian/Ubuntu).
SHELL := /bin/bash

.PHONY: help server server-install server-lint server-format server-check \
        test test-all test-cov test-api test-auth test-sentinel test-backend test-dashboard \
        dashboard dashboard-install dashboard-build dashboard-lint dashboard-format \
        android-build android-release android-install \
        docker-build docker-up docker-down docker-logs docker-clean \
        deploy generate-env \
        lint lint-python lint-dashboard format check validate typecheck \
        pre-commit pre-commit-install \
        clean version setup install

help:           ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Server ───────────────────────────────────────────────────────────────────

server:         ## Start the FastAPI development server
	cd server && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000

server-install: ## Install server dependencies (runtime + dev tooling)
	cd server && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt

server-lint:    ## Lint server code with flake8 (repo-root .flake8 config)
	cd server && source venv/bin/activate && flake8 . --count --statistics

server-format:  ## Format server code with black
	cd server && source venv/bin/activate && black .

server-check: server-lint test  ## Run all server checks

# ─── Tests ────────────────────────────────────────────────────────────────────

test: test-backend test-dashboard  ## Run backend + dashboard tests (mirrors CI; full backend suite: make test-all)

test-all:       ## Run ALL backend tests (including slow WebSocket tests)
	cd server && source venv/bin/activate && python -m pytest tests/ -v --tb=short

test-backend:   ## Run backend tests (excludes slow WebSocket tests — matches CI)
	cd server && source venv/bin/activate && python -m pytest tests/ -v --tb=short -k "not slow"

test-dashboard: ## Run dashboard tests (jest, CI mode)
	cd dashboard && npm run test:ci

test-cov:       ## Run backend tests with coverage
	cd server && source venv/bin/activate && python -m pytest tests/ -v --tb=short --cov=. --cov-report=term-missing

test-api:       ## Run only API tests
	cd server && source venv/bin/activate && python -m pytest tests/test_api.py -v --tb=short

test-auth:      ## Run only auth tests
	cd server && source venv/bin/activate && python -m pytest tests/test_auth.py -v --tb=short

test-sentinel:  ## Run only sentinel tests
	cd server && source venv/bin/activate && python -m pytest tests/test_sentinel.py -v --tb=short

# ─── Dashboard ────────────────────────────────────────────────────────────────

dashboard:      ## Start the Next.js dev server
	cd dashboard && npm run dev

dashboard-install: ## Install dashboard dependencies
	cd dashboard && npm ci

dashboard-build: ## Build the dashboard for production
	cd dashboard && npm run build

dashboard-lint: ## Lint dashboard code
	cd dashboard && npm run lint

dashboard-format: ## Format dashboard code with Prettier
	cd dashboard && npx prettier --write 'src/**/*.{ts,tsx,css}'

# ─── Android ──────────────────────────────────────────────────────────────────

android-build:  ## Build Android APK (debug)
	cd android-app && ./gradlew assembleDebug

android-release: ## Build Android APK (release)
	cd android-app && ./gradlew assembleRelease

android-install: ## Install debug APK via ADB
	cd android-app && ./gradlew installDebug

# ─── Docker ──────────────────────────────────────────────────────────────────

docker-build:   ## Build all Docker images
	docker compose build

docker-up:      ## Start all Docker services
	docker compose up -d

docker-down:    ## Stop all Docker services
	docker compose down

docker-logs:    ## Follow Docker logs
	docker compose logs -f

docker-clean:   ## Remove Docker volumes and images
	docker compose down -v

# ─── Deployment ───────────────────────────────────────────────────────────────

deploy:         ## Deploy with Docker Compose (production)
	git pull && docker compose build && docker compose up -d

generate-env:   ## Generate secure environment secrets
	bash scripts/generate-env.sh

# ─── Code Quality ─────────────────────────────────────────────────────────────

lint: server-lint dashboard-lint  ## Lint all code

lint-python: server-lint  ## Alias: flake8 with the repo-root .flake8 config

lint-dashboard: dashboard-lint  ## Alias: eslint on dashboard

typecheck:      ## TypeScript check (dashboard)
	cd dashboard && npx tsc --noEmit

format: server-format dashboard-format  ## Format all code

check: test lint  ## Run all checks (tests + lint)

validate: lint typecheck test pre-commit  ## Full quality gate (CI-equivalent)
	@echo "✅ All quality gates passed"

# ── Pre-commit ──────────────────────────────────────────────────────────────

pre-commit:     ## Run the full pre-commit gate on all files
	cd server && source venv/bin/activate && pre-commit run --all-files

pre-commit-install: ## Install pre-commit hooks
	pip install pre-commit 2>/dev/null || true
	pre-commit install

# ─── Utility ──────────────────────────────────────────────────────────────────

clean:          ## Remove build artifacts
	rm -rf server/__pycache__ server/**/__pycache__ server/.pytest_cache
	rm -rf dashboard/.next dashboard/out
	rm -rf android-app/app/build
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

version:        ## Show current version
	@cat VERSION 2>/dev/null || echo "1.0.0"

setup: server-install dashboard-install  ## Install everything

install: setup  ## Alias for setup
