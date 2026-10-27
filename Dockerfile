FROM python:3.12-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:0.10.1 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache \
    MINIKV_DATA_FILE=/data/data.json

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project

COPY src ./src
RUN uv sync --locked

RUN addgroup --system minikv \
    && adduser --system --ingroup minikv --no-create-home minikv \
    && mkdir /data \
    && chown minikv:minikv /data \
    && chown -R minikv:minikv /tmp/uv-cache

USER minikv

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
