.PHONY: help up down build logs \
	lint lint-backend lint-frontend \
	format \
	test test-backend test-frontend \
	migrate migration \
	check

help:
	@echo "Targets:"
	@echo "  make up              - docker compose up --build"
	@echo "  make down            - docker compose down"
	@echo "  make logs            - tail backend logs"
	@echo "  make lint            - ruff check + tsc --noEmit"
	@echo "  make format          - ruff format (backend)"
	@echo "  make test            - backend pytest + frontend build check"
	@echo "  make migrate         - alembic upgrade head"
	@echo "  make migration m=... - alembic revision --autogenerate -m \"...\""
	@echo "  make check           - lint + test (what CI runs)"

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f backend

lint: lint-backend lint-frontend

# ruff isn't in requirements.txt / the backend image (CI installs it on the
# runner via `pip install ruff`); run it the same way here against the host
# checkout. Install once with: pip install ruff
lint-backend:
	ruff check backend/
	ruff format --check backend/

lint-frontend:
	cd frontend && npm run lint

format:
	ruff format backend/

test: test-backend test-frontend

test-backend:
	docker compose run --rm backend pytest -q

test-frontend:
	cd frontend && npm run build

migrate:
	docker compose run --rm backend alembic upgrade head

migration:
	docker compose run --rm backend alembic revision --autogenerate -m "$(m)"

check: lint test
