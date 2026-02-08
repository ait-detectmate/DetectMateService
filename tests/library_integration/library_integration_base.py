import time
import json
import signal
import yaml
import sys
from subprocess import Popen, PIPE, TimeoutExpired


def start_service(module_path, settings, config, settings_file, config_file):
    with open(settings_file, "w") as f:
        yaml.dump(settings, f)
    with open(config_file, "w") as f:
        yaml.dump(config, f)
    url = f"http://{settings["http_host"]}:{settings["http_port"]}"
    proc = Popen([sys.executable, "-m", "service.cli", "--settings", str(settings_file), "--config", str(config_file)], cwd=module_path)

    max_retries = 10
    for attempt in range(max_retries):
        status = Popen([sys.executable, "-m", "service.client", "--url", url, "status"], cwd=module_path, stdout=PIPE)
        stdout = status.communicate(timeout=5)
        time.sleep(1)
        try:
            data = json.loads(stdout[0])
            if data.get("status", {}).get("running"):
                break
        except json.JSONDecodeError:
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
    except Exception:
        pass
