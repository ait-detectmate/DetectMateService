from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable, cast
import logging
import pynng
import errno
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
            if not parsed.port:
                raise ValueError(f"Missing port in TCP address: {addr}")

        try:
            sock.listen(addr)
            return cast(EngineSocket, sock)  # use cast to tell mypy this implements EngineSocket
        except pynng.NNGException as e:
            logger.error("Failed to bind to address %s: %s", addr, e)
            sock.close()
            raise
