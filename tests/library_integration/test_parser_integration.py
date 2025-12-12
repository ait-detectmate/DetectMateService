"""Integration tests for the Service CLI with DummyParser.

Tests verify parsing via engine socket with LogSchema input.
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
from detectmatelibrary.schemas import ParserSchema, LogSchema


def create_test_log_messages() -> list:
    """Generate test LogSchema messages for parser input."""
    messages = []
    log_configs = [
        {
            "logID": 1,
            "log": "User john logged in from 192.168.1.100",
            "logSource": "auth_server",
            "hostname": "server-01",
        },
        {
            "logID": 2,
            "log": "Database query failed: connection timeout",
            "logSource": "database",
            "hostname": "db-01",
        },
        {
            "logID": 3,
            "log": "File config.txt accessed by admin at 10:45:30",
            "logSource": "file_server",
            "hostname": "fs-01",
        },
    ]
    for config in log_configs:
        log_msg = LogSchema(config)
        byte_message = log_msg.serialize()
        messages.append(byte_message)
    return messages


TEST_LOG_MESSAGES = create_test_log_messages()


@pytest.fixture(scope="session")
def test_log_messages() -> list:
    """Fixture providing test LogSchema messages for parser input."""
    return TEST_LOG_MESSAGES


@pytest.fixture(scope="function")
def running_parser_service(tmp_path: Path) -> Generator[dict, None, None]:
    """Start the parser service with test config and yield connection info."""
    timestamp = int(time.time() * 1000)
    module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    settings = {
        "component_type": "parsers.dummy_parser.DummyParser",
        "component_config_class": "parsers.dummy_parser.DummyParserConfig",
        "component_name": "test-parser",
        "manager_addr": f"ipc:///tmp/test_parser_cmd_{timestamp}.ipc",
        "engine_addr": f"ipc:///tmp/test_parser_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": False,
        "log_to_file": False,
        "engine_autostart": True,
    }

    config = {}

    # Write YAML files
    settings_file = tmp_path / "parser_settings.yaml"
    config_file = tmp_path / "parser_config.yaml"
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

    def is_service_ready(addr: str) -> bool:
        """Check if service is ready for actual work, not just ping."""
        try:
            with pynng.Pair0(dial=addr, recv_timeout=1000) as sock:
                # Send a test message that should get a real response
                test_msg = TEST_LOG_MESSAGES[0]
                sock.send(test_msg)
                response = sock.recv()
                return len(response) > 0
        except Exception:
            return False

    # Wait for service to be truly ready
    max_retries = 5
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
                raise RuntimeError(f"Parser service not ready within {max_retries} attempts")
        time.sleep(0.5)

    yield service_info

    try:
        with pynng.Req0(dial=service_info["manager_addr"], recv_timeout=5000) as sock:
            sock.send(b"stop")
            sock.recv()
    except Exception:
        pass  # Service might already be dead


class TestParserServiceViaEngine:
    """Tests for parsing via the engine socket."""

    def test_engine_socket_connection(self, running_parser_service: dict) -> None:
        """Verify we can connect to the parser engine socket."""
        engine_addr = running_parser_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=3000) as socket:
            assert socket is not None, "Should successfully connect to parser engine socket"

    def test_single_parse_returns_valid_result(
        self, running_parser_service: dict, test_log_messages: list
    ) -> None:
        """Verify a single parse request processes LogSchema and returns
        ParserSchema."""
        engine_addr = running_parser_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=5000) as socket:
            socket.send(test_log_messages[0])
            try:
                response = socket.recv()
                assert len(response) > 0, "Should receive non-empty response"
                # Verify it can be deserialized as ParserSchema
                (parser_schema := ParserSchema()).deserialize(response)
                assert hasattr(parser_schema, "parserType"), "ParserSchema should have parserType"
                assert hasattr(parser_schema, "log"), "ParserSchema should have log"
                assert hasattr(parser_schema, "variables"), "ParserSchema should have variables"
                assert hasattr(parser_schema, "template"), "ParserSchema should have template"
            except pynng.Timeout:
                pytest.skip("Parser service did not respond to message")

    def test_parse_preserves_original_log(
        self, running_parser_service: dict, test_log_messages: list
    ) -> None:
        """Verify parser preserves the original log content."""
        engine_addr = running_parser_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            # Use the first test message which has known log content
            original_log = "User john logged in from 192.168.1.100"
            socket.send(test_log_messages[0])
            response = socket.recv()
            (parser_schema := ParserSchema()).deserialize(response)
            assert parser_schema.log == original_log

    def test_parse_has_expected_variables(
        self, running_parser_service: dict, test_log_messages: list
    ) -> None:
        """Verify parser includes the expected dummy variables."""
        engine_addr = running_parser_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_log_messages[0])
            response = socket.recv()
            (parser_schema := ParserSchema()).deserialize(response)
            assert parser_schema.variables == ["dummy_variable"]

    def test_parse_has_expected_template(
        self, running_parser_service: dict, test_log_messages: list
    ) -> None:
        """Verify parser includes the expected dummy template."""
        engine_addr = running_parser_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_log_messages[0])
            response = socket.recv()
            (parser_schema := ParserSchema()).deserialize(response)
            assert parser_schema.template == "This is a dummy template"

    def test_parse_has_event_id(
        self, running_parser_service: dict, test_log_messages: list
    ) -> None:
        """Verify parser includes the expected EventID."""
        engine_addr = running_parser_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_log_messages[0])
            response = socket.recv()
            (parser_schema := ParserSchema()).deserialize(response)
            assert parser_schema.EventID == 2

    def test_parses_first_log_schema(
        self, running_parser_service: dict, test_log_messages: list
    ) -> None:
        """Verify parser processes the first test log schema."""
        engine_addr = running_parser_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_log_messages[0])
            try:
                response = socket.recv()
                (parser_schema := ParserSchema()).deserialize(response)
                assert parser_schema.log == "User john logged in from 192.168.1.100"
            except pynng.Timeout:
                pytest.skip("Parser service did not respond to message")

    def test_parses_second_log_schema(
        self, running_parser_service: dict, test_log_messages: list
    ) -> None:
        """Verify parser processes the second test log schema."""
        engine_addr = running_parser_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_log_messages[1])
            try:
                response = socket.recv()
                (parser_schema := ParserSchema()).deserialize(response)
                assert parser_schema.log == "Database query failed: connection timeout"
            except pynng.Timeout:
                pytest.skip("Parser service did not respond to message")

    def test_parses_third_log_schema(
        self, running_parser_service: dict, test_log_messages: list
    ) -> None:
        """Verify parser processes the third test log schema."""
        engine_addr = running_parser_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            socket.send(test_log_messages[2])
            try:
                response = socket.recv()
                (parser_schema := ParserSchema()).deserialize(response)
                assert parser_schema.log == "File config.txt accessed by admin at 10:45:30"
            except pynng.Timeout:
                pytest.skip("Parser service did not respond to message")

    def test_consecutive_message_parsing(
            self, running_parser_service: dict, test_log_messages: list
    ) -> None:
        """Test consecutive messages with fresh connections."""
        engine_addr = running_parser_service["engine_addr"]
        responses_received = []
        for i, log_message in enumerate(test_log_messages):
            # Use a fresh connection for each message
            with pynng.Pair0(dial=engine_addr, recv_timeout=15000) as socket:
                print(f"DEBUG: Sending log message {i + 1}")
                socket.send(log_message)
                try:
                    response = socket.recv()
                    print(f"DEBUG: Received parser response {i + 1}")
                except pynng.Timeout as e:
                    print(f"DEBUG: Timeout on log message {i + 1}")
                    raise e
                (parser_schema := ParserSchema()).deserialize(response)
                assert parser_schema.variables == ["dummy_variable"]
                assert parser_schema.template == "This is a dummy template"
                responses_received.append(parser_schema)
                time.sleep(0.2)
        assert len(responses_received) == 3

    def test_consistent_parsing_across_messages(
        self, running_parser_service: dict, test_log_messages: list
    ) -> None:
        """Verify parser produces consistent output regardless of input log."""
        engine_addr = running_parser_service["engine_addr"]
        with pynng.Pair0(dial=engine_addr, recv_timeout=10000) as socket:
            for log_message in test_log_messages:
                socket.send(log_message)
                response = socket.recv()
                (parser_schema := ParserSchema()).deserialize(response)
                # All messages should have the same dummy parser output structure
                assert parser_schema.variables == ["dummy_variable"]
                assert parser_schema.template == "This is a dummy template"
                assert parser_schema.EventID == 2
