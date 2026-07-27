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

## Hot-reloading the Docker Compose stack

`docker-compose.dev.yml` is an overlay for the stack from
[Docker Compose reference](docker-compose.md): it bind-mounts `./src` into
`parser`, `detector`, and `detector-rule`, and wraps each service's command
in [`watchfiles`](https://watchfiles.helpmanual.io/) (already installed as a
transitive dependency of `uvicorn[standard]`), which restarts the process
whenever a `.py` file under `src/` changes. `uv sync` already installs
`detectmateservice` in editable mode, the restarted process picks up
edits immediately without a rebuild.

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Restarting resets in-memory state (e.g. `NewValueDetector`'s learned
values) unless persistence with `auto_load` is configured — see
[Persistency Endpoints](configuration.md#persistency-endpoints).

## Updating the DetectMateLibrary version

[DetectMateLibrary](https://github.com/ait-detectmate/DetectMateLibrary) ships optional
extras (`llm`, `dataframes`, `polars-rtcompat`) that the service passes through in
`pyproject.toml`. The version is pinned in one place:
`detectmatelibrary==X.Y.Z` entry in `dependencies`. The `llm`/`dataframes`/
`polars-rtcompat` extras deliberately reference `detectmatelibrary[extra]` with no
version of their own.
1. Update the single `detectmatelibrary==X.Y.Z` pin in `pyproject.toml`.
2. Run `uv lock` to regenerate `uv.lock`.
3. Run `uv sync --extra full && uv run --dev pytest` to confirm every extra still resolves and installs correctly.


