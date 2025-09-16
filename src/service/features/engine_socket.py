from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable
import logging
import pynng
import errno
import socket
from urllib.parse import urlparse


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
    def create(self, addr: str, logger: logging.Logger) -> EngineSocket: ...


class NngPairSocketFactory:
    """Default factory using pynng.Pair0 and binding to the given address."""
    def create(self, addr: str, logger: logging.Logger) -> EngineSocket:
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
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port
            if not port:
                raise ValueError(f"Missing port in TCP address: {addr}")

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((host, port)) == 0:
                    logger.error("Port %s is already in use", port)
                    raise OSError(f"Port {port} is already in use")

        try:
            sock.listen(addr)
            return sock
        except pynng.NNGException as e:
            logger.error("Failed to bind to address %s: %s", addr, e)
            sock.close()
            raise
