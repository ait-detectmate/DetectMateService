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


## Developer setup

For development, you can install with optional dependencies:

```bash
uv sync --dev
```

We recommend using [`prek`](https://github.com/j178/prek) to manage Git
pre-commit hooks. `prek` is configured via the existing `.pre-commit-config.yaml`
and can be installed as part of the `dev` extras. To ensure pre-commit hooks run before each commit, run:
```bash
uv run prek install
```
