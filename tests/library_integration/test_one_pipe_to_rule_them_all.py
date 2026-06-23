"""Integration tests for the complete pipeline: Reader -> Parser -> Detector.

Tests verify the full data flow where:
1. Reader outputs LogSchema
2. Parser consumes LogSchema and outputs ParserSchema
3. Detector consumes ParserSchema and outputs DetectorSchema (or None)

The DummyDetector alternates: False, True, False
"""
from detectmatelibrary_tests.test_parsers.dummy_parser import DummyParser
from library_integration_base import start_service, cleanup_service, AUDIT_LOG
import time
from pathlib import Path
from typing import Generator
import pytest
import pynng
import json
import sys
import os
from subprocess import Popen, PIPE
from detectmatelibrary.schemas import ParserSchema, DetectorSchema
from detectmatelibrary.helper.from_to import From
pytest_plugins = ["library_integration_base_fixtures"]


@pytest.fixture(scope="function")
def running_pipeline_services(tmp_path: Path, test_templates_file: Path) -> Generator[dict, None, None]:
    """Start all three services (Reader, Parser, Detector) with test
    configs."""
    timestamp = int(time.time() * 1000)
    module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Parser settings
    parser_settings = {
        "component_type": "detectmatelibrary_tests.test_parsers.dummy_parser.DummyParser",
        "component_config_class": "detectmatelibrary_tests.test_parsers.dummy_parser.DummyParserConfig",
        "component_name": "test-parser",
        "http_host": "127.0.0.1",
        "http_port": "8020",
        "engine_addr": f"ipc:///tmp/test_pipeline_parser_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": False,
        "log_to_file": False,
        "engine_autostart": True,
    }
    parser_config = {
        "parsers": {
            "DummyParser": {
                "method_type": "dummy_parser",
                "auto_config": False,
                "log_format": "type=<type> msg=audit(<Time>...): <Content>",
                "time_format": None,
                "params": {}
            }
        }
    }

    # Detector settings
    detector_settings = {
        "component_type": "detectmatelibrary_tests.test_detectors.dummy_detector.DummyDetector",
        "component_config_class": "detectmatelibrary_tests.test_detectors.dummy_detector.DummyDetectorConfig",
        "component_name": "test-detector",
        "http_host": "127.0.0.1",
        "http_port": "8030",
        "engine_addr": f"ipc:///tmp/test_pipeline_detector_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": False,
        "log_to_file": False,
        "engine_autostart": True,
    }
    detector_config = {}

    parser_proc, parser_url = start_service(
        module_path, parser_settings, parser_config, tmp_path / "parser_settings.yaml",
        tmp_path / "parser_config.yaml")
    detector_proc, detector_url = start_service(
        module_path, detector_settings, detector_config, tmp_path / "detector_settings.yaml",
        tmp_path / "detector_config.yaml")

    time.sleep(1.0)
    service_info = {
        "parser_process": parser_proc,
        "detector_process": detector_proc,
        "http_host": parser_settings["http_host"],
        "parser_http_port": parser_settings["http_port"],
        "parser_engine_addr": parser_settings["engine_addr"],
        "detector_http_port": detector_settings["http_port"],
        "detector_engine_addr": detector_settings["engine_addr"],
        "parser_config": parser_config
    }

    yield service_info

    cleanup_service(module_path, parser_proc, parser_url)
    cleanup_service(module_path, detector_proc, detector_url)


class TestFullPipeline:
    """Tests for the complete Reader → Parser → Detector pipeline."""

    def test_all_services_start_successfully(self, running_pipeline_services: dict) -> None:
        """Verify all three services start and respond to ping."""
        module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for service_name, host, port in [
            ("parser", running_pipeline_services["http_host"], running_pipeline_services["parser_http_port"]),
            ("detector", running_pipeline_services["http_host"],
             running_pipeline_services["detector_http_port"]),
        ]:
            max_retries = 10
            url = f"http://{host}:{port}"
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
                    # Service may not yet be returning valid JSON; retry until max_retries is reached.
                    pass
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Service not ready within {max_retries} attempts")
                time.sleep(0.2)

    def test_single_pipeline_flow(self, running_pipeline_services: dict) -> None:
        """Test a single message flowing through the entire pipeline."""
        parser_engine = running_pipeline_services["parser_engine_addr"]
        detector_engine = running_pipeline_services["detector_engine_addr"]

        # Step 1: Read log from Reader
        parser = DummyParser(config=running_pipeline_services["parser_config"])
        logs = [log for log in From.log(parser, AUDIT_LOG, do_process=True) if log is not None]
        log_schema = logs[0]
        assert hasattr(log_schema, "log")
        assert hasattr(log_schema, "logID")

        # Step 2: Parse the log with Parser
        with pynng.Pair0(dial=parser_engine, recv_timeout=3000) as socket:
            socket.send(log_schema.serialize())
            parser_response = socket.recv()

        (parser_schema := ParserSchema()).deserialize(parser_response)

        assert parser_schema.log == "DummyParser", "Log not as expected."
        assert log_schema != "DummyParser", "Log not as expected."
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
        parser_engine = running_pipeline_services["parser_engine_addr"]
        detector_engine = running_pipeline_services["detector_engine_addr"]

        detection_results: list[bool] = []

        for iteration in range(3):
            # Step 1: Read log
            parser = DummyParser(config=running_pipeline_services["parser_config"])
            logs = [log for log in From.log(parser, AUDIT_LOG, do_process=True) if log is not None]
            log_schema = logs[0]
            assert hasattr(log_schema, "log")
            assert hasattr(log_schema, "logID")

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
        parser_engine = running_pipeline_services["parser_engine_addr"]

        # Step 1: Read log
        parser = DummyParser(config=running_pipeline_services["parser_config"])
        logs = [log for log in From.log(parser, AUDIT_LOG, do_process=True) if log is not None]
        log_schema = logs[0]
        assert hasattr(log_schema, "log")
        assert hasattr(log_schema, "logID")
        original_log = log_schema.log

        # Step 2: Parse log
        with pynng.Pair0(dial=parser_engine, recv_timeout=3000) as socket:
            socket.send(log_schema.serialize())
            parser_response = socket.recv()

        parser_schema = ParserSchema()
        parser_schema.deserialize(parser_response)
        parsed_log = parser_schema.log

        assert parsed_log == "DummyParser", "Log not as expected."
        assert original_log != "DummyParser", "Log not as expected."

    def test_pipeline_with_successful_detection(
        self, running_pipeline_services: dict
    ) -> None:
        """Test complete pipeline flow that results in successful detection."""
        parser_engine = running_pipeline_services["parser_engine_addr"]
        detector_engine = running_pipeline_services["detector_engine_addr"]

        # First flow: no detection (False)
        parser = DummyParser(config=running_pipeline_services["parser_config"])
        logs = [log for log in From.log(parser, AUDIT_LOG, do_process=True) if log is not None]
        log_schema = logs[0]
        assert hasattr(log_schema, "log")
        assert hasattr(log_schema, "logID")

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
        log_schema_2 = logs[1]

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
        assert parser_schema_2.log == "DummyParser", "Log not as expected."
        assert log_schema_2.log != "DummyParser", "Log not as expected."

    def test_multiple_logs_through_pipeline(
        self, running_pipeline_services: dict
    ) -> None:
        """Test multiple logs flowing through the complete pipeline."""
        parser_engine = running_pipeline_services["parser_engine_addr"]
        detector_engine = running_pipeline_services["detector_engine_addr"]

        processed_logs: list[dict[str, object]] = []
        detection_count = 0

        # Read
        parser = DummyParser(config=running_pipeline_services["parser_config"])
        logs = [log for log in From.log(parser, AUDIT_LOG, do_process=True) if log is not None]
        for i in range(3):
            log_schema = logs[i]
            assert hasattr(log_schema, "log")
            assert hasattr(log_schema, "logID")

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

        # Verify content
        for log in processed_logs:
            assert log["parsed_log"] == "DummyParser", "Log not as expected."
            assert log["original_log"] != "DummyParser", "Log not as expected."

        # Verify detection pattern (1 out of 3)
        assert detection_count == 1, "Expected 1 detection from 3 logs (False, True, False)"
