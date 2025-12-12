"""Integration tests for the complete pipeline: Reader -> Parser -> Detector.

Tests verify the full data flow where:
1. Reader outputs LogSchema
2. Parser consumes LogSchema and outputs ParserSchema
3. Detector consumes ParserSchema and outputs DetectorSchema (or None)

The DummyDetector alternates: False, True, False
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
from detectmatelibrary.schemas import LogSchema, ParserSchema, DetectorSchema


@pytest.fixture(scope="session")
def test_log_file() -> Path:
    """Return path to the test log file in this folder."""
    return Path(__file__).parent / "test_logs.log"


@pytest.fixture(scope="function")
def running_pipeline_services(tmp_path: Path, test_log_file: Path) -> Generator[dict, None, None]:
    """Start all three services (Reader, Parser, Detector) with test
    configs."""
    timestamp = int(time.time() * 1000)
    module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Reader settings
    reader_settings = {
        "component_type": "readers.log_file.LogFileReader",
        "component_config_class": "readers.log_file.LogFileConfig",
        "component_name": "test-reader",
        "manager_addr": f"ipc:///tmp/test_pipeline_reader_cmd_{timestamp}.ipc",
        "engine_addr": f"ipc:///tmp/test_pipeline_reader_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": False,
        "log_to_file": False,
        "engine_autostart": True,
    }
    reader_config = {
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

    # Parser settings
    parser_settings = {
        "component_type": "parsers.dummy_parser.DummyParser",
        "component_config_class": "parsers.dummy_parser.DummyParserConfig",
        "component_name": "test-parser",
        "manager_addr": f"ipc:///tmp/test_pipeline_parser_cmd_{timestamp}.ipc",
        "engine_addr": f"ipc:///tmp/test_pipeline_parser_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": False,
        "log_to_file": False,
        "engine_autostart": True,
    }
    parser_config = {}

    # Detector settings
    detector_settings = {
        "component_type": "detectors.dummy_detector.DummyDetector",
        "component_config_class": "detectors.dummy_detector.DummyDetectorConfig",
        "component_name": "test-detector",
        "manager_addr": f"ipc:///tmp/test_pipeline_detector_cmd_{timestamp}.ipc",
        "engine_addr": f"ipc:///tmp/test_pipeline_detector_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": False,
        "log_to_file": False,
        "engine_autostart": True,
    }
    detector_config = {}

    # Write all YAML files
    reader_settings_file = tmp_path / "reader_settings.yaml"
    reader_config_file = tmp_path / "reader_config.yaml"
    parser_settings_file = tmp_path / "parser_settings.yaml"
    parser_config_file = tmp_path / "parser_config.yaml"
    detector_settings_file = tmp_path / "detector_settings.yaml"
    detector_config_file = tmp_path / "detector_config.yaml"

    with open(reader_settings_file, "w") as f:
        yaml.dump(reader_settings, f)
    with open(reader_config_file, "w") as f:
        yaml.dump(reader_config, f)
    with open(parser_settings_file, "w") as f:
        yaml.dump(parser_settings, f)
    with open(parser_config_file, "w") as f:
        yaml.dump(parser_config, f)
    with open(detector_settings_file, "w") as f:
        yaml.dump(detector_settings, f)
    with open(detector_config_file, "w") as f:
        yaml.dump(detector_config, f)

    # Start all services
    reader_proc = Popen(
        [sys.executable, "-m", "service.cli", "start",
         "--settings", str(reader_settings_file),
         "--config", str(reader_config_file)],
        cwd=module_path,
    )

    parser_proc = Popen(
        [sys.executable, "-m", "service.cli", "start",
         "--settings", str(parser_settings_file),
         "--config", str(parser_config_file)],
        cwd=module_path,
    )

    detector_proc = Popen(
        [sys.executable, "-m", "service.cli", "start",
         "--settings", str(detector_settings_file),
         "--config", str(detector_config_file)],
        cwd=module_path,
    )

    time.sleep(1.0)

    service_info = {
        "reader_process": reader_proc,
        "parser_process": parser_proc,
        "detector_process": detector_proc,
        "reader_manager_addr": reader_settings["manager_addr"],
        "reader_engine_addr": reader_settings["engine_addr"],
        "parser_manager_addr": parser_settings["manager_addr"],
        "parser_engine_addr": parser_settings["engine_addr"],
        "detector_manager_addr": detector_settings["manager_addr"],
        "detector_engine_addr": detector_settings["engine_addr"],
    }

    # Verify all services are running
    max_retries = 10
    for service_name, manager_addr in [
        ("reader", service_info["reader_manager_addr"]),
        ("parser", service_info["parser_manager_addr"]),
        ("detector", service_info["detector_manager_addr"]),
    ]:
        for attempt in range(max_retries):
            try:
                with pynng.Req0(dial=manager_addr, recv_timeout=2000) as sock:
                    sock.send(b"ping")
                    if sock.recv().decode() == "pong":
                        break
            except Exception:
                if attempt == max_retries - 1:
                    reader_proc.terminate()
                    parser_proc.terminate()
                    detector_proc.terminate()
                    reader_proc.wait(timeout=5)
                    parser_proc.wait(timeout=5)
                    detector_proc.wait(timeout=5)
                    raise RuntimeError(f"{service_name} service not ready within {max_retries} attempts")
            time.sleep(0.2)

    yield service_info

    # Cleanup all services
    for proc, manager_addr in [
        (reader_proc, service_info["reader_manager_addr"]),
        (parser_proc, service_info["parser_manager_addr"]),
        (detector_proc, service_info["detector_manager_addr"]),
    ]:
        try:
            with pynng.Req0(dial=manager_addr, recv_timeout=5000) as sock:
                sock.send(b"stop")
                sock.recv()
        except Exception:
            pass


class TestFullPipeline:
    """Tests for the complete Reader → Parser → Detector pipeline."""

    def test_all_services_start_successfully(self, running_pipeline_services: dict) -> None:
        """Verify all three services start and respond to ping."""
        for service_name, manager_addr in [
            ("reader", running_pipeline_services["reader_manager_addr"]),
            ("parser", running_pipeline_services["parser_manager_addr"]),
            ("detector", running_pipeline_services["detector_manager_addr"]),
        ]:
            with pynng.Req0(dial=manager_addr, recv_timeout=2000) as sock:
                sock.send(b"ping")
                reply = sock.recv().decode()
                assert reply == "pong", f"{service_name} should respond to ping"

    def test_single_pipeline_flow(self, running_pipeline_services: dict) -> None:
        """Test a single message flowing through the entire pipeline."""
        reader_engine = running_pipeline_services["reader_engine_addr"]
        parser_engine = running_pipeline_services["parser_engine_addr"]
        detector_engine = running_pipeline_services["detector_engine_addr"]

        # Step 1: Read log from Reader
        with pynng.Pair0(dial=reader_engine, recv_timeout=3000) as socket:
            socket.send(b"read")
            log_response = socket.recv()

        (log_schema := LogSchema()).deserialize(log_response)
        assert hasattr(log_schema, "log")
        assert hasattr(log_schema, "logID")

        # Step 2: Parse the log with Parser
        with pynng.Pair0(dial=parser_engine, recv_timeout=3000) as socket:
            socket.send(log_response)
            parser_response = socket.recv()

        (parser_schema := ParserSchema()).deserialize(parser_response)

        assert parser_schema.log == log_schema.log, "Parser should preserve original log"
        assert parser_schema.variables == ["dummy_variable"]
        assert parser_schema.template == "This is a dummy template"

        # Step 3: Detect with Detector
        # First call should NOT trigger detection (pattern: False, True, False)
        with pynng.Pair0(dial=detector_engine, recv_timeout=2000) as socket:
            socket.send(parser_response)
            try:
                socket.recv()
                pytest.fail("First detection call should timeout (no detection)")
            except pynng.Timeout:
                pass  # Expected: no detection on first call

    def test_three_pipeline_flows_with_detection_pattern(
        self, running_pipeline_services: dict
    ) -> None:
        """Test three complete pipeline flows verifying the alternating
        detection pattern.

        Expected detector pattern: False, True, False
        """
        reader_engine = running_pipeline_services["reader_engine_addr"]
        parser_engine = running_pipeline_services["parser_engine_addr"]
        detector_engine = running_pipeline_services["detector_engine_addr"]

        detection_results: list[bool] = []

        for iteration in range(3):
            # Step 1: Read log
            with pynng.Pair0(dial=reader_engine, recv_timeout=3000) as socket:
                socket.send(b"read")
                log_response = socket.recv()

            log_schema = LogSchema()
            log_schema.deserialize(log_response)

            # Step 2: Parse log
            with pynng.Pair0(dial=parser_engine, recv_timeout=3000) as socket:
                socket.send(log_schema.serialize())
                parser_response = socket.recv()

            parser_schema = ParserSchema()
            parser_schema.deserialize(parser_response)

            # Step 3: Detect
            with pynng.Pair0(dial=detector_engine, recv_timeout=2000) as socket:
                socket.send(parser_schema.serialize())
                try:
                    detector_response = socket.recv()
                    detector_schema = DetectorSchema()
                    detector_schema.deserialize(detector_response)

                    assert detector_schema.score == 1.0
                    assert detector_schema.description == "Dummy detection process"
                    detection_results.append(True)
                except pynng.Timeout:
                    detection_results.append(False)

        # Verify alternating pattern: False, True, False
        expected_pattern = [False, True, False]
        assert detection_results == expected_pattern, \
            f"Expected detection pattern {expected_pattern}, got {detection_results}"

    def test_pipeline_preserves_log_content_through_all_stages(
        self, running_pipeline_services: dict
    ) -> None:
        """Verify the original log content is preserved through Reader →
        Parser."""
        reader_engine = running_pipeline_services["reader_engine_addr"]
        parser_engine = running_pipeline_services["parser_engine_addr"]

        # Step 1: Read log
        with pynng.Pair0(dial=reader_engine, recv_timeout=3000) as socket:
            socket.send(b"read")
            log_response = socket.recv()

        log_schema = LogSchema()
        log_schema.deserialize(log_response)
        original_log = log_schema.log

        # Step 2: Parse log
        with pynng.Pair0(dial=parser_engine, recv_timeout=3000) as socket:
            socket.send(log_schema.serialize())
            parser_response = socket.recv()

        parser_schema = ParserSchema()
        parser_schema.deserialize(parser_response)
        parsed_log = parser_schema.log

        assert original_log == parsed_log, "Log content should be preserved through pipeline"

    def test_pipeline_with_successful_detection(
        self, running_pipeline_services: dict
    ) -> None:
        """Test complete pipeline flow that results in successful detection."""
        reader_engine = running_pipeline_services["reader_engine_addr"]
        parser_engine = running_pipeline_services["parser_engine_addr"]
        detector_engine = running_pipeline_services["detector_engine_addr"]

        # First flow: no detection (False)
        with pynng.Pair0(dial=reader_engine, recv_timeout=3000) as socket:
            socket.send(b"read")
            log_response = socket.recv()

        log_schema = LogSchema()
        log_schema.deserialize(log_response)

        # Parse
        with pynng.Pair0(dial=parser_engine, recv_timeout=3000) as socket:
            socket.send(log_schema.serialize())
            parser_response = socket.recv()

        parser_schema = ParserSchema()
        parser_schema.deserialize(parser_response)

        # Detect
        with pynng.Pair0(dial=detector_engine, recv_timeout=2000) as socket:
            socket.send(parser_schema.serialize())
            try:
                socket.recv()
            except pynng.Timeout:
                pass  # Expected (no detection for first flow)

        # Second flow: WITH detection (True)
        with pynng.Pair0(dial=reader_engine, recv_timeout=3000) as socket:
            socket.send(b"read")
            log_response_2 = socket.recv()

        log_schema_2 = LogSchema()
        log_schema_2.deserialize(log_response_2)

        with pynng.Pair0(dial=parser_engine, recv_timeout=3000) as socket:
            socket.send(log_schema_2.serialize())
            parser_response_2 = socket.recv()

        parser_schema_2 = ParserSchema()
        parser_schema_2.deserialize(parser_response_2)

        with pynng.Pair0(dial=detector_engine, recv_timeout=2000) as socket:
            socket.send(parser_schema_2.serialize())
            detector_response = socket.recv()

        # Verify detection occurred
        detector_schema = DetectorSchema()
        detector_schema.deserialize(detector_response)

        assert detector_schema.score == 1.0
        assert detector_schema.description == "Dummy detection process"
        assert "Anomaly detected by DummyDetector" in detector_schema.alertsObtain["type"]

        # Verify original log made it through
        assert parser_schema_2.log == log_schema_2.log

    def test_multiple_logs_through_pipeline(
        self, running_pipeline_services: dict
    ) -> None:
        """Test multiple logs flowing through the complete pipeline."""
        reader_engine = running_pipeline_services["reader_engine_addr"]
        parser_engine = running_pipeline_services["parser_engine_addr"]
        detector_engine = running_pipeline_services["detector_engine_addr"]

        processed_logs: list[dict[str, object]] = []
        detection_count = 0

        for i in range(3):
            # Read
            with pynng.Pair0(dial=reader_engine, recv_timeout=3000) as socket:
                socket.send(b"read")
                log_response = socket.recv()

            log_schema = LogSchema()
            log_schema.deserialize(log_response)

            # Parse
            with pynng.Pair0(dial=parser_engine, recv_timeout=3000) as socket:
                socket.send(log_schema.serialize())
                parser_response = socket.recv()

            parser_schema = ParserSchema()
            parser_schema.deserialize(parser_response)

            processed_logs.append({
                "original_log": log_schema.log,
                "parsed_log": parser_schema.log,
                "logID": log_schema.logID,
            })

            # Detect
            with pynng.Pair0(dial=detector_engine, recv_timeout=2000) as socket:
                socket.send(parser_schema.serialize())
                try:
                    # we only care if a detection response was produced
                    socket.recv()
                    detection_count += 1
                except pynng.Timeout:
                    pass  # No detection

        # Verify all logs were processed
        assert len(processed_logs) == 3

        # Verify logs are different
        log_contents = [log["original_log"] for log in processed_logs]
        assert len(set(log_contents)) == 3, "Each log should be unique"

        # Verify content preservation
        for log in processed_logs:
            assert log["original_log"] == log["parsed_log"]

        # Verify detection pattern (1 out of 3)
        assert detection_count == 1, "Expected 1 detection from 3 logs (False, True, False)"
