import errno
import socket
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import pynng

from service.features.engine_socket import NngPairSocketFactory


mock_logger = MagicMock()


class TestEngineSocketFactoryErrorHandling:
    def test_successful_ipc_creation(self, tmp_path):
        """Test successful IPC socket creation."""
        ipc_file = tmp_path / "test.ipc"
        factory = NngPairSocketFactory()

        sock = factory.create(f"ipc://{ipc_file}", mock_logger)
        assert sock is not None
        sock.close()

    def test_successful_tcp_creation(self):
        """Test successful TCP socket creation."""
        # Find an available port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        factory = NngPairSocketFactory()
        sock = factory.create(f"tcp://127.0.0.1:{port}", mock_logger)
        assert sock is not None
        sock.close()

    def test_ipc_file_cleanup_error(self, tmp_path):
        """Test error handling when IPC file cleanup fails."""
        ipc_file = tmp_path / "test.ipc"
        ipc_file.touch()  # create the file first

        factory = NngPairSocketFactory()

        with patch.object(Path, "unlink", side_effect=OSError(errno.EPERM, "Permission denied")):
            with pytest.raises(OSError, match="Permission denied"):
                factory.create(f"ipc://{ipc_file}", mock_logger)

    def test_tcp_port_already_in_use(self):
        """Test error when TCP port is already in use."""
        # Bind to a port first
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

            factory = NngPairSocketFactory()
            with pytest.raises(pynng.exceptions.AddressInUse):
                factory.create(f"tcp://127.0.0.1:{port}", mock_logger)

    def test_invalid_address(self):
        """Test error handling for invalid addresses."""
        factory = NngPairSocketFactory()

        with pytest.raises(pynng.exceptions.NotSupported):
            factory.create("invalid://address", mock_logger)

    def test_socket_listen_failure(self):
        """Test error handling when socket listen fails."""
        factory = NngPairSocketFactory()

        with patch('pynng.Pair0') as mock_pair:
            mock_sock = MagicMock()
            mock_pair.return_value = mock_sock
            # Create a proper NNGException with errno
            mock_sock.listen.side_effect = pynng.NNGException("Listen failed", 1)

            with pytest.raises(pynng.NNGException, match="Listen failed"):
                factory.create("ipc:///tmp/test.ipc", mock_logger)

            # Verify socket is closed on error
            mock_sock.close.assert_called_once()

    def test_socket_creation_failure(self):
        """Test error handling when socket creation fails."""
        factory = NngPairSocketFactory()

        # Create a proper NNGException with errno
        with patch('pynng.Pair0', side_effect=pynng.NNGException("Creation failed", 1)):
            with pytest.raises(pynng.NNGException, match="Creation failed"):
                factory.create("ipc:///tmp/test.ipc", mock_logger)

    def test_nonexistent_ipc_file_handling(self, tmp_path):
        """Test that non-existent IPC files don't cause errors."""
        ipc_file = tmp_path / "nonexistent.ipc"

        factory = NngPairSocketFactory()
        sock = factory.create(f"ipc://{ipc_file}", mock_logger)
        assert sock is not None
        sock.close()
