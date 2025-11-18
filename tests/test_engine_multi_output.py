"""Tests for Engine multi-destination output functionality."""
import pytest
import time
import pynng
import logging

from service.settings import ServiceSettings
from service.features.engine import Engine
from library.processor import BaseProcessor


class SimpleProcessor(BaseProcessor):
    """Test processor that transforms input."""

    def __call__(self, raw_message: bytes) -> bytes:
        # Simple transformation: uppercase and add prefix
        return b"PROCESSED: " + raw_message.upper()


class NullProcessor(BaseProcessor):
    """Test processor that returns None."""

    def __call__(self, raw_message: bytes) -> None:
        return None


class FailingProcessor(BaseProcessor):
    """Test processor that raises an exception."""

    def __call__(self, raw_message: bytes) -> bytes:
        raise ValueError("Processor failure")


@pytest.fixture
def temp_ipc_paths(tmp_path):
    """Generate temporary IPC paths for testing."""
    return {
        'engine': f"ipc://{tmp_path}/engine.ipc",
        'out1': f"ipc://{tmp_path}/out1.ipc",
        'out2': f"ipc://{tmp_path}/out2.ipc",
        'out3': f"ipc://{tmp_path}/out3.ipc",
        'manager': f"ipc://{tmp_path}/manager.ipc",
    }


@pytest.fixture
def tcp_ports():
    """Generate TCP ports for testing."""
    return {
        'out1': 'tcp://127.0.0.1:15555',
        'out2': 'tcp://127.0.0.1:15556',
        'out3': 'tcp://127.0.0.1:15557',
    }


class TestEngineMultiOutput:
    """Test suite for Engine multi-destination output."""

    def test_single_output_destination(self, temp_ipc_paths):
        """Test engine with a single output destination."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[temp_ipc_paths['out1']],
            engine_autostart=False,
        )

        # Create output receiver
        receiver = pynng.Pull0()
        receiver.listen(temp_ipc_paths['out1'])
        receiver.recv_timeout = 1000

        # Create engine with processor
        processor = SimpleProcessor()
        engine = Engine(settings=settings, processor=processor)

        # Create input sender
        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            # Start engine
            engine.start()
            time.sleep(0.1)  # Give engine time to start

            # Send test message
            test_message = b"hello world"
            sender.send(test_message)

            # Receive processed message
            result = receiver.recv()
            assert result == b"PROCESSED: HELLO WORLD"

        finally:
            engine.stop()
            sender.close()
            receiver.close()

    def test_multiple_output_destinations(self, temp_ipc_paths):
        """Test engine sending to multiple output destinations."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[
                temp_ipc_paths['out1'],
                temp_ipc_paths['out2'],
                temp_ipc_paths['out3'],
            ],
            engine_autostart=False,
        )

        # Create multiple output receivers
        receivers = []
        for addr in [temp_ipc_paths['out1'], temp_ipc_paths['out2'], temp_ipc_paths['out3']]:
            receiver = pynng.Pull0()
            receiver.listen(addr)
            receiver.recv_timeout = 1000
            receivers.append(receiver)

        # Create engine
        processor = SimpleProcessor()
        engine = Engine(settings=settings, processor=processor)

        # Create input sender
        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            # Start engine
            engine.start()
            time.sleep(0.1)

            # Send test message
            test_message = b"test message"
            sender.send(test_message)

            # All receivers should get the same processed message
            results = []
            for receiver in receivers:
                result = receiver.recv()
                results.append(result)

            # Verify all receivers got the same message
            expected = b"PROCESSED: TEST MESSAGE"
            assert all(r == expected for r in results)
            assert len(results) == 3

        finally:
            engine.stop()
            sender.close()
            for receiver in receivers:
                receiver.close()

    def test_no_output_destinations(self, temp_ipc_paths):
        """Test engine with no output destinations configured."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[],  # Empty list
            engine_autostart=False,
        )

        processor = SimpleProcessor()
        engine = Engine(settings=settings, processor=processor)

        # Create input sender
        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            # Start engine
            engine.start()
            time.sleep(0.1)

            # Send test message - should not cause error even with no outputs
            test_message = b"test message"
            sender.send(test_message)
            time.sleep(0.1)  # Give time to process

            # Engine should continue running without error
            assert engine._running

        finally:
            engine.stop()
            sender.close()

    def test_mixed_ipc_tcp_destinations(self, temp_ipc_paths):
        """Test engine with both IPC and TCP output destinations."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[
                temp_ipc_paths['out1'],
                'tcp://127.0.0.1:15555',
            ],
            engine_autostart=False,
        )

        # Create IPC receiver
        ipc_receiver = pynng.Pull0()
        ipc_receiver.listen(temp_ipc_paths['out1'])
        ipc_receiver.recv_timeout = 1000

        # Create TCP receiver
        tcp_receiver = pynng.Pull0()
        tcp_receiver.listen('tcp://127.0.0.1:15555')
        tcp_receiver.recv_timeout = 1000

        processor = SimpleProcessor()
        engine = Engine(settings=settings, processor=processor)

        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            engine.start()
            time.sleep(0.1)

            # Send test message
            test_message = b"mixed transport"
            sender.send(test_message)

            # Both receivers should get the message
            ipc_result = ipc_receiver.recv()
            tcp_result = tcp_receiver.recv()

            expected = b"PROCESSED: MIXED TRANSPORT"
            assert ipc_result == expected
            assert tcp_result == expected

        finally:
            engine.stop()
            sender.close()
            ipc_receiver.close()
            tcp_receiver.close()

    def test_processor_returns_none(self, temp_ipc_paths):
        """Test that no output is sent when processor returns None."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[temp_ipc_paths['out1']],
            engine_autostart=False,
        )

        receiver = pynng.Pull0()
        receiver.listen(temp_ipc_paths['out1'])
        receiver.recv_timeout = 500  # Short timeout

        processor = NullProcessor()
        engine = Engine(settings=settings, processor=processor)

        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            engine.start()
            time.sleep(0.1)

            # Send message
            sender.send(b"test")
            time.sleep(0.1)

            # Should timeout because no message is sent
            with pytest.raises(pynng.Timeout):
                receiver.recv()

        finally:
            engine.stop()
            sender.close()
            receiver.close()

    def test_output_socket_failure_resilience(self, temp_ipc_paths):
        """Test that engine continues with remaining sockets if one fails."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            # out1: has receiver, out2: no receiver (simulated failure)
            out_addr=[
                temp_ipc_paths['out1'],
                temp_ipc_paths['out2'],
            ],
            engine_autostart=False,
        )

        # Create receiver only for out1 (skip out2 to trigger dial/send issues)
        receiver1 = pynng.Pull0()
        receiver1.listen(temp_ipc_paths['out1'])
        receiver1.recv_timeout = 2000

        processor = SimpleProcessor()
        engine = Engine(settings=settings, processor=processor)

        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            engine.start()
            time.sleep(0.2)  # Give time for connections

            # Send a few messages; even if out2 fails, out1 should still work
            test_message = b"resilience test"
            for _ in range(3):
                sender.send(test_message)
                time.sleep(0.05)

            # Receiver 1 should still get the processed message
            result1 = receiver1.recv()
            expected = b"PROCESSED: RESILIENCE TEST"
            assert result1 == expected

        finally:
            engine.stop()
            sender.close()
            receiver1.close()

    def test_multiple_messages_sequence(self, temp_ipc_paths):
        """Test sending multiple messages in sequence to multiple outputs."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[temp_ipc_paths['out1'], temp_ipc_paths['out2']],
            engine_autostart=False,
        )

        receivers = []
        for addr in [temp_ipc_paths['out1'], temp_ipc_paths['out2']]:
            receiver = pynng.Pull0()
            receiver.listen(addr)
            receiver.recv_timeout = 1000
            receivers.append(receiver)

        processor = SimpleProcessor()
        engine = Engine(settings=settings, processor=processor)

        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            engine.start()
            time.sleep(0.1)

            # Send multiple messages
            messages = [b"msg1", b"msg2", b"msg3"]
            for msg in messages:
                sender.send(msg)

            # Collect results from all receivers
            for receiver in receivers:
                for msg in messages:
                    result = receiver.recv()
                    expected = b"PROCESSED: " + msg.upper()
                    assert result == expected

        finally:
            engine.stop()
            sender.close()
            for receiver in receivers:
                receiver.close()

    def test_engine_stop_closes_all_sockets(self, temp_ipc_paths):
        """Test that stopping engine closes all output sockets."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[temp_ipc_paths['out1'], temp_ipc_paths['out2']],
            engine_autostart=False,
        )

        # Create receivers
        receivers = []
        for addr in [temp_ipc_paths['out1'], temp_ipc_paths['out2']]:
            receiver = pynng.Pull0()
            receiver.listen(addr)
            receivers.append(receiver)

        processor = SimpleProcessor()
        engine = Engine(settings=settings, processor=processor)

        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            engine.start()
            time.sleep(0.1)

            # Verify engine has output sockets
            assert len(engine._out_sockets) == 2

            # Stop engine
            engine.stop()

            # Verify sockets are closed (attempting to send should fail)
            for sock in engine._out_sockets:
                with pytest.raises(pynng.NNGException):
                    sock.send(b"test")

        finally:
            sender.close()
            for receiver in receivers:
                receiver.close()

    def test_settings_from_yaml(self, tmp_path):
        """Test loading multi-output configuration from YAML."""
        yaml_content = """
component_name: "test-component"
component_type: "core"
log_dir: "./logs"
manager_addr: "ipc:///tmp/test.cmd.ipc"
engine_addr: "ipc:///tmp/test.engine.ipc"
out_addr:
  - "ipc:///tmp/out1.ipc"
  - "ipc:///tmp/out2.ipc"
  - "tcp://localhost:5555"
"""
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text(yaml_content)

        settings = ServiceSettings.from_yaml(yaml_file)

        assert settings.out_addr == [
            "ipc:///tmp/out1.ipc",
            "ipc:///tmp/out2.ipc",
            "tcp://localhost:5555",
        ]

    def test_concurrent_message_processing(self, temp_ipc_paths):
        """Test that messages are processed and sent correctly under load."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[temp_ipc_paths['out1']],
            engine_autostart=False,
        )

        receiver = pynng.Pull0()
        receiver.listen(temp_ipc_paths['out1'])
        receiver.recv_timeout = 2000

        processor = SimpleProcessor()
        engine = Engine(settings=settings, processor=processor)

        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            engine.start()
            time.sleep(0.1)

            # Send multiple messages rapidly
            num_messages = 10
            for i in range(num_messages):
                sender.send(f"message {i}".encode())
                time.sleep(0.01)  # Small delay

            # Receive all messages
            received = []
            for i in range(num_messages):
                result = receiver.recv()
                received.append(result)

            # Verify all messages received
            assert len(received) == num_messages
            for i, msg in enumerate(received):
                expected = f"PROCESSED: MESSAGE {i}".encode()
                assert msg == expected

        finally:
            engine.stop()
            sender.close()
            receiver.close()

    def test_invalid_output_address_handling(self, temp_ipc_paths, caplog):
        """Test that invalid output addresses are handled gracefully."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[
                temp_ipc_paths['out1'],  # Valid
                "invalid://bad.address",  # Invalid
                temp_ipc_paths['out2'],  # Valid
            ],
            engine_autostart=False,
            log_level="DEBUG",
        )

        # Create receivers for valid addresses
        receiver1 = pynng.Pull0()
        receiver1.listen(temp_ipc_paths['out1'])
        receiver1.recv_timeout = 1000

        receiver2 = pynng.Pull0()
        receiver2.listen(temp_ipc_paths['out2'])
        receiver2.recv_timeout = 1000

        processor = SimpleProcessor()

        # Engine creation should succeed despite invalid address
        with caplog.at_level(logging.ERROR):
            engine = Engine(settings=settings, processor=processor)

        # Should have logged error for invalid address
        assert any("Failed to connect output socket" in record.message
                   for record in caplog.records)

        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            engine.start()
            time.sleep(0.1)

            # Send message
            sender.send(b"test")

            # Valid receivers should still work
            result1 = receiver1.recv()
            result2 = receiver2.recv()

            expected = b"PROCESSED: TEST"
            assert result1 == expected
            assert result2 == expected

        finally:
            engine.stop()
            sender.close()
            receiver1.close()
            receiver2.close()


class TestEngineMultiOutputEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_message_handling(self, temp_ipc_paths):
        """Test handling of empty messages."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[temp_ipc_paths['out1']],
            engine_autostart=False,
        )

        receiver = pynng.Pull0()
        receiver.listen(temp_ipc_paths['out1'])
        receiver.recv_timeout = 500

        processor = SimpleProcessor()
        engine = Engine(settings=settings, processor=processor)

        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            engine.start()
            time.sleep(0.1)

            # Send empty message
            sender.send(b"")
            time.sleep(0.1)

            # Should timeout - empty messages are skipped
            with pytest.raises(pynng.Timeout):
                receiver.recv()

        finally:
            engine.stop()
            sender.close()
            receiver.close()

    def test_large_message_handling(self, temp_ipc_paths):
        """Test handling of large messages to multiple outputs."""
        settings = ServiceSettings(
            engine_addr=temp_ipc_paths['engine'],
            manager_addr=temp_ipc_paths['manager'],
            out_addr=[temp_ipc_paths['out1'], temp_ipc_paths['out2']],
            engine_autostart=False,
        )

        receivers = []
        for addr in [temp_ipc_paths['out1'], temp_ipc_paths['out2']]:
            receiver = pynng.Pull0()
            receiver.listen(addr)
            receiver.recv_timeout = 2000
            receivers.append(receiver)

        processor = SimpleProcessor()
        engine = Engine(settings=settings, processor=processor)

        sender = pynng.Pair0()
        sender.dial(temp_ipc_paths['engine'])

        try:
            engine.start()
            time.sleep(0.1)

            # Send large message (1MB)
            large_message = b"x" * (1024 * 1024)
            sender.send(large_message)

            # All receivers should get the processed large message
            for receiver in receivers:
                result = receiver.recv()
                assert len(result) > 1024 * 1024  # Should be larger due to prefix
                assert result.startswith(b"PROCESSED: ")

        finally:
            engine.stop()
            sender.close()
            for receiver in receivers:
                receiver.close()
