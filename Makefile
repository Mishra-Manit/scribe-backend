.PHONY: help install serve run celery-worker flower celery-reset stop-all clean
.PHONY: migrate migration migrate-down db-current test-infra
.PHONY: redis-start redis-stop redis-ping check-env create-env lint lint-fix format

# Load environment variables from .env file if it exists
ifneq (,$(wildcard .env))
    ENV_LOADED := true
else
    ENV_LOADED := false
endif

# Helper to load .env variables in shell commands
define load_env
	$(if $(filter true,$(ENV_LOADED)),set -a && [ -f .env ] && . .env && set +a &&,)
endef

# Default target
help: ## Show this help message
	@echo "=== Scribe Backend ==="
	@echo "Cold Email Generation Platform with Multi-Step Agentic Pipeline"
	@echo
	@echo "🚀 Quick Start:"
	@echo "  make serve        # Start FastAPI server + Celery worker"
	@echo "  make redis-start  # Start Redis (required for Celery)"
	@echo
	@echo "📋 Available Commands:"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "💡 Architecture:"
	@echo "  - FastAPI backend with Supabase auth (JWT validation)"
	@echo "  - PostgreSQL/Supabase for database (direct connection)"
	@echo "  - Redis for Celery task queue"
	@echo "  - Multi-step pipeline for email generation"
	@echo "  - Observability via Logfire"

# Installation
install: ## Install project dependencies
	pip install -r requirements.txt

# Server Commands
serve: ## Run FastAPI server and Celery worker together
	@echo "Starting FastAPI + Celery worker..."
	@bash -c "source venv/bin/activate 2>/dev/null || true && $(load_env) ( \
	  (uvicorn main:app --host 0.0.0.0 --port 8000 --reload &) && \
	  (celery -A celery_config.celery_app worker --loglevel=info --queues=email_default --concurrency=1 &) && \
	  wait \
	)"

run: serve ## Alias for serve command

celery-worker: ## Start Celery worker only
	@echo "Starting Celery worker..."
	@bash -c "source venv/bin/activate 2>/dev/null || true && $(load_env) celery -A celery_config.celery_app worker --loglevel=info --queues=email_default --concurrency=4"

flower: ## Start Flower monitoring UI on port 5555
	@echo "Starting Flower at http://localhost:5555"
	@bash -c "source venv/bin/activate 2>/dev/null || true && $(load_env) celery -A celery_config.celery_app flower --port=5555"

celery-reset: ## Clear all Celery queues and reset worker state
	@echo "Clearing all Celery queues..."
	@bash -c "source venv/bin/activate 2>/dev/null || true && $(load_env) celery -A celery_config.celery_app purge -f"
	@echo "✅ Celery queues cleared"

# Process Management
stop-all: ## Stop all running processes (uvicorn, celery, flower)
	@echo "Stopping all running processes..."
	@echo "Terminating uvicorn processes..."
	-@pkill -f "uvicorn.*main:app" 2>/dev/null || true
	-@pkill -f "python.*uvicorn.*main:app" 2>/dev/null || true
	@echo "Terminating celery processes..."
	-@pkill -f "celery.*worker" 2>/dev/null || true
	-@pkill -f "python.*celery.*worker" 2>/dev/null || true
	-@pkill -f "celery.*flower" 2>/dev/null || true
	@echo "Waiting 2 seconds for graceful shutdown..."
	@sleep 2
	@echo "Force killing any remaining processes..."
	-@pkill -9 -f "uvicorn.*main:app" 2>/dev/null || true
	-@pkill -9 -f "python.*uvicorn" 2>/dev/null || true
	-@pkill -9 -f "celery.*worker" 2>/dev/null || true
	-@pkill -9 -f "python.*celery" 2>/dev/null || true
	-@pkill -9 -f "celery.*flower" 2>/dev/null || true
	@echo "✅ All processes stopped (hard kill applied if needed)"

# Database Commands
migrate: ## Apply pending database migrations
	@echo "Applying database migrations..."
	alembic upgrade head
	@echo "✅ Migrations applied"

migration: ## Create new migration (usage: make migration MSG="description")
	@if [ -z "$(MSG)" ]; then \
		echo "❌ Error: MSG required. Usage: make migration MSG=\"your description\""; \
		exit 1; \
	fi
	@echo "Creating new migration: $(MSG)"
	alembic revision --autogenerate -m "$(MSG)"
	@echo "✅ Migration created. Review in alembic/versions/ before applying"

migrate-down: ## Rollback one migration
	@echo "Rolling back one migration..."
	alembic downgrade -1
	@echo "✅ Rolled back one migration"

db-current: ## Show current migration version
	@echo "Current database migration version:"
	@alembic current

db-history: ## Show migration history
	@echo "Migration history:"
	@alembic history --verbose

# Redis Commands (Manual Control)
redis-start: ## Start Redis server via Homebrew
	@echo "Starting Redis via Homebrew..."
	@brew services start redis 2>/dev/null || redis-server --daemonize yes
	@sleep 1
	@make redis-ping

redis-stop: ## Stop Redis server
	@echo "Stopping Redis..."
	@brew services stop redis 2>/dev/null || redis-cli shutdown 2>/dev/null || true
	@echo "✅ Redis stopped"

redis-ping: ## Check if Redis is running
	@echo "Pinging Redis..."
	@redis-cli ping && echo "✅ Redis is running" || echo "❌ Redis is not running"

# Environment Management
create-env: ## Create .env file from .env.example template
	@if [ -f .env ]; then \
		echo "⚠️  .env file already exists"; \
	else \
		echo "Creating .env file from template..."; \
		cp .env.example .env; \
		echo "✅ Created .env file from .env.example. Please update with your actual values."; \
	fi

check-env: ## Check environment configuration (validates settings.py)
	@echo "Checking environment variable configuration..."
	@python -c "from config.settings import get_settings; settings = get_settings(); print('✅ All required environment variables are set')" 2>&1 || \
	echo "❌ Missing required environment variables. Run 'make create-env' and update .env file"

# Testing
test-infra: ## Test infrastructure (Redis, Celery, Logfire)
	@echo "Testing infrastructure..."
	@python scripts/test_infrastructure.py

# Linting and Formatting
lint: ## Run all linting checks (black, flake8, mypy)
	@echo "Running black..."
	black --check --diff .
	@echo "Running flake8..."
	flake8 . || true
	@echo "Running mypy..."
	mypy . || true

lint-fix: ## Auto-fix linting issues where possible
	@echo "Running black formatter..."
	black .
	@echo "✅ Code formatted"

format: lint-fix ## Alias for lint-fix

# Utilities
clean: ## Clean up temporary files and caches
	@echo "Cleaning temporary files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleaned up temporary files and caches"
