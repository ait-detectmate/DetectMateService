import time
import threading
import pynng
import httpx
import pytest

from service.settings import ServiceSettings
from service.core import Service


class MockComponent(Service):
    component_type = "test"

    def process(self, raw_message: bytes) -> bytes | None:
        if raw_message == b"boom":
            raise ValueError("boom!")
        if raw_message == b"skip":
            return None
        return raw_message[::-1]  # just reverse

    def _log_engine_error(self, phase: str, exc: Exception) -> None:
        # Minimal logging stub for the test
        if hasattr(self, "log"):
            self.log.debug("err %s: %s", phase, exc)


@pytest.fixture
def comp(tmp_path):
    settings = ServiceSettings(
        engine_addr=f"ipc://{tmp_path}/t_engine.ipc",
        engine_autostart=True,
        log_level="DEBUG",
        http_port=8001
    )
    c = MockComponent(settings=settings)

    t = threading.Thread(target=c.run, daemon=True)
    t.start()

    time.sleep(0.3)
    yield c

    if c._running:
        # Trigger graceful shutdown
        try:
            httpx.post("http://127.0.0.1:8000/admin/shutdown", timeout=1.0)
        except Exception:
            c.stop()  # Fallback

    # WAIT for the thread to actually die before Pytest closes the pipes
    t.join(timeout=2.0)


def test_normal_and_error_paths(comp):
    # Connect a PAIR client
    with pynng.Pair0(dial=comp.settings.engine_addr) as sock:
        time.sleep(0.1)
        # normal
        sock.send(b"hello")
        assert sock.recv() == b"olleh"

        # error -> engine logs, but no response
        sock.send(b"boom")
        sock.recv_timeout = 100  # ms
        with pytest.raises(pynng.Timeout):
            sock.recv()

        # skip -> None, no response
        sock.send(b"skip")
        with pytest.raises(pynng.Timeout):
            sock.recv()

    # Stop via HTTP Admin API ---
    admin_url = f"http://{comp.settings.http_host}:{comp.settings.http_port}"

    # Send stop command to the engine
    response = httpx.post(f"{admin_url}/admin/stop")
    assert response.status_code == 200

    time.sleep(0.1)
    assert comp._running is False
