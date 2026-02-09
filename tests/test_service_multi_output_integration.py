"""Integration tests for Service with multi-destination output."""
import socket
import threading
import time
from typing import List

import httpx
import pynng
import pytest

from service.core import Service
from service.settings import ServiceSettings

# --- Constants ---
STARTUP_DELAY = 0.2
SHUTDOWN_DELAY = 0.1
RECV_TIMEOUT = 1000
BASE_HTTP_URL = "http://127.0.0.1"


class MockService(Service):
    """Concrete test service for integration testing."""
    component_type = "test_service"


# --- Helpers & Fixtures ---

def create_settings(ipc_paths, out_addrs=None, port=8001, **kwargs):
    """Helper to create ServiceSettings with common defaults."""
    defaults = {
        "component_name": "test-service",
        "engine_addr": ipc_paths['engine'],
        "http_host": "127.0.0.1",
        "http_port": port,
        "out_addr": out_addrs or [],
        "engine_autostart": True,
    }
    defaults.update(kwargs)
    return ServiceSettings(**defaults)


@pytest.fixture
def http_port() -> int:
    """Find and return a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
def port_generator():
    """Yields unique available ports."""
    used_ports = set()

    def _get_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            port = s.getsockname()[1]
            # Ensure we don't pick the same one twice in rapid succession
            while port in used_ports:
                s.bind(('', 0))
                port = s.getsockname()[1]
            used_ports.add(port)
            return port
    return _get_port


@pytest.fixture
def ipc_paths(tmp_path) -> dict:
    """Generate temporary IPC paths for testing."""
    return {
        'engine': f"ipc://{tmp_path}/engine.ipc",
        'out1': f"ipc://{tmp_path}/out1.ipc",
        'out2': f"ipc://{tmp_path}/out2.ipc",
        'out3': f"ipc://{tmp_path}/out3.ipc",
    }


@pytest.fixture
def service_factory():
    """Factory to manage service lifecycle and cleanup."""
    services = []

    def _create_service(settings: ServiceSettings):
        svc = MockService(settings=settings)
        services.append(svc)
        thread = threading.Thread(target=svc.run, daemon=True)
        thread.start()
        time.sleep(STARTUP_DELAY)
        return svc

    yield _create_service

    for svc in services:
        svc.stop()
        try:
            url = f"{BASE_HTTP_URL}:{svc.settings.http_port}/admin/shutdown"
            httpx.post(url, timeout=0.5)
        except (httpx.HTTPError, Exception):
            pass
    time.sleep(SHUTDOWN_DELAY)


@pytest.fixture
def receiver_manager():
    """Context manager-like fixture to handle multiple NNG receivers."""
    sockets = []

    def _create_receivers(addresses: List[str]) -> List[pynng.Pair0]:
        for addr in addresses:
            receiver = pynng.Pair0(listen=addr, recv_timeout=RECV_TIMEOUT)
            sockets.append(receiver)
        return sockets

    yield _create_receivers

    for sock in sockets:
        sock.close()


@pytest.fixture
def sender_factory():
    """Factory for NNG sender sockets."""
    sockets = []

    def _create_sender(address: str) -> pynng.Pair0:
        sender = pynng.Pair0(dial=address)
        sockets.append(sender)
        return sender

    yield _create_sender

    for sock in sockets:
        sock.close()


class TestServiceMultiOutputIntegration:
    """Integration tests for Service with multi-output functionality."""

    def test_service_with_multiple_outputs(
            self,
            ipc_paths,
            http_port,
            service_factory,
            receiver_manager,
            sender_factory
    ):
        """Test complete service flow with multiple outputs."""
        out_addrs = [ipc_paths['out1'], ipc_paths['out2']]
        settings = create_settings(ipc_paths, out_addrs=out_addrs, port=http_port)

        # Use managers to handle socket lifecycles
        receivers = receiver_manager(out_addrs)
        service_factory(settings)
        sender = sender_factory(ipc_paths['engine'])

        # Send test message
        test_message = b"integration test"
        sender.send(test_message)

        # All receivers should get the message
        for receiver in receivers:
            result = receiver.recv()
            assert result == test_message

    def test_service_status_with_output_config(self, ipc_paths, http_port, service_factory, receiver_manager):
        """Test that status command includes output configuration."""
        out_addrs = [ipc_paths['out1'], ipc_paths['out2']]
        settings = create_settings(ipc_paths, out_addrs=out_addrs, port=http_port)

        # output listeners must exist before service starts
        receiver_manager(out_addrs)
        service_factory(settings)

        # Request status via HTTP
        response = httpx.get(f"{BASE_HTTP_URL}:{http_port}/admin/status")
        assert response.status_code == 200
        status_data = response.json()

        # Verify output addresses are in settings
        assert status_data['settings']['out_addr'] == out_addrs

    def test_service_context_manager_with_outputs(
            self,
            ipc_paths,
            http_port,
            service_factory,
            receiver_manager,

            sender_factory):
        """Test service as context manager with multiple outputs."""
        out_addrs = [ipc_paths['out1']]
        settings = create_settings(ipc_paths, out_addrs=out_addrs, port=http_port)

        receivers = receiver_manager(out_addrs)
        sender = sender_factory(ipc_paths['engine'])
        service_factory(settings)

        sender.send(b"context manager test")
        assert receivers[0].recv() == b"context manager test"

    def test_service_stop_command_closes_outputs(self,
                                                 ipc_paths,
                                                 http_port,
                                                 service_factory,
                                                 receiver_manager):
        """Test that stop command properly closes output sockets."""
        out_addrs = [ipc_paths['out1'], ipc_paths['out2']]
        settings = create_settings(ipc_paths, out_addrs=out_addrs, port=http_port)

        receiver_manager(out_addrs)
        svc = service_factory(settings)

        assert svc._running

        # Send stop command
        httpx.post(f"{BASE_HTTP_URL}:{http_port}/admin/stop")
        time.sleep(SHUTDOWN_DELAY)

        assert not svc._running

        # Verify output sockets are closed/non-functional
        for sock in svc._out_sockets:
            with pytest.raises(pynng.NNGException):
                sock.send(b"test")

    def test_service_with_no_outputs_still_works(self, ipc_paths, http_port, service_factory, sender_factory):
        """Test that service works normally with no output addresses."""
        settings = create_settings(ipc_paths, out_addrs=[], port=http_port)

        svc = service_factory(settings)
        sender = sender_factory(ipc_paths['engine'])

        sender.send(b"test message")
        time.sleep(0.1)
        assert svc._running

    def test_yaml_config_loading_with_outputs(self, tmp_path, http_port):
        """Test loading service settings from YAML with output addresses."""
        yaml_content = f"""
        component_name: "yaml-test"
        component_type: "test_service"
        log_dir: "{tmp_path}/logs"
        http_host: "127.0.0.1"
        http_port: {http_port}
        engine_addr: "ipc://{tmp_path}/engine.ipc"
        out_addr:
          - "ipc://{tmp_path}/out1.ipc"
          - "ipc://{tmp_path}/out2.ipc"
          - "tcp://localhost:5555"
        engine_autostart: false
        """
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text(yaml_content)

        settings = ServiceSettings.from_yaml(yaml_file)

        assert settings.component_name == "yaml-test"
        assert len(settings.out_addr) == 3
        out_strs = [str(a) for a in settings.out_addr]
        assert "tcp://localhost:5555" in out_strs

    def test_concurrent_services_different_outputs(self,
                                                   tmp_path,
                                                   service_factory,
                                                   receiver_manager,
                                                   sender_factory,
                                                   port_generator):
        """Test multiple services with different output destinations."""
        # Service 1
        paths1 = {'engine': f"ipc://{tmp_path}/s1_eng.ipc", 'out': f"ipc://{tmp_path}/s1_out.ipc"}
        set1 = create_settings(paths1, out_addrs=[paths1['out']], port=port_generator())
        rec1 = receiver_manager([paths1['out']])[0]
        service_factory(set1)
        sender1 = sender_factory(paths1['engine'])

        # Service 2
        paths2 = {'engine': f"ipc://{tmp_path}/s2_eng.ipc", 'out': f"ipc://{tmp_path}/s2_out.ipc"}
        set2 = create_settings(paths2, out_addrs=[paths2['out']], port=port_generator())
        # Note: receiver_manager fixture appends to the same list, so we grab the new one
        rec2 = receiver_manager([paths2['out']])[-1]
        service_factory(set2)
        sender2 = sender_factory(paths2['engine'])

        sender1.send(b"message 1")
        sender2.send(b"message 2")

        assert rec1.recv() == b"message 1"
        assert rec2.recv() == b"message 2"


class TestServiceMultiOutputStressTests:
    """Stress tests for multi-output functionality."""

    def test_high_throughput_multiple_outputs(self,
                                              ipc_paths,
                                              http_port,
                                              service_factory,
                                              receiver_manager,
                                              sender_factory):
        """Test handling high message throughput to multiple outputs."""
        out_addrs = [ipc_paths['out1'], ipc_paths['out2'], ipc_paths['out3']]
        settings = create_settings(ipc_paths, out_addrs=out_addrs, port=http_port)

        receivers = receiver_manager(out_addrs)
        service_factory(settings)
        sender = sender_factory(ipc_paths['engine'])

        num_messages = 100
        for i in range(num_messages):
            sender.send(f"msg {i}".encode())

        for receiver in receivers:
            for i in range(num_messages):
                assert receiver.recv() == f"msg {i}".encode()
