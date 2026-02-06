import time
import threading
import pynng
import httpx
import pytest
from contextlib import contextmanager
from service.settings import ServiceSettings
from service.core import Service


class MockComponent(Service):
    component_type = "test"

    def process(self, raw_message: bytes) -> bytes | None:
        if raw_message == b"boom":
            raise ValueError("boom!")
        if raw_message == b"skip":
            return None
        return raw_message[::-1]


@contextmanager
def pair_socket(addr: str, recv_timeout: int = 100):
    """Context manager for PAIR socket with automatic cleanup."""
    sock = pynng.Pair0(dial=addr)
    sock.recv_timeout = recv_timeout
    time.sleep(0.1)
    try:
        yield sock
    finally:
        sock.close()


@pytest.fixture
def service_thread():
    """Manages service thread lifecycle across tests."""
    threads = []

    def start(service):
        t = threading.Thread(target=service.run, daemon=True)
        t.start()
        threads.append((service, t))
        time.sleep(0.3)
        return t

    yield start

    for service, thread in threads:
        service._service_exit_event.set()
        thread.join(timeout=2.0)


@pytest.fixture
def comp(tmp_path, service_thread):
    settings = ServiceSettings(
        engine_addr=f"ipc://{tmp_path}/t_engine.ipc",
        engine_autostart=True,
        log_level="DEBUG",
        http_port=8001
    )
    c = MockComponent(settings=settings)
    service_thread(c)
    return c


def test_message_processing(comp):
    with pair_socket(comp.settings.engine_addr) as sock:
        sock.send(b"hello")
        assert sock.recv() == b"olleh"


def test_error_handling(comp):
    with pair_socket(comp.settings.engine_addr) as sock:
        sock.send(b"boom")
        with pytest.raises(pynng.Timeout):
            sock.recv()


def test_skip_processing(comp):
    with pair_socket(comp.settings.engine_addr) as sock:
        sock.send(b"skip")
        with pytest.raises(pynng.Timeout):
            sock.recv()


def test_admin_stop(comp):
    admin_url = f"http://{comp.settings.http_host}:{comp.settings.http_port}"
    response = httpx.post(f"{admin_url}/admin/stop")

    assert response.status_code == 200
    time.sleep(0.1)
    assert comp._running is False
