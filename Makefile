# Thai Election Ballot OCR - Makefile
# Common development tasks

.PHONY: help install test lint run clean coverage

# Default target
help:
	@echo "Available targets:"
	@echo "  install       - Install dependencies"
	@echo "  test          - Run all tests"
	@echo "  test-unit     - Run unit tests only"
	@echo "  test-pdf      - Run PDF generation tests"
	@echo "  test-accuracy - Run accuracy tests (requires API keys)"
	@echo "  coverage      - Run tests with coverage report"
	@echo "  lint          - Run linters (ruff)"
	@echo "  format        - Format code with ruff"
	@echo "  typecheck     - Run type checker (pyright)"
	@echo "  run           - Start the web UI (localhost)"
	@echo "  run-external  - Start web UI with external access"
	@echo "  clean         - Remove generated files"
	@echo "  ci            - Run CI checks (lint + test)"

# Install dependencies
install:
	pip install -r requirements.txt

# Install development dependencies
install-dev:
	pip install -r requirements.txt
	pip install pytest pytest-cov ruff pyright pre-commit
	@echo "Development environment ready!"

# Run unit tests
test-unit:
	python tests/test_unit.py -v

# Run PDF generation tests
test-pdf:
	python test_executive_summary_pdf.py
	python test_constituency_pdf.py
	python test_batch_pdf_charts.py
	python test_pdf_generation.py

# Run all tests
test: test-unit test-pdf
	@echo "All tests passed!"

# Run accuracy tests (requires API keys)
test-accuracy:
	python tests/test_accuracy.py --all

# Run tests with coverage
coverage:
	@which pytest > /dev/null || pip install pytest pytest-cov
	pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html
	@echo "Coverage report generated in htmlcov/"

# Run linters
lint:
	@which ruff > /dev/null || pip install ruff
	ruff check . --statistics || true

# Format code
format:
	@which ruff > /dev/null || pip install ruff
	ruff format .
	ruff check . --fix || true

# Run type checker
typecheck:
	@which pyright > /dev/null || pip install pyright
	pyright --ignoreexternal --warnings *.py 2>/dev/null || true

# Start web UI (localhost only for security)
run:
	python web_ui.py

# Start web UI with external access
run-external:
	WEB_UI_HOST=0.0.0.0 python web_ui.py

# Clean generated files
clean:
	rm -rf reports_test/*.pdf
	rm -rf reports_test/*.json
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf .coverage
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -delete

# Full CI check
ci: lint test
	@echo "CI checks passed!"

# Development setup
dev: install-dev
	@echo "Run 'pre-commit install' to set up git hooks"
