# Service Prototype

This project demonstrates a basic `Service` class designed to be inherited by other specialized components.

### Developer setup:

Set up the dev environment and install pre-commit hooks:

```bash
uv pip install -e .[dev]
pre-commit install
```

Run the tests:

```bash
uv run pytest -q
```

Run the tests with coverage (add `--cov-report=html` to generate an HTML report):

```bash
uv run pytest --cov=. --cov-report=term-missing
```
