FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
#RUN pip install uv

COPY pyproject.toml README.md ./
COPY ./src ./src
COPY ./demo ./demo
COPY ./tests ./tests

ARG GITHUB_TOKEN
ENV GITHUB_TOKEN=${GITHUB_TOKEN}

# Configure git to use the token for private repo access
RUN if [ -n "$GITHUB_TOKEN" ]; then \
    git config --global url."https://${GITHUB_TOKEN}:x-oauth-basic@github.com".insteadOf "https://github.com"; \
    fi

RUN uv pip install --system -e .[dev]

RUN git config --global --unset-all url.https://${GITHUB_TOKEN}:x-oauth-basic@github.com.insteadof || true

CMD ["detectmate", "--help"]
