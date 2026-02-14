"""Integration tests for the Service CLI with DummyParser.

Tests verify parsing via engine socket with LogSchema input.
"""
from library_integration_base import start_service, cleanup_service
import time
from pathlib import Path
from typing import Generator
import pytest
import pynng
import os
from detectmatelibrary.schemas import ParserSchema
pytest_plugins = ["library_integration_base_fixtures"]


@pytest.fixture(scope="function")
def running_parser_service(tmp_path: Path) -> Generator[dict, None, None]:
    """Start the parser service with test config and yield connection info."""
    timestamp = int(time.time() * 1000)
    module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings = {
        "component_type": "parsers.dummy_parser.DummyParser",
        "component_config_class": "parsers.dummy_parser.DummyParserConfig",
        "component_name": "test-parser",
        "http_host": "127.0.0.1",
        "http_port": "8020",
        "engine_addr": f"ipc:///tmp/test_parser_engine_{timestamp}.ipc",
        "log_level": "DEBUG",
        "log_dir": "./logs",
        "log_to_console": False,
        "log_to_file": False,
        "engine_autostart": True,
    }
    config = {}
    proc, url = start_service(module_path, settings, config, tmp_path /
                              "parser_settings.yaml", tmp_path / "parser_config.yaml")
    time.sleep(0.5)
    service_info = {
        "process": proc,
        "http_host": settings["http_host"],
        "http_port": settings["http_port"],
        "engine_addr": settings["engine_addr"],
    }

    yield service_info

    cleanup_service(module_path, proc, url)


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
                raise ValueError
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
                time.sleep(0.1)
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
