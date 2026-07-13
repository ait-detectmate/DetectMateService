# Installation

First, clone DetectMateService and navigate into the repository:

```bash
git clone https://github.com/ait-detectmate/DetectMateService.git
cd DetectMateService
```

## Setup with uv (recommended)

We recommend using [uv](https://github.com/astral-sh/uv) to manage the environment
and dependencies.

### 1. Download the dependencies

```bash
uv sync
```

## Alternative setup with pip

If you prefer plain `pip`, you can set things up like this instead:

```bash
# Create a virtual environment
python -m venv .venv
# Activate it
source .venv/bin/activate
# Install the project in editable mode with dev dependencies
pip install .
```

## Optional library components (extras)

[DetectMateLibrary](https://github.com/ait-detectmate/DetectMateLibrary) ships some
components (e.g. LLM-backed detectors, dataframe-based persistency backends) as
optional extras rather than hard dependencies, to keep lean installs lean. The
service exposes matching pass-through extras so you only pull in what your
configured components actually need:

| Extra              | Adds                                    | Needed for |
|---------------------|------------------------------------------|------------|
| `llm`               | `openai`, `tiktoken`, `scikit-learn`, `scipy`, `tenacity` | LLM-backed detectors/parsers |
| `dataframes`        | `pandas`, `polars`                        | Dataframe-based persistency backends and components |
| `polars-rtcompat`   | `polars[rtcompat]`                        | Polars runtime compatibility on older CPUs |
| `full`              | all of the above                          | Running any/all library components, e.g. local development |

Install only what you need:

```bash
uv sync --extra llm
# or with pip
pip install ".[llm]"
```

Or install everything:

```bash
uv sync --extra full
```

`uv sync --dev` (used for local development, see [development.md](development.md))
already installs the `full` extra via the `dev` dependency group, so
contributors get every optional component out of the box.

### Extras in Docker

`Dockerfile` and `Dockerfile-dev` take a `LIBRARY_EXTRAS` build arg (comma-separated
extras, default `full`) that controls which extras get installed in the image:

```bash
docker build --build-arg LIBRARY_EXTRAS=llm,dataframes -t detectmate .
```

With `docker compose`, set the `LIBRARY_EXTRAS` env var before building (it defaults
to `full` if unset):

```bash
LIBRARY_EXTRAS=llm docker compose build parser detector
```

