# Development

This section describes how to setup a development environment and how to contribute to `DetectMateService`.

!!! note

    Read the [Contribution Guide](contribution.md) to follow and understand the development workflow.


## Setup a development environment

For development we recommend using [uv](https://docs.astral.sh/uv/). You can install all optional dependencies:

```bash
uv sync --dev
```

*Please note that this step is not necessary. `uv run --dev` will automatically download all dependencies.*


## Use prek to run code checks

Every code contributer must use [`prek`](https://github.com/j178/prek) to run basic checks at commit time.
`prek` is configured via the existing `.pre-commit-config.yaml`
and can be installed as part of the `dev` extras. To ensure pre-commit hooks run before each commit, run:

```bash
uv run prek install
```

To run the checks manually, you can execute:

```bash
uv run prek run -a
```

## Add tests and run pytest

In oder to run the tests run the following command:

```bash
uv run --dev pytest
```

## Updating the DetectMateLibrary version

[DetectMateLibrary](https://github.com/ait-detectmate/DetectMateLibrary) ships optional
extras (`llm`, `dataframes`, `polars-rtcompat`) that the service passes through in
`pyproject.toml`. The version is pinned in exactly **one place** — the base
`detectmatelibrary==X.Y.Z` entry in `dependencies`. The `llm`/`dataframes`/
`polars-rtcompat` extras deliberately reference `detectmatelibrary[extra]` with no
version of their own; since it's the same package name, uv/pip unify them onto
whatever version the base pin specifies. When bumping the library version:

1. Update the single `detectmatelibrary==X.Y.Z` pin in `pyproject.toml`.
2. Run `uv lock` to regenerate `uv.lock`.
3. Run `uv sync --extra full && uv run --dev pytest` to confirm every extra still resolves and installs correctly.

`Dockerfile`, `Dockerfile-dev`, and `scripts/change_toml.sh` don't hardcode the
library version either, so they don't need touching for a version bump.
