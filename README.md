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


### Usage

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
        for cmd in ("ping", "status", "pause", "status", "resume", "status", "stop"):
            print(f">>> {cmd}")
            req.send(cmd.encode("utf-8"))
            reply = req.recv().decode("utf-8", "ignore")
            print(f"<<< {reply}")
```
