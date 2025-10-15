from __future__ import annotations
from pathlib import Path
import errno
from typing import Protocol, runtime_checkable, cast
from urllib.parse import urlparse

import pynng
import logging


@runtime_checkable
class ManagerSocket(Protocol):
    """Minimal socket interface the Manager depends on."""
    def recv(self) -> bytes: ...
    def send(self, data: bytes) -> None: ...
    def close(self) -> None: ...
    def listen(self, addr: str) -> None: ...
    recv_timeout: int


class ManagerSocketFactory(Protocol):
    """Factory that creates bound ManagerSocket instances."""
    def create(self, addr: str, logger: logging.Logger) -> ManagerSocket: ...


class NngRepSocketFactory:
    """Default factory using pynng.Rep0 with proper error handling."""
    def create(self, addr: str, logger: logging.Logger) -> ManagerSocket:
        sock = pynng.Rep0()
        parsed = urlparse(addr)
        if parsed.scheme == "ipc":
            ipc_path = Path(parsed.path)
            try:
                if ipc_path.exists():
                    ipc_path.unlink()
            except OSError as exc:
                if exc.errno != errno.ENOENT:  # ignore file doesn't exist errors
                    logger.error("Failed to remove IPC file: %s", exc)
                    raise

        # Handle TCP port binding conflicts
        elif parsed.scheme == "tcp":
            try:
                if not parsed.port:
                    raise ValueError(f"Missing port in TCP address: {addr}")
            except (ValueError, IndexError, OSError) as exc:
                logger.error("Invalid TCP address or port in use: %s", exc)
                raise

        try:
            sock.listen(addr)
            logger.info("Manager listening on %s", addr)
            return cast(ManagerSocket, sock)  # use cast to tell mypy this implements ManagerSocket
        except pynng.NNGException as exc:
            logger.error("Failed to bind to address %s: %s", addr, exc)
            sock.close()
            raise
