FROM python:3.14-slim

WORKDIR /app

# Comma-separated detectmatelibrary extras to install, e.g. "llm,dataframes".
# Defaults to "full" (all optional components available). Pass an empty
# string to install only the base library.
ARG LIBRARY_EXTRAS=full

# Install into the system site-packages instead of a
# .venv, so `detectmate`/`python` still work without activating anything.
ENV UV_PROJECT_ENVIRONMENT=/usr/local

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./

# --locked asserts uv.lock is up to date with pyproject.toml; the build
# fails instead of silently re-resolving if the lock is stale.
# --no-install-project installs only third-party dependencies,
# so this layer stays cached if the project code changes but dependencies don't.
RUN if [ -n "$LIBRARY_EXTRAS" ]; then \
    uv sync --locked --no-dev --no-install-project --extra "$LIBRARY_EXTRAS" ; \
    else \
    uv sync --locked --no-dev --no-install-project ; \
    fi

COPY ./src ./src
COPY ./tests ./tests

# dependencies are already installed above, so this is fast.
RUN if [ -n "$LIBRARY_EXTRAS" ]; then \
    uv sync --locked --no-dev --extra "$LIBRARY_EXTRAS" ; \
    else \
    uv sync --locked --no-dev ; \
    fi

CMD ["detectmate", "--help"]
