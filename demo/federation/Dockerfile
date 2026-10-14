# Service image for the federation demo.
# Build context is the repository root (see docker-compose.yml).
FROM python:3.14-slim

# Optional DetectMateLibrary git branch or tag; empty uses the uv.lock version.
ARG LIBRARY_REF=

ENV UV_PROJECT_ENVIRONMENT=/usr/local

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY ./src ./src
RUN uv sync --locked --no-dev --extra dataframes

# Replace the locked library with the requested git ref, if any. Containers
# run `detectmate` directly, not `uv run`, so this is not synced away again.
RUN if [ -n "$LIBRARY_REF" ]; then \
        uv pip install --system --reinstall-package detectmatelibrary \
        "detectmatelibrary[dataframes] @ git+https://github.com/ait-detectmate/DetectMateLibrary@${LIBRARY_REF}"; \
    fi

CMD ["detectmate", "--help"]
