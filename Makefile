.PHONY: setup index submit eval-a eval-b live-smoke live-stress dashboard lint test clean help

LIVE_COMBOS ?= a,nvidia
LIVE_STRESS_COMBO ?= nvidia
LIVE_STRESS_TASK ?= task_08_cache_transport
LIVE_STAGES ?= planning,context_ranking,error_parsing,test_analysis,llm_review

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and clone httpx
	pip install -e ".[dev]"
	@if [ ! -d "./target/httpx" ]; then \
		git clone https://github.com/encode/httpx ./target/httpx; \
		cd ./target/httpx && git checkout 0.28.1; \
	else \
		echo "httpx already cloned"; \
	fi
	cp -n .env.example .env 2>/dev/null || true
	@echo "\n✅ Setup complete. Edit .env with your API keys."

index: ## Build tree index from target codebase
	python -m src index --path ./target/httpx

submit: ## Submit a single task (usage: make submit TASK="your task here")
	python -m src submit "$(TASK)"

eval-a: ## Run offline fixture eval benchmark with Combo A
	python -m src eval --combo a

eval-b: ## Run offline fixture eval benchmark with Combo B
	python -m src eval --combo b

live-smoke: ## API-key required: smoke live provider routing
	@if ! { [ -n "$$GOOGLE_API_KEY$$ANTHROPIC_API_KEY$$GROQ_API_KEY$$NVIDIA_API_KEY" ] || grep -Eq '^(GOOGLE_API_KEY|ANTHROPIC_API_KEY|GROQ_API_KEY|NVIDIA_API_KEY)=[^[:space:]]+' .env 2>/dev/null; }; then \
		echo "ERROR: make live-smoke requires a real provider API key in env or .env"; \
		echo "Set GOOGLE_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY, or NVIDIA_API_KEY."; \
		exit 1; \
	fi
	uv run python -m src provider-smoke --combos "$(LIVE_COMBOS)" --stages "$(LIVE_STAGES)" --output reports/provider_stage_smoke_live.json

live-stress: ## API-key required: run the 3+ file live stress benchmark task
	@if ! { [ -n "$$GOOGLE_API_KEY$$ANTHROPIC_API_KEY$$GROQ_API_KEY$$NVIDIA_API_KEY" ] || grep -Eq '^(GOOGLE_API_KEY|ANTHROPIC_API_KEY|GROQ_API_KEY|NVIDIA_API_KEY)=[^[:space:]]+' .env 2>/dev/null; }; then \
		echo "ERROR: make live-stress requires a real provider API key in env or .env"; \
		echo "Set GOOGLE_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY, or NVIDIA_API_KEY."; \
		exit 1; \
	fi
	uv run python -m src eval --combo "$(LIVE_STRESS_COMBO)" --live --tasks "$(LIVE_STRESS_TASK)" --path ./target/httpx --output reports/combo_$(LIVE_STRESS_COMBO)_live_stress.json

dashboard: ## Launch the Rich terminal dashboard
	python -m src dashboard

lint: ## Run ruff + mypy on source
	ruff check src/ tests/
	mypy src/

test: ## Run pytest with coverage
	pytest tests/ -v --cov=src --cov-report=term-missing

clean: ## Remove caches and generated files
	rm -rf .cache/ logs/ eval/results/ __pycache__ .mypy_cache .ruff_cache .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleaned."
