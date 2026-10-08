# ChangeGuard developer commands. `make help` lists them.
SHELL := /bin/bash
ENGINE_PORT ?= 8000
WEB_PORT ?= 3000
EVAL_MODELS ?= llama3.2:3b,qwen2.5-coder:7b,qwen2.5-coder:7b@3

.DEFAULT_GOAL := help
.PHONY: help setup dev engine web test test-engine test-web e2e lint typecheck check eval eval-check contract data docker clean

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Install engine (uv) and web (npm) dependencies
	cd backend && uv sync
	cd frontend && npm ci

dev: ## Run the engine (:8000) and the web app (:3000) with reload
	@trap 'kill 0' INT TERM EXIT; \
	(cd backend && uv run uvicorn changeguard.api.app:create_default_app --factory --reload --port $(ENGINE_PORT)) & \
	(cd frontend && CHANGEGUARD_API_URL=http://127.0.0.1:$(ENGINE_PORT) npm run dev -- --port $(WEB_PORT)) & \
	wait

engine: ## Run only the engine, with reload
	cd backend && uv run uvicorn changeguard.api.app:create_default_app --factory --reload --port $(ENGINE_PORT)

web: ## Run only the web app (expects an engine on ENGINE_PORT)
	cd frontend && CHANGEGUARD_API_URL=http://127.0.0.1:$(ENGINE_PORT) npm run dev -- --port $(WEB_PORT)

test: test-engine test-web ## Unit and integration tests for both halves

test-engine:
	cd backend && uv run pytest -q

test-web:
	cd frontend && npm test

e2e: ## Playwright end-to-end tests against a production build and a real engine
	cd frontend && npm run build && npm run test:e2e

lint: ## Lint and formatting checks
	cd backend && uv run ruff check src tests tools && uv run ruff format --check src tests tools
	cd frontend && npm run lint

typecheck: ## Static type checks (mypy strict, tsc)
	cd backend && uv run mypy src
	cd frontend && npm run typecheck

check: lint typecheck test eval-check ## Everything CI runs except e2e and container builds

eval: ## Run the evaluation (models replayed from recordings) and refresh the reports
	cd backend && uv run changeguard eval --ai replay --ai-model "$(EVAL_MODELS)"

eval-check: ## Evaluation regression gate against the committed baseline
	cd backend && uv run changeguard eval --ai replay --ai-model "$(EVAL_MODELS)" --no-write \
		--check-baseline ../eval/baselines/changeguard.json

contract: ## Regenerate the OpenAPI document and the web app's TypeScript types
	cd backend && uv run python -m changeguard.api.openapi_export ../frontend/openapi.json
	cd frontend && npm run gen:api

data: ## Regenerate the web app's static data (rules, recorded sample report, exports)
	cd backend && uv run python tools/export_frontend_data.py ../frontend/src/data

docker: ## Build and start both containers (web on :3000, engine on :8000)
	docker compose up --build

clean: ## Remove build and test artefacts
	rm -rf frontend/.next frontend/test-results frontend/playwright-report frontend/tsconfig.tsbuildinfo
	rm -rf backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache backend/htmlcov backend/.coverage
