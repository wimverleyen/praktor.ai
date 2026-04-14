.PHONY: test lint benchmark install install-dev install-all docs serve-docs clean

# Default target
help:
	@echo "praktor.ai — development targets"
	@echo ""
	@echo "  make install       Install praktor in editable mode"
	@echo "  make install-dev   Install with dev dependencies"
	@echo "  make install-all   Install with all optional extras"
	@echo "  make test          Run test suite"
	@echo "  make lint          Run black formatter check"
	@echo "  make benchmark     Run governance benchmark suite"
	@echo "  make docs          Build mkdocs site"
	@echo "  make serve-docs    Serve docs locally (localhost:8000)"
	@echo "  make clean         Remove build artifacts and caches"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

install-all:
	pip install -e ".[dev,presidio,kafka,minio,otel,docs]"

test:
	python3 -m pytest tests/ -x -v

lint:
	black --check praktor/ tests/

benchmark:
	cd praktor && python3 -m pytest benchmarks/ -v --tb=short

docs:
	mkdocs build

serve-docs:
	mkdocs serve

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
