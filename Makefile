# Agent Swarm — Deployment Makefile
# Usage: make up | make down | make logs | make infra | make build
#
# Layered compose:
#   Phase 1: infra      (RabbitMQ, Redis, Postgres, Gatekeeper)
#   Phase 2: conductor  (Orchestrator + Web UI)
#   Phase 3: agents     (Superintendent, Mercury, Sapper, DaVinci)
#   Phase 4: observers  (Monitor, Scribe, Judge)
#   Phase 5: monitoring (Prometheus, Grafana)

COMPOSE_INFRA      = -f docker-compose.infra.yml
COMPOSE_CONDUCTOR  = $(COMPOSE_INFRA) -f docker-compose.conductor.yml
COMPOSE_AGENTS     = $(COMPOSE_CONDUCTOR) -f docker-compose.agents.yml
COMPOSE_OBSERVERS  = $(COMPOSE_AGENTS) -f docker-compose.observers.yml
COMPOSE_FULL       = $(COMPOSE_OBSERVERS) -f docker-compose.monitoring.yml

.PHONY: help infra conductor agents observers up down restart build logs ps clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ==================== LAYERED STARTUP ====================

infra: ## Start Phase 1: shared infrastructure
	docker compose $(COMPOSE_INFRA) up -d

conductor: ## Start Phase 1+2: infra + conductor
	docker compose $(COMPOSE_CONDUCTOR) up -d

agents: ## Start Phase 1-3: infra + conductor + subagents
	docker compose $(COMPOSE_AGENTS) up -d

observers: ## Start Phase 1-4: infra + conductor + agents + observers
	docker compose $(COMPOSE_OBSERVERS) up -d

up: ## Start full stack (all 5 phases)
	docker compose $(COMPOSE_FULL) up -d

# ==================== MANAGEMENT ====================

down: ## Stop all services
	docker compose $(COMPOSE_FULL) down

restart: down up ## Restart full stack

build: ## Build all agent images
	docker compose $(COMPOSE_FULL) build

build-no-cache: ## Build all agent images without cache
	docker compose $(COMPOSE_FULL) build --no-cache

ps: ## Show running services
	docker compose $(COMPOSE_FULL) ps

logs: ## Tail logs for all services
	docker compose $(COMPOSE_FULL) logs -f --tail=50

logs-conductor: ## Tail conductor logs
	docker compose $(COMPOSE_CONDUCTOR) logs -f conductor --tail=100

logs-agents: ## Tail subagent logs
	docker compose $(COMPOSE_AGENTS) logs -f superintendent mercury sapper davinci --tail=100

logs-observers: ## Tail observer logs
	docker compose $(COMPOSE_OBSERVERS) logs -f monitor scribe judge --tail=100

# ==================== UTILITIES ====================

health: ## Check health of all agents
	@echo "=== Agent Health ==="
	@for port in 8000 8001 8002 8003 8004 8005 8006 8007; do \
		printf "  port $$port: "; \
		curl -sf http://localhost:$$port/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent','conductor'), '-', d.get('status','?'))" 2>/dev/null || echo "DOWN"; \
	done

shell-%: ## Open a shell in a container (e.g., make shell-conductor)
	docker compose $(COMPOSE_FULL) exec $* sh

clean: ## Remove all volumes (DESTRUCTIVE)
	@echo "This will delete ALL swarm data (Postgres, Redis, RabbitMQ, Grafana)."
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] && \
		docker compose $(COMPOSE_FULL) down -v || echo "Aborted."

env: ## Create .env from example if it doesn't exist
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example — edit it with real values")
	@test -f .env && echo ".env exists"
