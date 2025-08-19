# Makefile for RSSBrew development tasks

.PHONY: help install install-dev format lint typecheck test clean migrate run run-huey shell docker-up docker-down

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -r requirements.txt

install-dev: install ## Install development dependencies
	pip install -r requirements-dev.txt
	pre-commit install
	python manage.py migrate
	python manage.py init_server

format: ## Format code with ruff and djlint
	ruff format .
	ruff check --fix .
	djlint --reformat FeedManager/templates/ templates/ --extension html || true

lint: ## Run all linters
	ruff check .
	djlint FeedManager/templates/ templates/ --extension html --lint || true
	python manage.py check

typecheck: ## Run type checking with mypy (requires mypy installation)
	@which mypy > /dev/null || (echo "Installing mypy..." && pip install mypy django-stubs)
	mypy FeedManager/ rssbrew/ manage.py || true

test: ## Run Django tests
	python manage.py test

test-verbose: ## Run Django tests with verbose output
	python manage.py test --verbosity=2

test-coverage: ## Run tests with coverage report
	coverage run --source='.' manage.py test
	coverage report
	coverage html

test-translations: ## Test translations
	python manage.py test_translations

clean: ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	find . -type f -name ".DS_Store" -delete
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/

migrate: ## Run database migrations
	python manage.py migrate

makemigrations: ## Create new migrations
	python manage.py makemigrations

createsuperuser: ## Create a superuser
	python manage.py createsuperuser

collectstatic: ## Collect static files
	python manage.py collectstatic --noinput

run: ## Run development server
	python manage.py runserver

run-huey: ## Run Huey task queue
	python manage.py run_huey

shell: ## Open Django shell
	python manage.py shell

shell-plus: ## Open Django shell_plus (if django-extensions is installed)
	python manage.py shell_plus || python manage.py shell

update-feeds: ## Update all feeds manually
	python manage.py update_feeds

generate-digest: ## Generate digest for all feeds
	python manage.py generate_digest

clean-articles: ## Clean old articles
	python manage.py clean_old_articles

translate-make: ## Generate translation files
	python manage.py makemessages -l zh_Hans --no-location

translate-compile: ## Compile translation messages
	python manage.py compilemessages

init-server: ## Initialize server with default superuser
	python manage.py init_server

docker-up: ## Start Docker containers
	docker-compose up -d

docker-down: ## Stop Docker containers
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f rssbrew

docker-build: ## Rebuild Docker images
	docker-compose build

docker-shell: ## Open shell in Docker container
	docker-compose exec rssbrew bash

pre-commit: ## Run pre-commit hooks on all files
	pre-commit run --all-files

check-all: lint typecheck test ## Run all checks (lint, typecheck, test)

dev-setup: install-dev ## Full development setup (includes migrate and init_server)

reset-db: ## Reset database (WARNING: destroys all data)
	rm -f data/db.sqlite3
	python manage.py migrate
	python manage.py init_server

requirements-update: ## Update requirements.txt with current packages
	pip freeze > requirements.txt
