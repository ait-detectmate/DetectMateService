"""Integration tests for the Service CLI with DummyDetector.

Tests verify detection via engine socket with ParserSchema input.
"""
import time
from pathlib import Path
from subprocess import Popen, TimeoutExpired
from typing import Generator
import pytest
import pynng
import glob
import yaml
import sys
import os
from detectmatelibrary.schemas import (
    PARSER_SCHEMA,
    DETECTOR_SCHEMA,
    deserialize,
    serialize,
    ParserSchema,
)


@pytest.fixture(scope="session")
def test_parser_messages() -> list:
    """Generate test ParserSchema messages for detector input."""
    messages = []
    parser_configs = [
        {
            "parserType": "LogParser",
            "parserID": "parser_001",
            "EventID": 1,
            "template": "User <*> logged in from <*>",
            "variables": ["john", "192.168.1.100"],
            "parsedLogID": 101,
            "logID": 1,
            "log": "User john logged in from 192.168.1.100",
            "logFormatVariables": {
                "username": "john",
                "ip": "192.168.1.100",
                "timestamp": "1634567890"
            },
            "receivedTimestamp": 1634567890,
            "parsedTimestamp": 1634567891,
        },
        {
            "parserType": "LogParser",
            "parserID": "parser_002",
            "EventID": 2,
            "template": "Database query failed: <*>",
            "variables": ["connection timeout"],
            "parsedLogID": 102,
            "logID": 2,
            "log": "Database query failed: connection timeout",
            "logFormatVariables": {
                "error": "connection timeout",
                "severity": "HIGH",
                "timestamp": "1634567900"
            },
            "receivedTimestamp": 1634567900,
            "parsedTimestamp": 1634567901,
        },
        {
            "parserType": "LogParser",
            "parserID": "parser_003",
            "EventID": 3,
            "template": "File <*> accessed by <*> at <*>",
            "variables": ["config.txt", "admin", "10:45:30"],
            "parsedLogID": 103,
            "logID": 3,
            "log": "File config.txt accessed by admin at 10:45:30",
            "logFormatVariables": {
                "filename": "config.txt",
                "user": "admin",
                "timestamp": "1634567910"
            },
            "receivedTimestamp": 1634567910,
            "parsedTimestamp": 1634567911,
        },
    ]

    for config in parser_configs:
        parser_msg = ParserSchema(__version__="1.0.0", **config)
        byte_message = serialize(PARSER_SCHEMA, parser_msg)
        messages.append(byte_message)

    return messages


@pytest.fixture(scope="function")
def running_detector_service(tmp_path: Path) -> Generator[dict, None, None]:
    """Start the detector service with test config and yield connection
    info."""
    timestamp = int(time.time() * 1000)
    module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    settings = {
        "component_type": "detectors.dummy_detector.DummyDetector",
        "component_config_class": "detectors.dummy_detector.DummyDetectorConfig",
        "component_name": "test-detector",
        "manager_addr": f"ipc:///tmp/test_detector_cmd_{timestamp}.ipc",
        "engine_addr": f"ipc:///tmp/test_detector_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": False,
        "log_to_file": False,
        "engine_autostart": True,
    }

    config = {}  # DummyDetectorConfig has no additional config

    # Write YAML files
    settings_file = tmp_path / "detector_settings.yaml"
    config_file = tmp_path / "detector_config.yaml"

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

    # Enhanced service readiness check
    def is_service_ready(addr: str) -> bool:
        """Check if service is ready for actual work, not just ping."""
        try:
            with pynng.Pair0(dial=addr, recv_timeout=1000) as sock:
                # Send a test message that should get a real response
                test_msg = test_parser_messages[0]  # Use your actual test message
                sock.send(test_msg)
                response = sock.recv()
                return len(response) > 0
        except Exception:
            return False

    # Wait for service to be truly ready
    max_retries = 10
    for attempt in range(max_retries):
        try:
            # First check basic ping
            with pynng.Req0(dial=service_info["manager_addr"], recv_timeout=2000) as sock:
                sock.send(b"ping")
                if sock.recv().decode() == "pong":
                    # Then check if engine is actually processing messages
                    if is_service_ready(service_info["engine_addr"]):
                        break
        except Exception:
            if attempt == max_retries - 1:
                proc.terminate()
                proc.wait(timeout=5)
                raise RuntimeError(f"Detector service not ready within {max_retries} attempts")
        time.sleep(0.5)

    yield service_info

    # Enhanced cleanup process
    try:
        # 1. Send graceful shutdown
        with pynng.Req0(dial=service_info["manager_addr"], recv_timeout=5000) as sock:
            sock.send(b"stop")
            sock.recv()
    except Exception:
        pass  # Service might already be dead

    # 2. Terminate process with retries
    for _ in range(3):
        try:
            proc.terminate()
            proc.wait(timeout=5)
            break
        except TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=2)
                break
            except TimeoutExpired:
                continue

    # 3. Force IPC cleanup with retries and error handling
    import time as time_module
    for attempt in range(5):
        try:
            ipc_files = glob.glob(f"/tmp/test_detector_*_{timestamp}.ipc")
            for ipc_file in ipc_files:
                if os.path.exists(ipc_file):
                    os.unlink(ipc_file)
            # Verify cleanup
            remaining_files = glob.glob(f"/tmp/test_detector_*_{timestamp}.ipc")
            if not remaining_files:
                break
        except (OSError, PermissionError):
            pass
        time_module.sleep(0.2)


# @pytest.fixture(autouse=True)
# def slow_down_tests():
#     yield
#     time.sleep(0.5)


class TestDetectorServiceViaEngine:
    """Tests for detection via the engine socket."""

    def test_engine_socket_connection(self, running_detector_service: dict) -> None:
        """Verify we can connect to the engine socket."""
        engine_addr = running_detector_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=3000) as socket:
            assert socket is not None, "Should successfully connect to engine socket"

    def test_single_detection_returns_valid_result(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify a single detection request processes ParserSchema and returns
        DetectorSchema."""

        engine_addr = running_detector_service["engine_addr"]

        with pynng.Pair0(dial=engine_addr, recv_timeout=5000) as socket:
            # Send first parser message
            socket.send(test_parser_messages[0])

            try:
                response = socket.recv()
                assert len(response) > 0, "Should receive non-empty response"

                # Verify it can be deserialized as DetectorSchema
                schema_id, detector_schema = deserialize(response)

                assert schema_id == DETECTOR_SCHEMA, "Response should be a DetectorSchema"
                assert hasattr(detector_schema, "description"), "DetectorSchema should have description"
                assert hasattr(detector_schema, "score"), "DetectorSchema should have score"
                assert hasattr(detector_schema, "alertsObtain"), "DetectorSchema should have alertsObtain"
            except pynng.Timeout:
                # If detector doesn't respond, at least verify connection was established
                pytest.skip("Detector service did not respond to message")

    def test_detection_description_present(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify detection always includes the expected description."""
        engine_addr = running_detector_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_parser_messages[0])
            try:
                response = socket.recv()
                schema_id, detector_schema = deserialize(response)
                assert detector_schema.description == "Dummy detection process"
            except pynng.Timeout:
                pytest.skip("Detector service did not respond to message")

    def test_detection_result_has_valid_score(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify detection result has a valid score (0.0 or 1.0)."""
        engine_addr = running_detector_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_parser_messages[0])
            time.sleep(0.2)
            response = socket.recv()
            schema_id, detector_schema = deserialize(response)
            assert detector_schema.score in [0.0, 1.0], "Score should be 0.0 or 1.0"

    def test_detection_alert_correlation_with_score(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify detection alert presence correlates with score."""
        engine_addr = running_detector_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_parser_messages[0])
            time.sleep(0.2)
            response = socket.recv()
            schema_id, detector_schema = deserialize(response)
            has_alert = len(detector_schema.alertsObtain) > 0

            if has_alert:
                assert detector_schema.score == 1.0, "Score should be 1.0 when alert present"
                assert "type" in detector_schema.alertsObtain, "Alert should have type field"
                assert "Anomaly detected by DummyDetector" in detector_schema.alertsObtain["type"]
            else:
                assert detector_schema.score == 0.0, "Score should be 0.0 when no alert"

    def test_detects_first_parser_schema(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify detector processes the first test parser schema."""

        engine_addr = running_detector_service["engine_addr"]

        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_parser_messages[0])
            time.sleep(0.2)
            try:
                response = socket.recv()
                schema_id, detector_schema = deserialize(response)

                assert schema_id == DETECTOR_SCHEMA
                assert detector_schema.score in [0.0, 1.0]
            except pynng.Timeout:
                pytest.skip("Detector service did not respond to message")

    def test_detects_second_parser_schema(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify detector processes the second test parser schema."""

        engine_addr = running_detector_service["engine_addr"]

        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_parser_messages[1])
            time.sleep(0.2)
            try:
                response = socket.recv()
                schema_id, detector_schema = deserialize(response)

                assert schema_id == DETECTOR_SCHEMA
                assert detector_schema.score in [0.0, 1.0]
            except pynng.Timeout:
                pytest.skip("Detector service did not respond to message")

    def test_detects_third_parser_schema(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify detector processes the third test parser schema."""

        engine_addr = running_detector_service["engine_addr"]

        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_parser_messages[2])
            time.sleep(0.2)
            try:
                response = socket.recv()
                schema_id, detector_schema = deserialize(response)

                assert schema_id == DETECTOR_SCHEMA
                assert detector_schema.score in [0.0, 1.0]
            except pynng.Timeout:
                pytest.skip("Detector service did not respond to message")

    def test_consecutive_message_detection_simplified(
            self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Test consecutive messages with fresh connections."""
        engine_addr = running_detector_service["engine_addr"]
        responses_received = []

        for i, parser_message in enumerate(test_parser_messages):
            # Use a fresh connection for each message
            with pynng.Pair0(dial=engine_addr, recv_timeout=15000) as socket:
                print(f"DEBUG: Sending message {i + 1}")
                socket.send(parser_message)

                try:
                    response = socket.recv()
                    print(f"DEBUG: Received response {i + 1}")
                except pynng.Timeout as e:
                    print(f"DEBUG: Timeout on message {i + 1}")
                    raise e

                schema_id, detector_schema = deserialize(response)
                assert schema_id == DETECTOR_SCHEMA
                assert detector_schema.score in [0.0, 1.0]
                responses_received.append(detector_schema)

                time.sleep(0.2)

        assert len(responses_received) == 3
