FROM python:3.11-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/uploads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uv", "run", "--locked", "company-rag-serve", "--host", "0.0.0.0", "--port", "8000"]

