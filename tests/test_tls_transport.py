"""Tests for TLS support in the socket factory and engine output sockets.

Covers:
  - NngPairSocketFactory: tls+tcp happy path and error cases
  - Engine._setup_output_sockets: tls_config assignment ordering
"""
import socket
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pynng
import pytest

from service.features.engine import Engine
from service.features.engine_socket import NngPairSocketFactory
from service.settings import ServiceSettings, TlsInputConfig, TlsOutputConfig


@pytest.fixture
def mock_logger():
    return MagicMock()


@pytest.fixture
def socket_manager():
    """Track and close pynng sockets after each test."""
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


@pytest.fixture
def available_port():
    """Return a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def self_signed_cert(tmp_path):
    """Generate a self-signed server cert+key PEM and CA cert using openssl.

    The combined server PEM (cert + key in one file) is what pynng expects
    for cert_key_file on the server side.

    Returns a dict:
        server_pem: Path  , combined cert + key (used as cert_key_file)
        ca_pem:     Path  , CA cert (used as ca_file on client side)
    """
    ca_key = tmp_path / "ca.key"
    ca_pem = tmp_path / "ca.pem"
    server_key = tmp_path / "server.key"
    server_csr = tmp_path / "server.csr"
    server_crt = tmp_path / "server.crt"
    server_pem = tmp_path / "server.pem"

    subprocess.run(
        ["openssl", "genrsa", "-out", str(ca_key), "2048"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["openssl", "req", "-x509", "-new", "-nodes",
         "-key", str(ca_key), "-days", "1", "-out", str(ca_pem),
         "-subj", "/CN=DetectMate-Test-CA"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["openssl", "genrsa", "-out", str(server_key), "2048"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["openssl", "req", "-new",
         "-key", str(server_key), "-out", str(server_csr),
         "-subj", "/CN=127.0.0.1"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["openssl", "x509", "-req",
         "-in", str(server_csr),
         "-CA", str(ca_pem), "-CAkey", str(ca_key), "-CAcreateserial",
         "-out", str(server_crt), "-days", "1"],
        check=True, capture_output=True,
    )
    # pynng cert_key_file expects cert and key concatenated in one PEM file
    server_pem.write_bytes(server_crt.read_bytes() + server_key.read_bytes())

    return {"server_pem": server_pem, "ca_pem": ca_pem}


@pytest.fixture
def ipc_engine_addr(tmp_path):
    """IPC address for the engine input socket used in engine output tests."""
    return f"ipc://{tmp_path}/engine.ipc"


# ---------------------------------------------------------------------------
# NngPairSocketFactory, TLS error cases
# ---------------------------------------------------------------------------

def test_tls_tcp_no_tls_config_raises_value_error(available_port, mock_logger):
    """Factory raises ValueError immediately when tls+tcp is used without a
    config."""
    factory = NngPairSocketFactory()
    with pytest.raises(ValueError, match="tls_input"):
        factory.create(f"tls+tcp://127.0.0.1:{available_port}", mock_logger)


def test_tls_tcp_nonexistent_cert_raises(available_port, mock_logger):
    """Factory raises an exception when the cert file path does not exist."""
    tls_cfg = TlsInputConfig(cert_key_file=Path("/nonexistent/cert.pem"))
    factory = NngPairSocketFactory()
    with pytest.raises(Exception):  # pynng raises NNGException at TLSConfig or listen time
        factory.create(
            f"tls+tcp://127.0.0.1:{available_port}",
            mock_logger,
            tls_config=tls_cfg,
        )


# ---------------------------------------------------------------------------
# NngPairSocketFactory,  TLS happy path
# ---------------------------------------------------------------------------

def test_tls_tcp_socket_creation(available_port, mock_logger, socket_manager, self_signed_cert):
    """Factory creates a listening tls+tcp socket with a valid self-signed
    cert."""
    tls_cfg = TlsInputConfig(cert_key_file=self_signed_cert["server_pem"])
    factory = NngPairSocketFactory()

    sock = socket_manager(
        factory.create(
            f"tls+tcp://127.0.0.1:{available_port}",
            mock_logger,
            tls_config=tls_cfg,
        )
    )
    assert sock is not None


# ---------------------------------------------------------------------------
# NngPairSocketFactory, TLS config assigned before listen()
# ---------------------------------------------------------------------------

def test_tls_config_assigned_before_listen(available_port, mock_logger, tmp_path):
    """tls_config is set on the socket before listen() is called."""
    cert = tmp_path / "fake.pem"
    cert.touch()
    tls_cfg = TlsInputConfig(cert_key_file=cert)
    factory = NngPairSocketFactory()

    tls_config_at_listen_time = []

    with patch("service.features.engine_socket.pynng.Pair0") as MockPair0, \
            patch("service.features.engine_socket.pynng.TLSConfig") as MockTLSConfig:

        mock_sock = MagicMock()
        MockPair0.return_value = mock_sock
        mock_tls = MagicMock()
        MockTLSConfig.return_value = mock_tls
        MockTLSConfig.MODE_SERVER = pynng.TLSConfig.MODE_SERVER

        def capture_on_listen(addr):
            tls_config_at_listen_time.append(mock_sock.tls_config)

        mock_sock.listen.side_effect = capture_on_listen

        factory.create(
            f"tls+tcp://127.0.0.1:{available_port}",
            mock_logger,
            tls_config=tls_cfg,
        )

    assert len(tls_config_at_listen_time) == 1, "listen() was not called exactly once"
    assert tls_config_at_listen_time[0] is mock_tls, (
        "tls_config was not assigned before listen()"
    )


def test_non_tls_socket_has_no_tls_config(available_port, mock_logger, tmp_path):
    """Factory does not assign tls_config when creating a plain tcp socket."""
    factory = NngPairSocketFactory()

    with patch("service.features.engine_socket.pynng.Pair0") as MockPair0:
        mock_sock = MagicMock()
        MockPair0.return_value = mock_sock
        mock_sock.tls_config = None  # start as None

        def verify_no_tls_on_listen(addr):
            pass  # don't actually listen

        mock_sock.listen.side_effect = verify_no_tls_on_listen

        factory.create(f"tcp://127.0.0.1:{available_port}", mock_logger)

    assert mock_sock.tls_config is None, (
        "tls_config should not be set for a plain tcp socket"
    )


# ---------------------------------------------------------------------------
# Engine._setup_output_sockets, TLS config assigned before dial()
# ---------------------------------------------------------------------------

def test_engine_output_tls_config_assigned_before_dial(tmp_path, ipc_engine_addr):
    """Engine sets tls_config on the output socket before calling dial().

    pynng requires tls_config to be assigned before dial() , the test
    captures the value of tls_config at the moment dial() fires.
    """
    ca = tmp_path / "ca.pem"
    ca.touch()
    settings = ServiceSettings(
        engine_addr=ipc_engine_addr,
        http_host="127.0.0.1",
        http_port=8097,
        engine_autostart=False,
        log_to_file=False,
        out_addr=["tls+tcp://detector:15200"],
        tls_output=TlsOutputConfig(ca_file=ca, server_name="detector"),
    )

    tls_config_at_dial = []
    mock_out_sock = MagicMock()

    def capture_on_dial(addr, block=True):
        tls_config_at_dial.append(mock_out_sock.tls_config)

    mock_out_sock.dial.side_effect = capture_on_dial

    with patch("service.features.engine.pynng.Pair0", return_value=mock_out_sock), \
            patch("service.features.engine.pynng.TLSConfig") as MockTLSConfig:
        mock_tls = MagicMock()
        MockTLSConfig.return_value = mock_tls
        MockTLSConfig.MODE_CLIENT = pynng.TLSConfig.MODE_CLIENT

        engine = Engine(
            settings=settings,
            processor=MagicMock(spec=["process"]),
        )

    assert len(tls_config_at_dial) == 1, "dial() was not called exactly once"
    assert tls_config_at_dial[0] is mock_tls, (
        "tls_config was not assigned before dial()"
    )

    engine._pair_sock.close()
