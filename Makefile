.PHONY: dev backend frontend test lint migrate db

# make が無い環境では README の直接コマンドを使う。
dev:
	@echo "Run 'make backend' and 'make frontend' in separate terminals (see README)."

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8001

frontend:
	cd frontend && pnpm dev

db:
	docker compose up -d db

test:
	cd backend && uv run pytest
	cd frontend && pnpm build

lint:
	cd backend && uv run ruff check
	cd frontend && pnpm lint

migrate:
	cd backend && uv run alembic upgrade head
