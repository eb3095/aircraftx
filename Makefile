PYTHON ?= python3
VENV ?= .venv
PIP = $(VENV)/bin/pip
PY = $(VENV)/bin/python
PACKAGE = aircraftx

.PHONY: help venv dev-install install run format format-check test build publish clean

help:
	@echo "AircraftX development targets:"
	@echo "  make venv          Create virtualenv"
	@echo "  make dev-install   Editable install with dev deps (black, pytest, build, twine)"
	@echo "  make install       Install aircraftx CLI into venv"
	@echo "  make run           Run from source via start.sh (no pip install)"
	@echo "  make format        Format code with black"
	@echo "  make format-check  Verify formatting (CI)"
	@echo "  make test          Run unit tests"
	@echo "  make build         Build sdist + wheel"
	@echo "  make publish       Upload dist/* to PyPI (requires TWINE_* creds)"
	@echo "  make clean         Remove build artifacts"

venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip

dev-install: venv
	$(PIP) install -e ".[dev]"

install: venv
	$(PIP) install -e .

run:
	./start.sh

format:
	$(PY) -m black $(PACKAGE) tests

format-check:
	$(PY) -m black --check $(PACKAGE) tests

test:
	$(PY) -m pytest tests/ -v

build: dev-install
	$(PY) -m build

publish: build
	$(PY) -m twine upload dist/*

clean:
	rm -rf build dist *.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
