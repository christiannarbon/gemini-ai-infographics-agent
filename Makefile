# =========================================================================
# Makefile for Gemini AI Infographics Agent Platform
# =========================================================================
#
# Providing common development tasks: linting, formatting, tests, and hooks setup.
# Uses virtual environment (.venv) binaries if available.
#
# Usage:
#   make lint          - Run all linting checks (Ruff, djLint)
#   make format        - Automatically fix code formatting issues
#   make test          - Run python tests via pytest
#   make install-hooks - Install git pre-push hooks
# =========================================================================

.PHONY: help lint format test install-hooks check-all

# Locate virtual environment binaries if they exist, otherwise fall back to system binaries.
VENV_BIN := $(shell [ -d .venv ] && echo ".venv/bin/" || echo "")

RUFF := $(VENV_BIN)ruff
DJLINT := $(VENV_BIN)djlint
PYTEST := $(VENV_BIN)pytest

# Default target runs when you just type 'make'
help:
	@echo "Available commands:"
	@echo "  make lint          - Run ruff check and djlint template verification"
	@echo "  make format        - Run ruff format/check and djlint formatter to auto-fix styling"
	@echo "  make test          - Run tests using pytest"
	@echo "  make install-hooks - Set up the Git pre-push hook"
	@echo "  make check-all     - Run lint checks and tests together"

# Check code styling and logic issues
lint:
	@echo "Running Ruff linter..."
	$(RUFF) check .
	@echo "Checking Ruff formatting..."
	$(RUFF) format --check .
	@echo "Running djLint on Jinja2 HTML templates..."
	$(DJLINT) web/templates --check

# Format code automatically
format:
	@echo "Formatting Python code with Ruff..."
	$(RUFF) format .
	@echo "Fixing auto-fixable lint issues with Ruff..."
	$(RUFF) check --fix .
	@echo "Formatting HTML/Jinja2 templates with djLint..."
	$(DJLINT) web/templates --reformat

# Run tests
test:
	@echo "Running unit tests..."
	$(PYTEST)

# Combine linting and testing
check-all: lint test

# Install the pre-push hook into .git/hooks/
install-hooks:
	@echo "Installing Git pre-push hook..."
	@mkdir -p .git/hooks
	cp scripts/pre-push .git/hooks/pre-push
	chmod +x .git/hooks/pre-push
	@echo "Pre-push hook successfully installed!"
