# ChangeGuard engine: FastAPI + tree-sitter + Ruff. Runs as an unprivileged user;
# analysed code is parsed, never executed.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# Dependencies first, so source edits do not invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra anthropic --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --extra anthropic --no-editable

FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 changeguard \
 && mkdir -p /data \
 && chown changeguard:changeguard /data
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CHANGEGUARD_ENV=production \
    CHANGEGUARD_DATABASE_PATH=/data/changeguard.db \
    PORT=8000
WORKDIR /data
USER changeguard
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/api/v1/health\", timeout=4)"]
# PORT is honoured for platforms that assign one (Render, Hugging Face Spaces, Fly.io).
CMD ["sh", "-c", "exec uvicorn changeguard.api.app:create_default_app --factory --host 0.0.0.0 --port \"${PORT}\" --no-server-header"]
