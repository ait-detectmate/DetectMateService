import time
import threading
import pynng
import pytest

from service.core import Service
from service.settings import ServiceSettings


class SmokeTestService(Service):
    """Simple service for smoke testing."""
    component_type = "smoke_test"

    def process(self, raw_message: bytes) -> bytes | None:
        """Echo the input with a prefix."""
        return b"processed: " + raw_message


@pytest.fixture
def smoke_service(tmp_path):
    """Fixture to create a smoke test service."""
    settings = ServiceSettings(
        manager_addr=f"ipc://{tmp_path}/smoke_cmd.ipc",
        engine_addr=f"ipc://{tmp_path}/smoke_engine.ipc",
        engine_autostart=True,
        log_level="ERROR",
    )
    service = SmokeTestService(settings=settings)

    # Start the service in a separate thread
    thread = threading.Thread(target=service.run, daemon=True)
    thread.start()

    # Give it time to start up
    time.sleep(0.2)

    yield service

    # Cleanup
    service.stop()

    # Close all sockets explicitly
    if hasattr(service, '_pair_sock'):
        service._pair_sock.close()

    if hasattr(service, '_rep_sock'):
        service._rep_sock.close()

    # Wait for threads to finish
    if hasattr(service, '_thread') and service._thread.is_alive():
        service._thread.join(timeout=1.0)

    if thread.is_alive():
        thread.join(timeout=1.0)


def test_service_creation(smoke_service):
    """Test that the service can be created and has the expected properties."""
    assert smoke_service is not None
    assert smoke_service.component_id is not None
    assert smoke_service.settings is not None
    assert smoke_service.component_type == "smoke_test"
    assert hasattr(smoke_service, '_stop_event')


def test_engine_processing(smoke_service):
    """Test that the engine processes messages correctly."""
    with pynng.Pair0(dial=smoke_service.settings.engine_addr) as pair:
        # Send a test message
        test_message = b"hello world"
        pair.send(test_message)

        # Receive and verify the processed response
        response = pair.recv()
        assert response == b"processed: " + test_message


def test_service_stop_command(smoke_service):
    """Test that the stop command works correctly."""
    with pynng.Req0(dial=smoke_service.settings.manager_addr) as req:
        # Test stop
        req.send(b"stop")
        response = req.recv().decode()
        assert "stopped" in response
        assert smoke_service._stop_event.is_set()


def test_service_id_stability():
    """Test that service IDs are stable based on configuration."""
    # Same configuration should yield same ID
    settings1 = ServiceSettings(
        component_name="test-service",
        component_type="test",
        manager_addr="ipc:///tmp/test1.ipc",
        engine_addr="ipc:///tmp/test2.ipc",
    )

    settings2 = ServiceSettings(
        component_name="test-service",
        component_type="test",
        manager_addr="ipc:///tmp/test1.ipc",
        engine_addr="ipc:///tmp/test2.ipc",
    )

    assert settings1.component_id == settings2.component_id

    # Different configuration should yield different ID
    settings3 = ServiceSettings(
        component_name="test-service-different",
        component_type="test",
        manager_addr="ipc:///tmp/test1.ipc",
        engine_addr="ipc:///tmp/test2.ipc",
    )

    assert settings1.component_id != settings3.component_id
