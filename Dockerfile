FROM python:3.14.5-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

RUN python -m pip install --no-cache-dir uv==0.9.5
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY data ./data
RUN uv sync --frozen --no-dev

USER 10001:10001
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app/src
