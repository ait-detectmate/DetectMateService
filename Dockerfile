FROM python:3.14-slim

WORKDIR /app

# Comma-separated detectmatelibrary extras to install, e.g. "llm,dataframes".
# Defaults to "full" (all optional components available). Pass an empty
# string to install only the base library.
ARG LIBRARY_EXTRAS=full

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml README.md ./
COPY ./src ./src
COPY ./tests ./tests

RUN if [ -n "$LIBRARY_EXTRAS" ]; then \
    uv pip install --system ".[$LIBRARY_EXTRAS]" ; \
    else \
    uv pip install --system . ; \
    fi

CMD ["detectmate", "--help"]
