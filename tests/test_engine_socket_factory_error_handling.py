"""Tests for engine socket factory error handling."""
import errno
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pynng
import pytest

from service.features.engine_socket import NngPairSocketFactory


# Fixtures
@pytest.fixture
def mock_logger():
    """Create a mock logger for testing."""
    return MagicMock()


@pytest.fixture
def available_tcp_port():
    """Find and return an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def socket_manager():
    """Manage socket lifecycle with guaranteed cleanup."""
    sockets = []

    def track(sock):
        sockets.append(sock)
        return sock

    yield track

    for sock in sockets:
        try:
            sock.close()
        except pynng.NNGException:
            pass


# Happy path tests
def test_ipc_socket_creation(tmp_path, mock_logger, socket_manager):
    """Test successful IPC socket creation."""
    ipc_file = tmp_path / "test.ipc"
    factory = NngPairSocketFactory()

    sock = socket_manager(factory.create(f"ipc://{ipc_file}", mock_logger))
    assert sock is not None


def test_tcp_socket_creation(available_tcp_port, mock_logger, socket_manager):
    """Test successful TCP socket creation."""
    factory = NngPairSocketFactory()

    sock = socket_manager(factory.create(f"tcp://127.0.0.1:{available_tcp_port}", mock_logger))
    assert sock is not None


def test_nonexistent_ipc_file_cleanup(tmp_path, mock_logger, socket_manager):
    """Test that non-existent IPC files don't cause errors."""
    ipc_file = tmp_path / "nonexistent.ipc"
    factory = NngPairSocketFactory()

    sock = socket_manager(factory.create(f"ipc://{ipc_file}", mock_logger))
    assert sock is not None


# Error handling tests
def test_ipc_cleanup_permission_error(tmp_path, mock_logger):
    """Test error handling when IPC file cleanup fails."""
    ipc_file = tmp_path / "test.ipc"
    ipc_file.touch()

    factory = NngPairSocketFactory()

    with patch.object(Path, "unlink", side_effect=OSError(errno.EPERM, "Permission denied")):
        with pytest.raises(OSError, match="Permission denied"):
            factory.create(f"ipc://{ipc_file}", mock_logger)


def test_tcp_port_already__in_use(available_tcp_port, mock_logger):
    """Test error when TCP port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", available_tcp_port))

        factory = NngPairSocketFactory()
        with pytest.raises(pynng.exceptions.AddressInUse):
            factory.create(f"tcp://127.0.0.1:{available_tcp_port}", mock_logger)


def test_invalid_address_scheme(mock_logger):
    """Test error handling for invalid address schemes."""
    factory = NngPairSocketFactory()

    with pytest.raises(pynng.exceptions.NotSupported):
        factory.create("invalid://address", mock_logger)


def test_socket_listen_failure(mock_logger):
    """Test error handling when socket listen fails."""
    factory = NngPairSocketFactory()

    with patch('pynng.Pair0') as mock_pair:
        mock_sock = MagicMock()
        mock_pair.return_value = mock_sock
        mock_sock.listen.side_effect = pynng.NNGException("Listen failed", 1)

        with pytest.raises(pynng.NNGException, match="Listen failed"):
            factory.create("ipc:///tmp/test.ipc", mock_logger)

        mock_sock.close.assert_called_once()


def test_socket_creation_failure(mock_logger):
    """Test error handling when socket creation fails."""
    factory = NngPairSocketFactory()

    with patch('pynng.Pair0', side_effect=pynng.NNGException("Creation failed", 1)):
        with pytest.raises(pynng.NNGException, match="Creation failed"):
            factory.create("ipc:///tmp/test.ipc", mock_logger)
