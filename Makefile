.PHONY: install install-dev test test-cov lint typecheck coverage clean

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

test:
	python -m pytest -v --tb=short

test-cov:
	python -m pytest -v --tb=short --cov=src/brompt --cov-report=term-missing --cov-fail-under=50

lint:
	ruff check src/brompt tests

typecheck:
	mypy src/brompt --strict
	pyright src/brompt

coverage:
	python -m pytest --cov=src/brompt --cov-report=html --cov-fail-under=50
	@echo "Coverage report: htmlcov/index.html"

clean:
	rm -rf .coverage htmlcov/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf *.egg-info/ dist/ build/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
