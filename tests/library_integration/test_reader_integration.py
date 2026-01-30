"""Integration tests for the Service CLI with LogFileReader.

Tests verify log reading via engine socket.
"""
import time
from pathlib import Path
from subprocess import Popen
from typing import Generator

import pytest
import pynng
import yaml
import sys
import os

from detectmatelibrary.schemas import LogSchema


# fixtures and configuration
@pytest.fixture(scope="session")
def test_log_file() -> Path:
    """Return path to the test log file in this folder."""
    return Path(__file__).parent / "test_logs.log"


@pytest.fixture
def running_service(tmp_path: Path, test_log_file: Path) -> Generator[dict, None, None]:
    """Start the service with test config and yield connection info."""

    timestamp = int(time.time() * 1000)
    module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Create settings and config
    settings = {
        "component_type": "readers.log_file.LogFileReader",
        "component_config_class": "readers.log_file.LogFileConfig",
        "component_name": "test-reader",
        "manager_addr": f"ipc:///tmp/test_reader_cmd_{timestamp}.ipc",
        "engine_addr": f"ipc:///tmp/test_reader_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": False,
        "log_to_file": False,
        "engine_autostart": True,
    }

    config = {
        "readers": {
            "File_reader": {
                "method_type": "log_file_reader",
                "auto_config": False,
                "params": {
                    "file": str(test_log_file)
                }
            }
        }
    }

    # Write YAML files
    settings_file = tmp_path / "reader_settings.yaml"
    config_file = tmp_path / "reader_config.yaml"
    with open(settings_file, "w") as f:
        yaml.dump(settings, f)
    with open(config_file, "w") as f:
        yaml.dump(config, f)

    # Start service
    proc = Popen(
        [sys.executable, "-m", "service.cli", "start",
         "--settings", str(settings_file),
         "--config", str(config_file)],
        cwd=module_path,
    )

    time.sleep(0.5)

    service_info = {
        "process": proc,
        "manager_addr": settings["manager_addr"],
        "engine_addr": settings["engine_addr"],
    }

    # Verify service is running
    max_retries = 5
    for attempt in range(max_retries):
        try:
            with pynng.Req0(dial=service_info["manager_addr"], recv_timeout=2000) as sock:
                sock.send(b"ping")
                if sock.recv().decode() == "pong":
                    break
        except Exception:
            if attempt == max_retries - 1:
                proc.terminate()
                proc.wait(timeout=5)
                raise RuntimeError("Service did not start within timeout")
            time.sleep(0.5)

    yield service_info

    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait()


# Tests
class TestReaderServiceInitialization:
    """Tests for service startup and configuration."""

    def test_service_starts_successfully(self, running_service: dict) -> None:
        """Verify the service starts and is responsive to ping."""
        manager_addr = running_service["manager_addr"]

        with pynng.Req0(dial=manager_addr, recv_timeout=2000) as sock:
            sock.send(b"ping")
            reply = sock.recv().decode()
            assert reply == "pong", "Service should respond to ping"


class TestReaderServiceViaEngine:
    """Tests for reading logs via the engine socket."""

    def test_engine_socket_connection(self, running_service: dict) -> None:
        """Verify we can connect to the engine socket."""
        engine_addr = running_service["engine_addr"]

        with pynng.Pair0(dial=engine_addr, recv_timeout=3000) as socket:
            assert socket is not None, "Should successfully connect to engine socket"

    def test_single_read_returns_log_data(self, running_service: dict) -> None:
        """Verify a single read request returns valid log data."""
        engine_addr = running_service["engine_addr"]

        with pynng.Pair0(dial=engine_addr, recv_timeout=3000) as socket:
            socket.send(b"read")
            response = socket.recv()

            assert len(response) > 0, "Should receive non-empty response"

            # Verify it can be deserialized as LogSchema
            (log_schema := LogSchema()).deserialize(response)
            assert hasattr(log_schema, "log"), "LogSchema should have log attribute"
            assert hasattr(log_schema, "logID"), "LogSchema should have logID attribute"

    def test_multiple_reads_return_different_logs(self, running_service: dict) -> None:
        """Verify multiple reads return different log entries."""
        engine_addr = running_service["engine_addr"]

        logs = []

        with pynng.Pair0(dial=engine_addr, recv_timeout=3000) as socket:
            for _ in range(3):
                socket.send(b"read")
                response = socket.recv()

                (log_schema := LogSchema()).deserialize(response)
                logs.append({
                    "log": log_schema.log,
                    "logID": log_schema.logID,
                })

        assert len(logs) == 3, "Should receive 3 log entries"

        # Verify logs are different
        log_texts = [log["log"] for log in logs]
        assert len(set(log_texts)) == 3, "Each read should return a different log entry"

        # Verify log IDs increment
        log_ids = [log["logID"] for log in logs]
        assert log_ids[1] == log_ids[0] + 1
        assert log_ids[2] == log_ids[1] + 1

    def test_log_contains_expected_content(self, running_service: dict) -> None:
        """Verify returned logs contain expected audit log content."""
        engine_addr = running_service["engine_addr"]

        with pynng.Pair0(dial=engine_addr, recv_timeout=3000) as socket:
            socket.send(b"read")
            response = socket.recv()

            (log_schema := LogSchema()).deserialize(response)
            log_text = log_schema.log

            assert "AREUTHERIGHTONE" in log_text or "type=AREUTHERIGHTONE" in log_text, \
                "First log should contain AREUTHERIGHTONE"

    def test_timeout_when_no_more_logs(self, running_service: dict) -> None:
        """Verify timeout occurs when all logs have been read."""
        engine_addr = running_service["engine_addr"]

        with pynng.Pair0(dial=engine_addr, recv_timeout=1000) as socket:
            # Read all available logs
            for _ in range(10):  # more than the 3 test logs
                socket.send(b"read")
                try:
                    socket.recv()
                except pynng.Timeout:
                    break  # expected when no more logs
            else:
                # if we got here without timeout on last attempt, try one more
                socket.send(b"read")
                with pytest.raises(pynng.Timeout):
                    socket.recv()


class TestReaderConfigurationPassing:
    """Tests for proper configuration file handling."""

    def test_log_file_path_from_config(self, running_service: dict, test_log_file: Path) -> None:
        """Verify the log file path was correctly passed from config."""
        engine_addr = running_service["engine_addr"]

        with pynng.Pair0(dial=engine_addr, recv_timeout=3000) as socket:
            socket.send(b"read")
            response = socket.recv()

            (log_schema := LogSchema()).deserialize(response)

            # The service should have read from our test log file
            log_text = log_schema.log
            log_content = test_log_file.read_text()
            lines = log_content.strip().split('\n')

            # Verify the returned log matches a line from our test file
            assert any(line in log_text or log_text in line for line in lines), \
                "Read log should come from the configured test log file"


class TestLogReading:
    """Parametrized tests for log reading behavior."""

    @pytest.mark.parametrize("read_count", [1, 2, 3])
    def test_sequential_reads(self, running_service: dict, read_count: int) -> None:
        """Test sequential read operations with different counts."""
        engine_addr = running_service["engine_addr"]

        collected_logs = []

        with pynng.Pair0(dial=engine_addr, recv_timeout=3000) as socket:
            for i in range(read_count):
                socket.send(b"read")
                response = socket.recv()
                (log_schema := LogSchema()).deserialize(response)
                collected_logs.append(log_schema.log)

        assert len(collected_logs) == read_count, f"Should collect exactly {read_count} logs"
        assert all(log for log in collected_logs), "All collected logs should be non-empty"
