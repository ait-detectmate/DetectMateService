import threading
import pynng
import pytest
import json

from service.core import Service
from service.settings import ServiceSettings
from service.features.manager import manager_command


class MockService(Service):
    """Mock service with additional commands for testing."""
    component_type = "test"

    def process(self, raw_message: bytes) -> bytes | None:
        return raw_message  # echo for testing

    @manager_command()
    def echo(self, cmd: str) -> str:
        """Echo the received command."""
        return cmd

    @manager_command("custom")
    def custom_command(self) -> str:
        """Custom test command."""
        return "custom response"


@pytest.fixture
def mock_service(tmp_path):
    settings = ServiceSettings(
        manager_addr=f"ipc://{tmp_path}/test_cmd.ipc",
        engine_addr=f"ipc://{tmp_path}/test_engine.ipc",
        engine_autostart=False,
        log_level="ERROR",
    )
    service = MockService(settings=settings)
    yield service
    service._close_manager()
    assert service._stop_event.is_set()


def test_manager_commands(mock_service):
    """Test basic manager commands."""
    with pynng.Req0(dial=mock_service.settings.manager_addr) as req:
        # Test ping
        req.send(b"ping")
        assert req.recv() == b"pong"

        # Test status - parse JSON response
        req.send(b"status")
        response = json.loads(req.recv().decode())
        assert response['status']['running'] is False  # Check running field

        # Test echo command
        test_message = b"echo test message"
        req.send(test_message)
        assert req.recv() == test_message

        # Test custom command
        req.send(b"custom")
        assert req.recv() == b"custom response"

        # Test unknown command
        req.send(b"unknown")
        assert b"unknown command" in req.recv()


def test_concurrent_commands(mock_service):
    """Test that manager handles concurrent commands correctly."""
    def send_command(addr, command, results, index):
        try:
            with pynng.Req0(dial=addr) as req:
                req.send(command)
                results[index] = req.recv()
        except Exception as e:
            results[index] = str(e)

    # Send multiple concurrent commands
    commands = [b"ping", b"status", b"echo test"]
    results = [None] * len(commands)
    threads = []

    for i, cmd in enumerate(commands):
        t = threading.Thread(
            target=send_command,
            args=(mock_service.settings.manager_addr, cmd, results, i)
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=2.0)

    # Verify all commands got responses
    assert all(results)
    assert results[0] == b"pong"
    # Parse status response
    status_response = json.loads(results[1].decode())
    assert status_response['status']['running'] is False
    assert results[2] == b"echo test"


def test_manager_reconnect(mock_service):
    """Test that manager handles client disconnects/reconnects properly."""
    # First connection
    with pynng.Req0(dial=mock_service.settings.manager_addr) as req:
        req.send(b"ping")
        assert req.recv() == b"pong"

    # Second connection (should work fine)
    with pynng.Req0(dial=mock_service.settings.manager_addr) as req:
        req.send(b"status")
        response = json.loads(req.recv().decode())
        assert response['status']['running'] is False
