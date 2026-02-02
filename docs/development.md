# Development

## Setup

For development, you can install with optional dependencies:

```bash
uv sync --dev
```

We are insisting to use [`prek`](https://github.com/j178/prek) to run basic checks at commit time.
`prek` is configured via the existing `.pre-commit-config.yaml`
and can be installed as part of the `dev` extras. To ensure pre-commit hooks run before each commit, run:
```bash
uv run prek install
```

