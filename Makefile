.PHONY: build test test-all test-integration test-slow lint typecheck coverage clean dev precommit

# ── Build ───────────────────────────────────────────────────────────────

## Build production ARM64 image
build:
	docker buildx build --platform linux/arm64 --load \
		-t supersunho/palworld-server:latest .

## Build with no cache (full rebuild)
build-nocache:
	docker buildx build --platform linux/arm64 --load --no-cache \
		-t supersunho/palworld-server:latest .

## Quick build with target=builder (for dev testing)
build-dev:
	docker buildx build --platform linux/arm64 --load \
		--target builder -t palworld-dev:latest .

# ── Test ────────────────────────────────────────────────────────────────

## Run unit tests (fast, default)
test:
	.venv/bin/python -m pytest --tb=short -v -m "unit and not slow"

## Run full test suite (unit + integration + slow)
test-all:
	.venv/bin/python -m pytest --tb=short -v

## Run integration tests only
test-integration:
	.venv/bin/python -m pytest --tb=short -v -m "integration"

## Run slow tests only
test-slow:
	.venv/bin/python -m pytest --tb=short -v -m "slow"

## Run tests with coverage
coverage:
	.venv/bin/python -m pytest --tb=short -v --cov=src --cov-report=term-missing

## Run tests matching keyword (e.g. make test-match k=backup)
test-match:
	.venv/bin/python -m pytest --tb=short -v -k $(k)

# ── Lint ────────────────────────────────────────────────────────────────

## Lint with flake8
lint:
	.venv/bin/python -m flake8 src/ scripts/ tests/ --max-line-length=100 --per-file-ignores="src/config/base.py:F401,F811"

## Type check with mypy
typecheck:
	.venv/bin/python -m mypy src/ --ignore-missing-imports --follow-imports=silent

## Format with black
format:
	.venv/bin/python -m black src/ tests/

## Check formatting (CI gate)
fmtcheck:
	.venv/bin/python -m black --check src/ tests/

# ── Setup ───────────────────────────────────────────────────────────────

## Install dev dependencies
dev:
	.venv/bin/pip install -e '.[dev]'
	.venv/bin/pre-commit install

## Install pre-commit hooks
precommit:
	.venv/bin/pre-commit install

# ── Clean ───────────────────────────────────────────────────────────────

## Clean temporary files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -rf .pytest_cache .coverage coverage_html/
	rm -rf *.egg-info/ dist/ build/

# ── Help ────────────────────────────────────────────────────────────────

## Show all targets
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Build:"
	@echo "  build        Build production ARM64 image"
	@echo "  build-nocache Full rebuild (no cache)"
	@echo ""
	@echo "Test:"
	@echo "  test            Run unit tests (fast, default)"
	@echo "  test-all        Run full test suite (unit + integration + slow)"
	@echo "  test-integration Run integration tests only"
	@echo "  test-slow       Run slow tests only"
	@echo "  coverage        Run tests with coverage report"
	@echo "  test-match      Run tests matching keyword (k=keyword)"
	@echo ""
	@echo "Lint:"
	@echo "  lint         Run flake8"
	@echo "  typecheck    Run mypy type checker"
	@echo "  format       Format with black"
	@echo ""
	@echo "Setup:"
	@echo "  dev          Install dev dependencies"
	@echo "  precommit    Install pre-commit hooks"
	@echo ""
	@echo "Clean:"
	@echo "  clean        Remove temp files and caches"
