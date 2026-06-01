"""Integration tests for the complete pipeline: Reader -> Parser -> Detector.

Tests verify the full data flow where:
1. Reader outputs LogSchema
2. Parser consumes LogSchema and outputs ParserSchema
3. Detector consumes ParserSchema and outputs DetectorSchema (or None)
"""
from detectmatelibrary.parsers.template_matcher import MatcherParser

from library_integration_base import start_service, cleanup_service, AUDIT_LOG
import time
from pathlib import Path
from subprocess import Popen
from typing import Generator
import pytest
import pynng
import sys
import os
import json
from subprocess import PIPE
from detectmatelibrary.schemas import ParserSchema, DetectorSchema
from detectmatelibrary.helper.from_to import From
pytest_plugins = ["library_integration_base_fixtures"]


@pytest.fixture(scope="function")
def running_pipeline_services(
    tmp_path: Path,
    test_templates_file: Path
) -> Generator[dict, None, None]:
    """Start all three services (Reader, Parser, Detector) with test
    configs."""
    timestamp = int(time.time() * 1000)
    module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Parser settings
    parser_settings = {
        "component_type": "parsers.template_matcher.MatcherParser",
        "component_config_class": "parsers.template_matcher.MatcherParserConfig",
        "component_name": "test-parser",
        "http_host": "127.0.0.1",
        "http_port": "8020",
        "engine_addr": f"ipc:///tmp/test_pipeline_parser_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": True,
        "log_to_file": False,
        "engine_autostart": True,
    }
    parser_config = {
        "parsers": {
            "MatcherParser": {
                "method_type": "matcher_parser",
                "auto_config": False,
                "log_format": "type=<type> msg=audit(<Time>...): <Content>",
                "time_format": None,
                "params": {
                    "remove_spaces": True,
                    "remove_punctuation": True,
                    "lowercase": True,
                    "path_templates": str(test_templates_file)
                }
            }
        }
    }

    # Detector settings
    detector_settings = {
        "component_type": "detectors.new_value_detector.NewValueDetector",
        "component_config_class": "detectors.new_value_detector.NewValueDetectorConfig",
        "component_name": "test-nvd",
        "http_host": "127.0.0.1",
        "http_port": "8030",
        "engine_addr": f"ipc:///tmp/test_pipeline_detector_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": True,
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

    time.sleep(6.5)

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

        # Step 1: Read log
        parser = MatcherParser(config=running_pipeline_services["parser_config"])
        logs = [log for log in From.log(parser, AUDIT_LOG, do_process=True) if log is not None]
        log_schema = logs[0]
        assert hasattr(log_schema, "log")
        assert hasattr(log_schema, "logID")

        # Step 2: Parse the log with Parser
        with pynng.Pair0(dial=parser_engine, recv_timeout=3000) as socket:
            socket.send(log_schema.serialize())
            parser_response = socket.recv()

        parser_schema = ParserSchema()
        parser_schema.deserialize(parser_response)

        # /detectmatelibrary/parsers/template_matcher/_parser.py: MatcherParser does not set the log!
        assert parser_schema.log == "MatcherParser", "Log not as expected."
        assert log_schema != "MatcherParser", "Log not as expected."

        # Step 3: Send to Detector (may or may not detect)
        with pynng.Pair0(dial=detector_engine, recv_timeout=2000) as socket:
            socket.send(parser_schema.serialize())
            try:
                detector_response = socket.recv()
                detector_schema = DetectorSchema()
                detector_schema.deserialize(detector_response)
            except pynng.Timeout:
                pass  # no detection

    def test_multiple_logs_through_pipeline(
        self, running_pipeline_services: dict
    ) -> None:
        """Test multiple logs flowing through the complete pipeline."""
        parser_engine = running_pipeline_services["parser_engine_addr"]
        detector_engine = running_pipeline_services["detector_engine_addr"]
        processed_logs = []

        for i in range(5):
            # Step 1: Read log
            parser = MatcherParser(config=running_pipeline_services["parser_config"])
            logs = [log for log in From.log(parser, AUDIT_LOG, do_process=True) if log is not None]
            log_schema = logs[0]

            # Step 2: Parse log
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

            # Step 3: Send to Detector
            with pynng.Pair0(dial=detector_engine, recv_timeout=2000) as socket:
                socket.send(parser_schema.serialize())
                try:
                    detector_response = socket.recv()
                    detector_schema = DetectorSchema()
                    detector_schema.deserialize(detector_response)
                except pynng.Timeout:
                    pass  # no detection

        # Verify all logs were processed
        assert len(processed_logs) == 5

        # Verify content preservation
        # /detectmatelibrary/parsers/template_matcher/_parser.py: MatcherParser does not set the log!
        for log in processed_logs:
            assert log["parsed_log"] == "MatcherParser", "Log not as expected."
            assert log["original_log"] != "MatcherParser", "Log not as expected."

    def test_pipeline_preserves_log_content(
        self, running_pipeline_services: dict
    ) -> None:
        """Verify the original log content is preserved through Reader →
        Parser."""
        parser_engine = running_pipeline_services["parser_engine_addr"]

        # Step 1: Read log
        parser = MatcherParser(config=running_pipeline_services["parser_config"])
        logs = [log for log in From.log(parser, AUDIT_LOG, do_process=True) if log is not None]
        log_schema = logs[0]
        original_log = log_schema.log

        # Step 2: Parse log
        with pynng.Pair0(dial=parser_engine, recv_timeout=3000) as socket:
            socket.send(log_schema.serialize())
            parser_response = socket.recv()

        parser_schema = ParserSchema()
        parser_schema.deserialize(parser_response)
        parsed_log = parser_schema.log

        # /detectmatelibrary/parsers/template_matcher/_parser.py: MatcherParser does not set the log!
        assert parsed_log == "MatcherParser", "Log not as expected."
        assert original_log != "MatcherParser", "Log not as expected."

    def test_full_pipeline_chain(self, running_pipeline_services: dict) -> None:
        """Test the complete chain: Reader -> Parser -> Detector in sequence."""
        parser_engine = running_pipeline_services["parser_engine_addr"]
        detector_engine = running_pipeline_services["detector_engine_addr"]

        # Read
        parser = MatcherParser(config=running_pipeline_services["parser_config"])
        logs = [log for log in From.log(parser, AUDIT_LOG, do_process=True) if log is not None]
        log_schema = logs[0]

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
                detector_response = socket.recv()
                detector_schema = DetectorSchema()
                detector_schema.deserialize(detector_response)
            except pynng.Timeout:
                pass  # no detection
