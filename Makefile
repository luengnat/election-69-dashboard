# Thai Election Ballot OCR - Makefile
# Common development tasks

.PHONY: help install test lint run clean

# Default target
help:
	@echo "Available targets:"
	@echo "  install    - Install dependencies"
	@echo "  test       - Run all tests"
	@echo "  lint       - Run linters (ruff)"
	@echo "  run        - Start the web UI"
	@echo "  clean      - Remove generated files"
	@echo "  ci         - Run CI checks (lint + test)"

# Install dependencies
install:
	pip install -r requirements.txt

# Run all tests
test:
	python test_executive_summary_pdf.py
	python test_constituency_pdf.py
	python test_batch_pdf_charts.py
	python test_pdf_generation.py

# Run accuracy tests (requires API keys)
test-accuracy:
	python tests/test_accuracy.py --all

# Run linters
lint:
	@which ruff > /dev/null || pip install ruff
	ruff check . --ignore E501 --ignore F401 --ignore F841 --statistics || true

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
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -delete

# Full CI check
ci: lint test
	@echo "CI checks passed!"

# Format code
format:
	@which ruff > /dev/null || pip install ruff
	ruff format .

# Development setup
dev: install
	pip install ruff pyright
	@echo "Development environment ready!"
