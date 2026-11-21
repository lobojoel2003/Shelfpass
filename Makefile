# Common development tasks. Requires uv (https://docs.astral.sh/uv/).
.PHONY: help install dev demo test lint format check dataset bundle build docker

export SHELFPASS_DEBUG ?= 1

help:  ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Install the app and dev tools into .venv
	uv sync --all-groups

dev: install  ## Run the development server on http://127.0.0.1:8000
	uv run python manage.py migrate
	uv run python manage.py sync_dataset
	uv run python manage.py runserver

demo: install  ## SQLite database with fictional demo data (login demo / shelfpass-demo)
	uv run python manage.py migrate -v 0
	uv run python manage.py seed_demo --reset
	uv run python manage.py runserver

test:  ## Run the test suite with coverage
	uv run pytest --cov

lint:  ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format:  ## Auto-format the code
	uv run ruff check --fix .
	uv run ruff format .

check: lint test dataset  ## Everything CI runs (except Docker)
	uv run python manage.py makemigrations --check --dry-run

dataset:  ## Validate the open dataset
	uv run python manage.py sync_dataset --check

bundle:  ## Build the dataset release bundle into dist/
	uv run python scripts/build_dataset_bundle.py --out dist

build:  ## Build the Python sdist and wheel into dist/
	uv build

docker:  ## Build the container image as shelfpass:dev
	docker build -t shelfpass:dev \
	  --build-arg VERSION=$$(uv run python -c 'import shelfpass; print(shelfpass.__version__)') \
	  --build-arg BUILD_NUMBER=$$(git rev-list --count HEAD) \
	  --build-arg GIT_SHA=$$(git rev-parse HEAD) .
