# DetectMate Service

DetectMate Service is a framework for building modular services that communicate via NNG messaging.

## Setup

With uv (recommended):

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

With pip and virtualenv:

```bash
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Developer setup

If you plan to contribute to the development of this package, follow these steps to set up the dev environment and install pre-commit hooks (using [prek](https://github.com/j178/prek))

```bash
uv pip install -e .[dev]
prek install
```

Run the tests:

```bash
uv run pytest -q
```

Run the tests with coverage (add `--cov-report=html` to generate an HTML report):

```bash
uv run pytest --cov=. --cov-report=term-missing
```


## Usage

To use the `Service` class, you can create a subclass that implements the `process` method. Here's an example:

```python
import pynng
from service.core import Service

class DemoService(Service):
    def process(self, raw_message: bytes) -> bytes | None:
        return None  # No actual processing in this demo

service = DemoService()

with service:
    with pynng.Req0(dial=service.settings.manager_addr) as req:
        for cmd in ("ping", "status", "stop"):
            print(f">>> {cmd}")
            req.send(cmd.encode("utf-8"))
            reply = req.recv().decode("utf-8", "ignore")
            print(f"<<< {reply}")
```

### CLI

You can also run the service using the command line interface (CLI).
It takes configuration files as arguments:

Example configuration files can be found in the `tests/config` directory.

Start the service:

```bash
detectmate start --settings tests/config/service_settings.yaml
```

Get the service status:

```bash
detectmate status --settings tests/config/service_settings.yaml
```

Stop the service:

```bash
detectmate stop --settings tests/config/service_settings.yaml
```


### Demo pipeline run with Docker

A containerized demonstration of the DetectMate log analysis pipeline. The demo runs three services (reader, parser,
detector) that process audit logs to detect anomalies, with a test script that feeds log lines through the complete
pipeline and reports detected anomalies.

**Terminal 1** (keep running to see service logs):
```bash
docker compose up reader parser detector
```

**Terminal 2** (run after services are up):
```bash
# Wait a few seconds for services to be ready, then:
docker compose up demo
```
