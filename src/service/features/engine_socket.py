from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable, cast
import logging
import pynng
import errno
from urllib.parse import urlparse
from service.settings import TlsInputConfig


@runtime_checkable
class EngineSocket(Protocol):
    """Minimal socket interface the Engine depends on."""

    def recv(self) -> bytes: ...
    def send(self, data: bytes) -> None: ...
    def close(self) -> None: ...
    def listen(self, addr: str) -> None: ...
    recv_timeout: int


class EngineSocketFactory(Protocol):
    """Factory that creates bound EngineSocket instances for a given
    address."""

    def create(
        self,
        addr: str,
        logger: logging.Logger,
        tls_config: Optional[TlsInputConfig] = None,
    ) -> EngineSocket: ...


class NngPairSocketFactory:
    """Default factory using pynng.Pair0 and binding to the given address."""

    def create(
        self,
        addr: str,
        logger: logging.Logger,
        tls_config: Optional[TlsInputConfig] = None,
    ) -> EngineSocket:
        sock = pynng.Pair0()
        parsed = urlparse(addr)
        if parsed.scheme == "ipc":
            ipc_path = Path(parsed.path)
            try:
                if ipc_path.exists():
                    ipc_path.unlink()
            except OSError as e:
                if e.errno != errno.ENOENT:
                    logger.error("Failed to remove IPC file: %s", e)
                    raise

        elif parsed.scheme == "tcp":
            if not parsed.port:
                raise ValueError(f"Missing port in TCP address: {addr}")

        elif parsed.scheme == "tls+tcp":
            if tls_config is None:
                sock.close()
                raise ValueError(
                    f"Address {addr} uses tls+tcp:// but no TLS config was provided. "
                    "Set tls_input in your settings."
                )
            cfg = pynng.TLSConfig(
                pynng.TLSConfig.MODE_SERVER,
                cert_key_file=str(tls_config.cert_key_file),
            )
            sock.tls_config = cfg
        try:
            sock.listen(addr)
            return cast(EngineSocket, sock)  # use cast to tell mypy this implements EngineSocket
        except pynng.NNGException as e:
            logger.error("Failed to bind to address %s: %s", addr, e)
            sock.close()
            raise
