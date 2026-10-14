# DetectMate Service

DetectMate Service is a framework for building modular log processing and anomaly detection services that
communicate via [NNG](https://nng.nanomsg.org/) messaging. Each service runs one component (for example a
parser or detector from [DetectMateLibrary](https://github.com/ait-detectmate/DetectMateLibrary)), receives
data on an input socket, forwards the results to one or more output sockets, and exposes an HTTP API for
management and Prometheus metrics.

Requires Python 3.12 or newer.

## Setup

With uv (recommended):

```bash
uv sync
```

With pip and a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
```

Some library components need optional extras (`llm`, `dataframes`, `polars-rtcompat`, or `full` for all of
them), e.g. `uv sync --extra llm`. See [Installation](https://ait-detectmate.github.io/DetectMateService/latest/installation/).

## Developer setup

If you plan to contribute to the development of this package, set up the dev environment and install the
pre-commit hooks (using [prek](https://github.com/j178/prek)):

```bash
uv sync --dev
uv run --dev prek install
```

Run the tests:

```bash
uv run --dev pytest -q
```

Run the tests with coverage (add `--cov-report=html` to generate an HTML report):

```bash
uv run --dev pytest --cov=. --cov-report=term-missing
```

## Usage

### CLI

Start a service with a settings file, and optionally a component configuration file:

```bash
uv run detectmate --settings examples/service_settings.yaml
uv run detectmate --settings settings.yaml --config detector-config.yaml
```

Pass `--no-autostart` to start the service with the processing engine idle.
See [Configuration](https://ait-detectmate.github.io/DetectMateService/latest/configuration/) for all settings.

### Managing a running service

Use the `detectmate-client` tool to inspect and control a running service. `--url` (default
`http://localhost:8000`) goes **before** the command:

```bash
uv run detectmate-client --url <http_host:http_port> status       # service status and configuration
uv run detectmate-client --url <http_host:http_port> stop         # stop the processing engine
uv run detectmate-client --url <http_host:http_port> start        # start it again
uv run detectmate-client --url <http_host:http_port> metrics      # Prometheus metrics
uv run detectmate-client --url <http_host:http_port> reconfigure new-config.yaml
```

Run `uv run detectmate-client --help` for the full list of commands, including persistency and training state.

The same operations are available over the HTTP API under `/api/v1`, e.g. to shut down the entire service:

```bash
curl -X POST http://<http_host:http_port>/api/v1/shutdown
```

If the service has an API key configured (`DETECTMATE_HTTP_API_KEY`), pass it with
`detectmate-client --api-key <key>` or the `X-Auth-Token` header. See
[Usage](https://ait-detectmate.github.io/DetectMateService/latest/usage/).

### Custom services in Python

To build your own service, subclass `Service` and implement `process`:

```python
from service.core import Service
from service.settings import ServiceSettings


class DemoService(Service):
    def process(self, raw_message: bytes) -> bytes | None:
        return raw_message.upper()  # return None to drop a message


settings = ServiceSettings(
    component_name="demo",
    out_addr=["ipc:///tmp/demo.out.ipc"],
)

with DemoService(settings=settings) as service:
    service.run()  # serves the HTTP API and blocks until shutdown
```

The service receives messages on `engine_addr` (default `ipc:///tmp/detectmate.engine.ipc`) and sends each
non-`None` result to every address in `out_addr`.

### Demo pipeline with Docker Compose

The repository ships a Docker Compose stack with a complete log analysis pipeline: Fluentd ingests logs, a
DetectMate parser structures them, two detectors (`NewValueDetector` and `RuleDetector`) flag anomalies,
and Prometheus and Grafana collect the metrics.

```bash
docker compose up -d
```

The [tutorial](https://ait-detectmate.github.io/DetectMateService/latest/tutorial/) walks through the
pipeline step by step using Nginx access logs, and the
[Docker Compose reference](https://ait-detectmate.github.io/DetectMateService/latest/docker-compose/)
explains each service.

## Documentation

- [Project Documentation](https://ait-detectmate.github.io/DetectMateService/latest)

## Contribution

We're happily taking patches and other contributions. Please see the following links for how to get started:

- [Git Workflow](https://ait-detectmate.github.io/DetectMateService/latest/contribution/)
- [Development](https://ait-detectmate.github.io/DetectMateService/latest/development/)

If you encounter any bugs, please create an issue on [GitHub](https://github.com/ait-detectmate/DetectMateService/issues).

## License

[EUPL-1.2](https://github.com/ait-detectmate/DetectMateService/blob/main/LICENSE.md)
