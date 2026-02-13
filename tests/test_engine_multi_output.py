"""Tests for Engine multi-destination output functionality."""
import pytest
import time
import pynng
from contextlib import contextmanager
from pydantic import ValidationError

from service.settings import ServiceSettings
from service.features.engine import Engine


# Timing constants
STARTUP_DELAY = 0.1
CONNECTION_DELAY = 0.2
RECV_TIMEOUT = 1000
SHORT_TIMEOUT = 500


# Test processors
class SimpleProcessor:
    """Transforms input to uppercase with prefix."""

    def process(self, raw_message: bytes) -> bytes:
        return b"PROCESSED: " + raw_message.upper()


class NullProcessor:
    """Returns None to test skip behavior."""

    def process(self, raw_message: bytes) -> None:
        return None


class FailingProcessor:
    """Raises exception to test error handling."""

    def process(self, raw_message: bytes) -> bytes:
        raise ValueError("Processor failure")


# Fixtures
@pytest.fixture
def ipc_paths(tmp_path):
    """Generate temporary IPC paths."""
    return {
        'engine': f"ipc://{tmp_path}/engine.ipc",
        'out1': f"ipc://{tmp_path}/out1.ipc",
        'out2': f"ipc://{tmp_path}/out2.ipc",
        'out3': f"ipc://{tmp_path}/out3.ipc",
    }


@contextmanager
def pair_socket(mode='dial', addr=None, timeout=RECV_TIMEOUT):
    """Context manager for PAIR socket with automatic cleanup."""
    sock = pynng.Pair0()
    sock.recv_timeout = timeout

    if addr:
        if mode == 'listen':
            sock.listen(addr)
        else:
            sock.dial(addr)

    try:
        yield sock
    finally:
        sock.close()


@pytest.fixture
def engine_manager():
    """Manages engine lifecycle across tests."""
    engines = []

    def create(settings, processor=None):
        proc = processor or SimpleProcessor()
        engine = Engine(settings=settings, processor=proc)
        engines.append(engine)
        return engine

    yield create

    for engine in engines:
        if engine._running:
            engine.stop()


@pytest.fixture
def receiver_manager():
    """Manages multiple receiver sockets with proper cleanup."""
    sockets = []

    def create_receivers(addrs, timeout=RECV_TIMEOUT):
        for addr in addrs:
            sock = pynng.Pair0()
            sock.recv_timeout = timeout
            sock.listen(addr)
            sockets.append(sock)
        return sockets

    yield create_receivers

    for sock in sockets:
        try:
            sock.close()
        except pynng.NNGException:
            pass


def create_settings(ipc_paths, out_addrs=None, port=8001):
    """Helper to create ServiceSettings with common defaults."""
    return ServiceSettings(
        engine_addr=ipc_paths['engine'],
        http_host="127.0.0.1",
        http_port=port,
        out_addr=out_addrs or [],
        engine_autostart=False,
    )


# Tests
def test_single_output_destination(ipc_paths, engine_manager):
    """Engine sends to single output destination."""
    settings = create_settings(ipc_paths, [ipc_paths['out1']])

    with pair_socket('listen', ipc_paths['out1']) as receiver, \
            pair_socket('dial', ipc_paths['engine']) as sender:

        engine = engine_manager(settings)
        engine.start()
        time.sleep(STARTUP_DELAY)

        sender.send(b"hello world")
        assert receiver.recv() == b"PROCESSED: HELLO WORLD"


def test_multiple_output_destinations(ipc_paths, engine_manager, receiver_manager):
    """Engine broadcasts to multiple outputs."""
    out_addrs = [ipc_paths['out1'], ipc_paths['out2'], ipc_paths['out3']]
    settings = create_settings(ipc_paths, out_addrs)

    receivers = receiver_manager(out_addrs)

    with pair_socket('dial', ipc_paths['engine']) as sender:
        engine = engine_manager(settings)
        engine.start()
        time.sleep(CONNECTION_DELAY)  # Need longer for multiple connections

        sender.send(b"test message")

        results = [r.recv() for r in receivers]
        assert all(r == b"PROCESSED: TEST MESSAGE" for r in results)
        assert len(results) == 3


def test_no_output_destinations(ipc_paths, engine_manager):
    """Engine with no outputs configured continues running."""
    settings = create_settings(ipc_paths, [])

    with pair_socket('dial', ipc_paths['engine']) as sender:
        engine = engine_manager(settings)
        engine.start()
        time.sleep(STARTUP_DELAY)

        sender.send(b"test message")
        time.sleep(STARTUP_DELAY)

        assert engine._running


def test_mixed_ipc_tcp_destinations(ipc_paths, engine_manager):
    """Engine sends to both IPC and TCP destinations."""
    tcp_addr = 'tcp://127.0.0.1:15555'
    settings = create_settings(ipc_paths, [ipc_paths['out1'], tcp_addr])

    with pair_socket('listen', ipc_paths['out1']) as ipc_recv, \
            pair_socket('listen', tcp_addr) as tcp_recv, \
            pair_socket('dial', ipc_paths['engine']) as sender:

        engine = engine_manager(settings)
        engine.start()
        time.sleep(STARTUP_DELAY)

        sender.send(b"mixed transport")

        assert ipc_recv.recv() == b"PROCESSED: MIXED TRANSPORT"
        assert tcp_recv.recv() == b"PROCESSED: MIXED TRANSPORT"


def test_processor_returns_none(ipc_paths, engine_manager):
    """No output sent when processor returns None."""
    settings = create_settings(ipc_paths, [ipc_paths['out1']])

    with pair_socket('listen', ipc_paths['out1'], SHORT_TIMEOUT) as receiver, \
            pair_socket('dial', ipc_paths['engine']) as sender:

        engine = engine_manager(settings, NullProcessor())
        engine.start()
        time.sleep(STARTUP_DELAY)

        sender.send(b"test")
        time.sleep(STARTUP_DELAY)

        with pytest.raises(pynng.Timeout):
            receiver.recv()


def test_output_socket_failure_resilience(ipc_paths, engine_manager):
    """Engine continues with remaining sockets if one fails."""
    settings = create_settings(ipc_paths, [ipc_paths['out1'], ipc_paths['out2']])

    with pair_socket('listen', ipc_paths['out1']) as recv1, \
            pair_socket('listen', ipc_paths['out2']), \
            pair_socket('dial', ipc_paths['engine']) as sender:

        engine = engine_manager(settings)
        engine.start()
        time.sleep(CONNECTION_DELAY)

        # Simulate mid-run failure
        engine._out_sockets[1].close()

        for _ in range(3):
            sender.send(b"resilience test")
            time.sleep(0.05)

        assert recv1.recv() == b"PROCESSED: RESILIENCE TEST"
        assert engine._running


def test_multiple_messages_sequence(ipc_paths, engine_manager, receiver_manager):
    """Multiple messages sent in sequence to multiple outputs."""
    out_addrs = [ipc_paths['out1'], ipc_paths['out2']]
    settings = create_settings(ipc_paths, out_addrs)

    receivers = receiver_manager(out_addrs)

    with pair_socket('dial', ipc_paths['engine']) as sender:
        engine = engine_manager(settings)
        engine.start()
        time.sleep(CONNECTION_DELAY)

        messages = [b"msg1", b"msg2", b"msg3"]
        for msg in messages:
            sender.send(msg)
            time.sleep(0.05)

        for receiver in receivers:
            for msg in messages:
                result = receiver.recv()
                expected = b"PROCESSED: " + msg.upper()
                assert result == expected


def test_engine_stop_closes_all_sockets(ipc_paths, engine_manager, receiver_manager):
    """Stopping engine closes all output sockets."""
    out_addrs = [ipc_paths['out1'], ipc_paths['out2']]
    settings = create_settings(ipc_paths, out_addrs)

    receiver_manager(out_addrs)

    with pair_socket('dial', ipc_paths['engine']):
        engine = engine_manager(settings)
        engine.start()
        time.sleep(CONNECTION_DELAY)

        assert len(engine._out_sockets) == 2

        engine.stop()

        for sock in engine._out_sockets:
            with pytest.raises(pynng.NNGException):
                sock.send(b"test")


def test_settings_from_yaml(tmp_path):
    """Load multi-output configuration from YAML."""
    yaml_content = """
component_name: "test-component"
component_type: "core"
log_dir: "./logs"
http_host: "127.0.0.1"
http_port: "8002"
engine_addr: "ipc:///tmp/test.engine.ipc"
out_addr:
  - "ipc:///tmp/out1.ipc"
  - "ipc:///tmp/out2.ipc"
  - "tcp://localhost:5555"
"""
    yaml_file = tmp_path / "settings.yaml"
    yaml_file.write_text(yaml_content)

    settings = ServiceSettings.from_yaml(yaml_file)

    assert [str(a) for a in settings.out_addr] == [
        "ipc:///tmp/out1.ipc",
        "ipc:///tmp/out2.ipc",
        "tcp://localhost:5555",
    ]
    assert [a.scheme for a in settings.out_addr] == ["ipc", "ipc", "tcp"]


def test_concurrent_message_processing(ipc_paths, engine_manager):
    """Messages processed correctly under load."""
    settings = create_settings(ipc_paths, [ipc_paths['out1']])

    with pair_socket('listen', ipc_paths['out1'], timeout=2000) as receiver, \
            pair_socket('dial', ipc_paths['engine']) as sender:

        engine = engine_manager(settings)
        engine.start()
        time.sleep(STARTUP_DELAY)

        num_messages = 10
        for i in range(num_messages):
            sender.send(f"message {i}".encode())
            time.sleep(0.01)

        received = [receiver.recv() for _ in range(num_messages)]

        assert len(received) == num_messages
        for i, msg in enumerate(received):
            assert msg == f"PROCESSED: MESSAGE {i}".encode()


def test_invalid_output_address_validation(ipc_paths):
    """Invalid schemes rejected at settings validation."""
    with pytest.raises(ValidationError):
        ServiceSettings(
            engine_addr=ipc_paths['engine'],
            http_host="127.0.0.1",
            http_port=8002,
            out_addr=[
                ipc_paths['out1'],
                "invalid://bad.address",
                ipc_paths['out2'],
            ],
            engine_autostart=False,
            log_level="DEBUG",
        )


def test_output_socket_failure_resilience_runtime(ipc_paths, engine_manager):
    """Engine continues sending to working outputs after runtime failure."""
    settings = create_settings(ipc_paths, [ipc_paths['out1'], ipc_paths['out2']])

    with pair_socket('listen', ipc_paths['out1']) as recv1, \
            pair_socket('listen', ipc_paths['out2']) as recv2, \
            pair_socket('dial', ipc_paths['engine']) as sender:

        engine = engine_manager(settings)
        engine.start()
        time.sleep(CONNECTION_DELAY)

        # First message: both working
        sender.send(b"initial")
        assert recv1.recv() == b"PROCESSED: INITIAL"
        assert recv2.recv() == b"PROCESSED: INITIAL"

        # Simulate runtime failure
        engine._out_sockets[1].close()

        # Second message: out1 still works
        sender.send(b"resilience test")
        assert recv1.recv() == b"PROCESSED: RESILIENCE TEST"
        assert engine._running


def test_unreachable_output_does_not_fail_startup(ipc_paths, engine_manager):
    """Engine starts even if output unreachable at startup."""
    settings = create_settings(ipc_paths, [ipc_paths['out1']])

    engine = engine_manager(settings)
    engine.start()
    engine.stop()


def test_output_socket_unavailable_does_not_fail_startup(ipc_paths, engine_manager):
    """Engine starts with mixed reachable/unreachable outputs."""
    settings = create_settings(ipc_paths, [ipc_paths['out1'], ipc_paths['out2']])

    with pair_socket('listen', ipc_paths['out1']):
        engine = engine_manager(settings)
        engine.start()
        assert engine._running
        engine.stop()


def test_late_binding_output(ipc_paths, engine_manager):
    """Engine connects to output that comes online after start."""
    settings = create_settings(ipc_paths, [ipc_paths['out1']])

    with pair_socket('dial', ipc_paths['engine']) as sender:
        engine = engine_manager(settings)
        engine.start()

        # Send while output down
        sender.send(b"msg1")
        time.sleep(STARTUP_DELAY)

        # Bring up output
        with pair_socket('listen', ipc_paths['out1'], timeout=2000) as receiver:
            time.sleep(1.0)  # Background connection

            sender.send(b"msg2")
            assert receiver.recv() == b"PROCESSED: MSG2"


def test_empty_message_handling(ipc_paths, engine_manager):
    """Empty messages are skipped."""
    settings = create_settings(ipc_paths, [ipc_paths['out1']])

    with pair_socket('listen', ipc_paths['out1'], SHORT_TIMEOUT) as receiver, \
            pair_socket('dial', ipc_paths['engine']) as sender:

        engine = engine_manager(settings)
        engine.start()
        time.sleep(STARTUP_DELAY)

        sender.send(b"")
        time.sleep(STARTUP_DELAY)

        with pytest.raises(pynng.Timeout):
            receiver.recv()


def test_large_message_handling(ipc_paths, engine_manager, receiver_manager):
    """Large messages handled correctly to multiple outputs."""
    out_addrs = [ipc_paths['out1'], ipc_paths['out2']]
    settings = create_settings(ipc_paths, out_addrs)

    receivers = receiver_manager(out_addrs, timeout=2000)

    with pair_socket('dial', ipc_paths['engine']) as sender:
        engine = engine_manager(settings)
        engine.start()
        time.sleep(CONNECTION_DELAY)

        large_message = b"x" * (1024 * 1024)
        sender.send(large_message)

        for receiver in receivers:
            result = receiver.recv()
            assert len(result) > 1024 * 1024
            assert result.startswith(b"PROCESSED: ")
