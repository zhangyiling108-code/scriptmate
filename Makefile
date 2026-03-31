PYTHON ?= python3
VENV ?= .venv
ACTIVATE = . $(VENV)/bin/activate

.PHONY: bootstrap install init doctor help test

bootstrap:
	bash scripts/bootstrap.sh

install:
	$(PYTHON) -m pip install -e .[dev]

init:
	$(ACTIVATE) && scriptmate init --config config.toml

doctor:
	$(ACTIVATE) && scriptmate doctor --config config.toml

help:
	$(ACTIVATE) && scriptmate --help

test:
	$(ACTIVATE) && python -m pytest tests -q
