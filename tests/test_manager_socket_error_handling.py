import errno
import socket
from pathlib import Path
from unittest.mock import patch, MagicMock
from pynng.exceptions import NNGException, AddressInUse
import pytest

from service.core import Service
from service.settings import ServiceSettings


class MockTestService(Service):
    """Class for testing."""
    component_type = "test"

    def process(self, raw_message: bytes) -> bytes | None:
        return raw_message  # echo for testing


class TestManagerSocketErrorHandling:
    def test_ipc_file_remove_error(self, tmp_path):
        """Test error handling when removing an IPC file fails for unexpected
        reasons."""
        ipc_file = tmp_path / "bad.ipc"
        ipc_file.touch()  # ensure exists -> hit unlink branch

        settings = ServiceSettings(
            manager_addr=f"ipc://{ipc_file}",
            engine_autostart=False,
            log_level="ERROR",
        )

        # Stub the service logger so we can assert the error log call
        mock_logger = MagicMock()
        with patch.object(Service, "_build_logger", return_value=mock_logger):
            # Simulate a non-ENOENT unlink error (eg. EPERM)
            with patch.object(Path, "unlink", side_effect=OSError(errno.EPERM, "Permission denied")):
                with pytest.raises(OSError):
                    MockTestService(settings=settings)

        # Ensure the error was logged by the service logger
        assert mock_logger.error.called
        assert any(
            "Failed to remove IPC file" in (call.args[0] if call.args else "")
            for call in mock_logger.error.call_args_list
        )

    def test_tcp_port_already_in_use(self, caplog):
        """Test error handling when TCP port is already in use."""
        settings = ServiceSettings(
            manager_addr="tcp://127.0.0.1:9999",
            engine_autostart=False,
            log_level="ERROR",
        )

        # Mock pynng to raise AddressInUse when creating sockets
        with patch('pynng.Rep0') as mock_rep:
            mock_rep.return_value.listen.side_effect = AddressInUse("Address in use", errno.EADDRINUSE)

            # Should raise an pynng.exceptions.AddressInUse when port is already in use
            with pytest.raises(AddressInUse, match="Address in use"):
                MockTestService(settings=settings)

    def test_invalid_tcp_address(self, caplog):
        """Test error handling for invalid TCP addresses."""
        settings = ServiceSettings(
            manager_addr="tcp://invalid-address:not-a-port",
            engine_autostart=False,
            log_level="ERROR",
        )

        # Should raise a ValueError for invalid port
        with pytest.raises(ValueError):
            MockTestService(settings=settings)

    def test_socket_bind_error(self, caplog):
        """Test error handling when socket binding fails."""
        settings = ServiceSettings(
            manager_addr="tcp://127.0.0.1:9999",
            engine_autostart=False,
            log_level="ERROR",
        )

        # Mock pynng to raise an exception on listen
        with patch('pynng.Rep0') as mock_rep:
            mock_sock = MagicMock()
            mock_rep.return_value = mock_sock
            # Create a proper NNGException with errno
            mock_sock.listen.side_effect = NNGException("Bind failed", 1)

            # Should raise NNGException when binding fails
            with pytest.raises(NNGException):
                MockTestService(settings=settings)

    def test_successful_ipc_binding(self, tmp_path):
        """Test successful IPC socket binding."""
        ipc_file = tmp_path / "test.ipc"

        settings = ServiceSettings(
            manager_addr=f"ipc://{ipc_file}",
            engine_autostart=False,
            log_level="ERROR",
        )

        # Should not raise any exceptions
        service = MockTestService(settings=settings)
        service._close_manager()

    def test_successful_tcp_binding(self):
        """Test successful TCP socket binding."""
        # Find an available port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        settings = ServiceSettings(
            manager_addr=f"tcp://127.0.0.1:{port}",
            engine_autostart=False,
            log_level="ERROR",
        )

        # Should not raise any exceptions
        service = MockTestService(settings=settings)
        service._close_manager()

    def test_missing_ipc_file_handling(self, tmp_path):
        """Test that missing IPC files don't cause errors."""
        ipc_file = tmp_path / "nonexistent.ipc"

        settings = ServiceSettings(
            manager_addr=f"ipc://{ipc_file}",
            engine_autostart=False,
            log_level="ERROR",
        )

        # Should not raise any exceptions even though file doesn't exist
        service = MockTestService(settings=settings)
        service._close_manager()
