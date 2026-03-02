FROM python:3.12-slim

WORKDIR /app
ARG DETECTMATELIBRARY_BRANCH=main

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

RUN if [ "$DETECTMATELIBRARY_BRANCH" != "main" ]; then \
        uv pip uninstall --system detectmatelibrary && \
        uv pip install --system "detectmatelibrary @ git+https://github.com/ait-detectmate/DetectMateLibrary.git@$DETECTMATELIBRARY_BRANCH" ; \
    fi

CMD ["detectmate", "--help"]
