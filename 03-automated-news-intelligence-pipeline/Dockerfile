FROM ghcr.io/astral-sh/uv:0.12.12 AS uv

FROM python:3.13-slim-bookworm AS builder

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev --no-install-project


FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    TZ=UTC

RUN groupadd --gid 10001 application \
    && useradd --uid 10001 --gid application \
       --no-create-home --shell /usr/sbin/nologin application

WORKDIR /app

COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 config ./config
COPY --chown=10001:10001 demo ./demo
COPY --chown=10001:10001 alembic ./alembic
COPY --chown=10001:10001 alembic.ini ./

USER application

CMD ["python", "-m", "app.infrastructure.db.check"]