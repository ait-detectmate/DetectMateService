import time
import json
import signal
import socket
import yaml
import sys
from subprocess import Popen, PIPE, TimeoutExpired


AUDIT_LOG = "tests/library_integration/audit.log"


def free_port() -> str:
    """Return an OS-assigned free TCP port on localhost.

    Used instead of hardcoded ports so parallel test workers (pytest-
    xdist) don't race to bind the same port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return str(s.getsockname()[1])


def start_service(module_path, settings, config, settings_file, config_file):
    with open(settings_file, "w") as f:
        yaml.dump(settings, f)
    with open(config_file, "w") as f:
        yaml.dump(config, f)
    url = f"http://{settings['http_host']}:{settings['http_port']}"
    proc = Popen([sys.executable, "-m", "service.cli", "--settings",
                 str(settings_file), "--config", str(config_file)], cwd=module_path)

    max_retries = 10
    for attempt in range(max_retries):
        status = Popen([sys.executable, "-m", "service.client", "--url",
                       url, "status"], cwd=module_path, stdout=PIPE)
        stdout = status.communicate(timeout=5)
        time.sleep(1)
        try:
            data = json.loads(stdout[0])
            if data.get("status", {}).get("running"):
                break
        except json.JSONDecodeError:
            # Service may not yet be returning valid JSON; ignore and retry until max_retries is reached.
            pass
        if attempt == max_retries - 1:
            proc.terminate()
            proc.wait(timeout=5)
            raise RuntimeError(f"Service not ready within {max_retries} attempts")
        time.sleep(0.2)
    return proc, url


def cleanup_service(module_path, proc, url):
    stop = Popen([sys.executable, "-m", "service.client", "--url", url, "stop"], cwd=module_path)
    stop.communicate(timeout=5)
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=5)
    except TimeoutExpired:
        # If it doesn't exit, force kill
        proc.kill()
        proc.wait()
    except Exception:  # skip any other exception and continue testing
        pass
