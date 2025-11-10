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

RUN uv pip install --system -e .

CMD ["detectmate", "--help"]
