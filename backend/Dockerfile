# backend API と migration / seed ジョブが共用するイメージ。
# ビルドコンテキストはリポジトリルート：
#   docker build -f backend/Dockerfile -t lpk-backend .
# ACA が実行できるのは linux/amd64 イメージのみ。CI では --platform linux/amd64 を明示する。
FROM python:3.12-slim-bookworm

# ffmpeg：WebM/Opus → WAV(16kHz mono) 変換（CLAUDE.md 地雷）
# libpango* / libharfbuzz-subset0：WeasyPrint の実行時依存（フォントは app/content/fonts に同梱）
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# scripts/seed/seed_demo.py が「リポジトリルート/backend」を sys.path に挿すため、
# コンテナ内もリポジトリと同じ相対配置（/srv/backend と /srv/scripts）にする。
WORKDIR /srv/backend

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY scripts /srv/scripts

ENV PATH="/srv/backend/.venv/bin:$PATH"

RUN useradd --create-home app
USER app

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
