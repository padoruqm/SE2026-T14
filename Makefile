.DEFAULT_GOAL := help
.PHONY: help dev test lint

PYTHON ?= python3
BACKEND_ENV = PYTHONPATH=backend

help:
	@printf '%s\n' 'Available targets: dev, test, lint'
	@printf '%s\n' 'dev: run the FastAPI backend on http://127.0.0.1:8000'
	@printf '%s\n' 'test: run backend unit/API tests'
	@printf '%s\n' 'lint: check Python syntax and whitespace errors'

dev:
	$(BACKEND_ENV) $(PYTHON) -m uvicorn app.main:app --reload

test:
	$(BACKEND_ENV) $(PYTHON) -m unittest discover -s backend/tests -v

lint:
	$(PYTHON) -m compileall -q backend/app backend/tests
	git diff --check
