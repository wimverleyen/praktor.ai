.PHONY: test lint benchmark install install-dev install-all docs serve-docs clean docker docker-up docker-run

# Default target
help:
	@echo "praktor.ai — development targets"
	@echo ""
	@echo "  make install       Install praktor in editable mode (uv)"
	@echo "  make install-dev   Install with dev dependencies (uv)"
	@echo "  make install-all   Install with all optional extras (uv)"
	@echo "  make test          Run test suite"
	@echo "  make lint          Run black formatter check"
	@echo "  make benchmark     Run governance benchmark suite"
	@echo "  make docs          Build mkdocs site"
	@echo "  make serve-docs    Serve docs locally (localhost:8000)"
	@echo "  make docker        Build Docker image"
	@echo "  make docker-up     Start RabbitMQ + consumer via docker compose"
	@echo "  make docker-run    Run a one-off agent in Docker"
	@echo "  make clean         Remove build artifacts and caches"

# ---- Install (uv) ----

install:
	uv pip install -e .

install-dev:
	uv pip install -e ".[dev]"

install-all:
	uv pip install -e ".[dev,presidio,kafka,minio,otel,docs]"

# ---- Test & Lint ----

test:
	uv run pytest tests/ -x -v

lint:
	uv run black --check praktor/ tests/

benchmark:
	cd praktor && uv run pytest benchmarks/ -v --tb=short

# ---- Docs ----

docs:
	uv run mkdocs build

serve-docs:
	uv run mkdocs serve

# ---- Docker ----

docker:
	docker build -t praktor .

docker-up:
	docker compose up

docker-run:
	@echo "Usage: make docker-run CMD='publish --agent thank_you --data ...'"
	docker compose run --rm praktor $(CMD)

# ---- Clean ----

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
