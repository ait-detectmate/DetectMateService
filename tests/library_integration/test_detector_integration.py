"""Integration tests for the Service CLI with DummyDetector.

Tests verify detection via engine socket with ParserSchema input.
Timeout means no detection occurred (detector returns None/False).
DummyDetector alternates: False, True, False
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
from detectmatelibrary.schemas import DetectorSchema, ParserSchema


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
                "Time": "1634567890"
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
                "Time": "1634567900"
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
                "Time": "1634567910"
            },
            "receivedTimestamp": 1634567910,
            "parsedTimestamp": 1634567911,
        },
    ]

    for config in parser_configs:
        parser_msg = ParserSchema(config)
        byte_message = parser_msg.serialize()
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

    service_info = {
        "process": proc,
        "manager_addr": settings["manager_addr"],
        "engine_addr": settings["engine_addr"],
    }

    # Wait for service to be ready
    max_retries = 10
    for attempt in range(max_retries):
        try:
            with pynng.Req0(dial=service_info["manager_addr"], recv_timeout=1000) as sock:
                sock.send(b"ping")
                if sock.recv().decode() == "pong":
                    break
        except Exception:
            if attempt == max_retries - 1:
                proc.terminate()
                proc.wait(timeout=5)
                raise RuntimeError(f"Detector service not ready within {max_retries} attempts")
        time.sleep(0.2)

    yield service_info

    # Cleanup
    try:
        with pynng.Req0(dial=service_info["manager_addr"], recv_timeout=5000) as sock:
            sock.send(b"stop")
            sock.recv()
    except Exception:
        pass


class TestDetectorServiceViaEngine:
    """Tests for detection via the engine socket."""

    def test_engine_socket_connection(self, running_detector_service: dict) -> None:
        """Verify we can connect to the engine socket."""
        engine_addr = running_detector_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=1000) as socket:
            assert socket is not None, "Should successfully connect to engine socket"

    @pytest.mark.parametrize("message_index", [0, 1, 2])
    def test_individual_messages(
        self, running_detector_service: dict, test_parser_messages: list, message_index: int
    ) -> None:
        """Parameterized test for individual message types.

        Timeout means no detection occurred (detector returned False).
        Response means detection occurred (detector returned True).
        """
        engine_addr = running_detector_service["engine_addr"]

        with pynng.Pair0(dial=engine_addr, recv_timeout=2000) as socket:
            socket.send(test_parser_messages[message_index])

            try:
                response = socket.recv()
                # If we get here, detection occurred
                assert response is not None
                assert len(response) > 0

                # Verify it's a valid DetectorSchema
                (detector_schema := DetectorSchema()).deserialize(response)
                assert detector_schema.score == 1.0
                assert detector_schema.description == "Dummy detection process"
            except pynng.Timeout:
                # Timeout means detector returned False/None (no detection)
                pass

    def test_alternating_detection_pattern(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify the alternating detection pattern: False, True, False.

        DummyDetector alternates: 1st call = no detection, 2nd = detection, 3rd = no detection.
        """
        engine_addr = running_detector_service["engine_addr"]
        results = []

        for i, parser_message in enumerate(test_parser_messages):
            with pynng.Pair0(dial=engine_addr, recv_timeout=2000) as socket:
                socket.send(parser_message)

                try:
                    response = socket.recv()
                    # Detection occurred
                    (detector_schema := DetectorSchema()).deserialize(response)
                    assert detector_schema.score == 1.0
                    results.append(True)
                except pynng.Timeout:
                    # No detection (timeout)
                    results.append(False)

        # Verify alternating pattern: False, True, False
        expected_pattern = [False, True, False]
        assert results == expected_pattern, f"Expected {expected_pattern}, got {results}"

    def test_detection_result_structure(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify detection result has proper structure when detection
        occurs."""
        engine_addr = running_detector_service["engine_addr"]

        # First message will NOT trigger detection (pattern: False, True, False)
        # So send first message to advance counter, then second message for detection
        with pynng.Pair0(dial=engine_addr, recv_timeout=2000) as socket:
            socket.send(test_parser_messages[0])
            try:
                socket.recv()
            except pynng.Timeout:
                pass  # Expected

        # Second message WILL trigger detection
        with pynng.Pair0(dial=engine_addr, recv_timeout=2000) as socket:
            socket.send(test_parser_messages[1])

            try:
                response = socket.recv()
                (detector_schema := DetectorSchema()).deserialize(response)
                # Verify structure
                assert detector_schema.description == "Dummy detection process"
                assert detector_schema.score == 1.0
                assert "type" in detector_schema.alertsObtain
                assert "Anomaly detected by DummyDetector" in detector_schema.alertsObtain["type"]
            except pynng.Timeout:
                pytest.fail("Second message should have triggered detection")

    def test_no_detection_returns_timeout(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify that no detection results in timeout (no response sent).

        Pattern is False, True, False - so 1st and 3rd calls should timeout.
        """
        engine_addr = running_detector_service["engine_addr"]
        # First call does NOT trigger detection (pattern: False)
        with pynng.Pair0(dial=engine_addr, recv_timeout=2000) as socket:
            socket.send(test_parser_messages[0])
            with pytest.raises(pynng.Timeout):
                socket.recv()
                pytest.fail("Expected timeout but received response")

    def test_consecutive_messages_with_mixed_results(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Test consecutive messages tracking both detections and non-
        detections."""
        engine_addr = running_detector_service["engine_addr"]
        detection_count = 0
        no_detection_count = 0

        for i, parser_message in enumerate(test_parser_messages):
            with pynng.Pair0(dial=engine_addr, recv_timeout=2000) as socket:
                socket.send(parser_message)

                try:
                    response = socket.recv()
                    if response is not None and len(response) > 0:
                        (detector_schema := DetectorSchema()).deserialize(response)
                        assert detector_schema.score == 1.0
                        detection_count += 1
                except pynng.Timeout:
                    # No detection occurred
                    no_detection_count += 1

        # All 3 messages should be processed
        total_processed = detection_count + no_detection_count
        assert total_processed == 3, f"Expected 3 messages processed, got {total_processed}"

        # With alternating pattern: False, True, False = 1 detection, 2 no-detections
        assert detection_count == 1, f"Expected 1 detection, got {detection_count}"
        assert no_detection_count == 2, f"Expected 2 no-detections, got {no_detection_count}"

    def test_detection_score_always_1_when_present(
        self, running_detector_service: dict, test_parser_messages: list
    ) -> None:
        """Verify that when detection occurs, score is always 1.0."""
        engine_addr = running_detector_service["engine_addr"]

        # Try all messages and collect scores from successful detections
        scores = []
        for parser_message in test_parser_messages:
            with pynng.Pair0(dial=engine_addr, recv_timeout=2000) as socket:
                socket.send(parser_message)
                try:
                    response = socket.recv()
                    (detector_schema := DetectorSchema()).deserialize(response)
                    scores.append(detector_schema.score)
                except pynng.Timeout:
                    pass  # No detection, skip

        # All collected scores should be 1.0
        for score in scores:
            assert score == 1.0, f"Expected score 1.0, got {score}"
