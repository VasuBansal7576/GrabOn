.PHONY: setup index submit eval-a eval-b dashboard lint test clean help

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

eval-a: ## Run eval benchmark with Combo A (Gemini Flash baseline)
	python -m src eval --combo a

eval-b: ## Run eval benchmark with Combo B (Haiku + Sonnet)
	python -m src eval --combo b

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
