import time
import threading
import pynng
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
        manager_addr=f"ipc://{tmp_path}/t_cmd.ipc",
        engine_addr=f"ipc://{tmp_path}/t_engine.ipc",
        engine_autostart=True,
        log_level="DEBUG",
    )
    c = MockComponent(settings=settings)
    t = threading.Thread(target=c.run, daemon=True)
    t.start()
    # Give it a moment to spin up
    time.sleep(0.2)
    yield c
    c.stop()
    time.sleep(0.1)
    assert c._stop_event.is_set()


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

    # Stop via manager
    with pynng.Req0(dial=comp.settings.manager_addr) as req:
        req.send(b"stop")
        assert req.recv() == b"engine stopped"
        assert comp._stop_event.is_set()
