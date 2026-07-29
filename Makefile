.PHONY: help install test cov lint format type pre-commit pre-commit-install build check publish-test publish clean all

help:
	@echo "install              Install dependencies"
	@echo "test                 Run pytest"
	@echo "cov                  Run pytest with coverage"
	@echo "lint                 Run ruff check"
	@echo "format               Run ruff format"
	@echo "type                 Run mypy"
	@echo "pre-commit           Run pre-commit on all files"
	@echo "pre-commit-install   Install pre-commit hooks"
	@echo "build                Build package"
	@echo "check                Build and check dist with twine"
	@echo "publish-test         Publish to TestPyPI"
	@echo "publish              Publish to PyPI"
	@echo "clean                Remove generated files"
	@echo "all                  Run lint, type, tests, build and check"

install:
	poetry install

test:
	poetry run pytest

cov:
	poetry run pytest --cov=strict_abc --cov-report=term-missing --cov-report=html --cov-fail-under=90

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

type:
	poetry run mypy

pre-commit:
	poetry run pre-commit run --all-files

pre-commit-install:
	poetry run pre-commit install

build:
	poetry build

check: build
	poetry run twine check dist/*

publish-test:
	poetry publish -r testpypi --build

publish:
	poetry publish --build

clean:
	rm -rf dist build htmlcov .coverage coverage.xml .pytest_cache .mypy_cache .ruff_cache

all: lint type test build check