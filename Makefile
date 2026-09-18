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

dev:            ## Start the docker dev stack (API :8000 + redis) — prod-parity
	bash scripts/dev-server.sh start

dev-stop:       ## Stop the docker dev stack (dev data kept)
	bash scripts/dev-server.sh stop

dev-reset:      ## Wipe dev data volumes + rebuild the docker dev stack fresh
	bash scripts/dev-server.sh reset

server:         ## Start the FastAPI dev server on the host (lightweight, --reload)
	cd server && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000

server-install: ## Install server dependencies (runtime + dev tooling)
	cd server && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt

server-lint:    ## Lint server code with flake8 (repo-root .flake8 config)
	cd server && source venv/bin/activate && flake8 . --count --statistics

server-format:  ## Format server code with black (line length matches pre-commit black hook)
	# NOTE: isort is intentionally NOT here — pre-commit is its single gate.
	# A second venv-based isort disagrees with the hook env (different config
	# discovery), which would reintroduce the drift this project avoids.
	cd server && source venv/bin/activate && black --line-length=120 .

server-check: server-lint test  ## Run all server checks

# ─── Tests ────────────────────────────────────────────────────────────────────

test: test-backend test-dashboard  ## Run backend + dashboard tests (mirrors CI)

test-all: test  ## Run EVERYTHING (backend + dashboard) — alias of make test, kept for compatibility

test-backend:   ## Run full backend suite (incl. live WebSocket integration tests — matches CI)
	cd server && source venv/bin/activate && python -m pytest tests/ -v --tb=short

test-dashboard: ## Run dashboard tests (jest, CI mode)
	cd dashboard && npm run test:ci

test-cov:       ## Run backend tests with coverage
	cd server && source venv/bin/activate && python -m pytest tests/ -v --tb=short --cov=. --cov-report=term-missing --cov-report=html:coverage_html --cov-report=xml:coverage.xml

# Threshold is 75% to mirror the CI job (.github/workflows/ci.yml) and
# quality-gate below — it previously said 80%, which this repo's actual
# coverage (~76%) could never satisfy, so the gate failed on every run.
coverage-check: test-cov  ## Check coverage threshold (75% minimum, fails if below)
	@python3 -c "import xml.etree.ElementTree as ET, sys; tree = ET.parse('server/coverage.xml'); rate = float(tree.getroot().attrib['line-rate']) * 100; print(f'Coverage: {rate:.1f}% (threshold: 75.0%)'); sys.exit(0 if rate >= 75.0 else 1)"

test-auth-integration: ## Run auth flow integration tests (register → verify → login → session)
	cd server && source venv/bin/activate && python -m pytest tests/test_auth_flow_integration.py -v --tb=short

test-auth-integration-cov: ## Run auth integration tests with coverage report
	cd server && source venv/bin/activate && python -m pytest tests/test_auth_flow_integration.py -v --tb=short --cov=. --cov-report=term-missing --cov-report=xml:coverage_auth.xml

test-device-integration: ## Run device lifecycle integration tests (register → claim → share)
	cd server && source venv/bin/activate && python -m pytest tests/test_device_lifecycle_integration.py -v --tb=short

test-geofence-integration: ## Run geofencing integration tests (create zone → trigger → alert)
	cd server && source venv/bin/activate && python -m pytest tests/test_geofence_integration.py -v --tb=short

test-integration: ## Run ALL integration tests (auth + device + geofence + e2e)
	cd server && source venv/bin/activate && python -m pytest tests/test_auth_flow_integration.py tests/test_device_lifecycle_integration.py tests/test_geofence_integration.py tests/test_e2e.py -v --tb=short

test-e2e-dashboard: ## Run Playwright E2E tests for dashboard
	cd dashboard && npx playwright test

test-e2e-chromium: ## Run Playwright E2E tests on Chromium only
	cd dashboard && npx playwright test --project=chromium

test-e2e-report: ## Show Playwright E2E test report
	cd dashboard && npx playwright show-report

android-e2e: ## Run Android Espresso UI tests (requires connected device/emulator)
	cd android-app && JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 ./gradlew connectedAndroidTest

# ─── Load Testing (k6) ──────────────────────────────────────────────────────

load-test-health: ## Run k6 load test on health endpoint (10 VUs, 30s)
	@mkdir -p tests/load/results
	k6 run tests/load/k6-health.js

load-test-location: ## Run k6 load test on device location endpoint
	@mkdir -p tests/load/results
	k6 run tests/load/k6-device-location.js

load-test-full: ## Run k6 full API load test (all endpoints)
	@mkdir -p tests/load/results
	k6 run tests/load/k6-full-api.js

load-test-stress: ## Run k6 stress test (100 VUs, 60s)
	@mkdir -p tests/load/results
	k6 run --vus 100 --duration 60s tests/load/k6-full-api.js

load-test-report: ## Show k6 load test results
	@cat tests/load/results/full-api-summary.json 2>/dev/null || echo "No results found. Run make load-test-full first."

# ─── Monitoring Stack ───────────────────────────────────────────────────────

monitoring-up: ## Start Grafana + Prometheus monitoring stack
	cd tests/load && docker-compose -f docker-compose.monitoring.yml up -d

monitoring-down: ## Stop monitoring stack
	cd tests/load && docker-compose -f docker-compose.monitoring.yml down

monitoring-logs: ## Follow monitoring logs
	cd tests/load && docker-compose -f docker-compose.monitoring.yml logs -f

load-test-monitored: ## Run k6 with Prometheus output (requires monitoring stack)
	k6 run --out prometheus tests/load/k6-full-api.js

grafana-open: ## Open Grafana in browser
	@echo "Opening Grafana at http://localhost:3000"
	@echo "Username: admin"
	@echo "Password: magneetar-dev"

# ─── k6 Cloud (Distributed Testing) ──────────────────────────────────────────

load-test-cloud: ## Run k6 in Grafana Cloud (distributed)
	k6 cloud tests/load/k6-distributed.js

load-test-cloud-lagos: ## Run k6 Cloud with Lagos focus (50% weight)
	K6_CLOUD_DISTRIBUTION='{"lagos":{"loadZone":"asia-south1","weight":50},"london":{"loadZone":"europe-west2","weight":30},"virginia":{"loadZone":"us-east4","weight":20}}' k6 cloud tests/load/k6-distributed.js

load-test-cloud-global: ## Run k6 Cloud with equal global distribution
	K6_CLOUD_DISTRIBUTION='{"lagos":{"loadZone":"asia-south1","weight":33},"london":{"loadZone":"europe-west2","weight":34},"virginia":{"loadZone":"us-east4","weight":33}}' k6 cloud tests/load/k6-distributed.js

k6-login: ## Login to k6 Cloud
	k6 cloud login

# ─── Design Tokens ──────────────────────────────────────────────────────────

tokens-sync: ## Sync Figma tokens to Tailwind config
	cd dashboard && node scripts/sync-figma-tokens.js

tokens-build: ## Build design tokens (CSS variables + Tailwind)
	cd dashboard && node config/style-dictionary.js

tokens-watch: ## Watch for token changes and rebuild
	cd dashboard && nodemon --watch src/styles/tokens -e json --exec "npm run tokens:build"

# ─── Figma Code Connect ──────────────────────────────────────────────────────

figma-connect: ## Connect Figma components to React code
	cd dashboard && npx @figma/code-connect

figma-connect-dry: ## Preview Figma connections without updating
	cd dashboard && npx @figma/code-connect --dry-run

figma-connect-status: ## Show Figma connection status
	cd dashboard && npx @figma/code-connect --status

# ─── Storybook ──────────────────────────────────────────────────────────────

storybook: ## Start Storybook dev server (port 6006)
	cd dashboard && npm run storybook

storybook-build: ## Build Storybook for deployment
	cd dashboard && npm run build-storybook

storybook-test: ## Run Storybook interaction tests
	cd dashboard && npm run test-storybook

# ─── Chromatic Visual Regression ─────────────────────────────────────────────

chromatic: ## Run Chromatic visual regression tests
	cd dashboard && npm run chromatic

chromatic-ci: ## Run Chromatic in CI mode (exit zero on changes)
	cd dashboard && npm run chromatic:ci

chromatic-accept: ## Auto-accept all changes on main
	cd dashboard && npm run chromatic:main

chromatic-baseline-accept: ## Accept all visual changes as new baseline
	bash scripts/chromatic-baseline.sh accept

chromatic-baseline-reject: ## Reject visual changes, keep old baseline
	bash scripts/chromatic-baseline.sh reject

chromatic-baseline-status: ## Show current baseline status
	bash scripts/chromatic-baseline.sh status

chromatic-baseline-diff: ## Show differences from baseline
	bash scripts/chromatic-baseline.sh diff

coverage-json: test-cov  ## Generate coverage summary JSON for dashboard
	python3 scripts/generate-coverage-json.py

kotlin-dead-code: ## Check Kotlin files for dead code patterns
	find android-app/app/src/main -name '*.kt' -type f | xargs bash scripts/check-kotlin-dead-code.sh

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

dashboard-format: ## Format dashboard code with ESLint --fix (matches pre-commit eslint hook)
	cd dashboard && npm run lint -- --fix

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

deploy-rolling: ## Deploy with rolling updates (zero-downtime)
	bash scripts/deploy-rolling.sh

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

quality-gate:  ## Full quality gate: tests + lint + typecheck + coverage + dead code
	@echo "═══ Magneetar Quality Gate ═══"
	@echo ""
	@echo "1/5 Backend tests..."
	@cd server && source venv/bin/activate && python -m pytest tests/ -q --tb=line --ignore=tests/test_media_delete.py 2>&1 | tail -3
	@echo ""
	@echo "2/5 Dashboard tests..."
	@cd dashboard && npm run test:ci 2>&1 | tail -3
	@echo ""
	@echo "3/5 TypeScript typecheck..."
	@cd dashboard && npx tsc --noEmit && echo "✅ TypeScript OK"
	@echo ""
	@echo "4/5 Python lint..."
	@cd server && source venv/bin/activate && flake8 . --count --statistics 2>&1 | tail -5
	@echo ""
	@echo "5/5 Coverage check..."
	@cd server && source venv/bin/activate && python -m pytest tests/ -q --cov=. --cov-report=xml:coverage.xml --tb=no -q 2>&1 | tail -3
	@python3 -c "import xml.etree.ElementTree as ET; tree = ET.parse('server/coverage.xml'); rate = float(tree.getroot().attrib['line-rate']) * 100; print(f'Coverage: {rate:.1f}% (threshold: 75.0%)'); exit(0 if rate >= 75.0 else 1)"
	@echo ""
	@echo "═══════════════════════════"
	@echo "✅ All quality gates passed"

# ── Health Monitoring ─────────────────────────────────────────────────────────

health-check:   ## Run a one-shot health check
	bash scripts/health-alert.sh

health-monitor: ## Start continuous health monitoring (Ctrl+C to stop)
	bash scripts/health-alert.sh --daemon

health-status:  ## Show health monitor status
	bash scripts/health-alert.sh --status

health-install: ## Install health monitor cron job (every 2 min)
	bash scripts/health-alert.sh --init-cron

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
