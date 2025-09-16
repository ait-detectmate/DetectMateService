from __future__ import annotations
from pathlib import Path
import errno
import socket
from typing import Protocol, runtime_checkable
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
                host = parsed.hostname or "127.0.0.1"
                port = parsed.port
                if not port:
                    raise ValueError(f"Missing port in TCP address: {addr}")

                # Check if port is already in use
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    if s.connect_ex((host, port)) == 0:
                        raise OSError(f"Port {port} is already in use")
                finally:
                    try:
                        s.close()
                    except (OSError, socket.error) as sock_err:
                        logger.debug("Socket close error: %s", sock_err)
            except (ValueError, IndexError, OSError) as exc:
                logger.error("Invalid TCP address or port in use: %s", exc)
                raise

        try:
            sock.listen(addr)
            logger.info("Manager listening on %s", addr)
            return sock
        except pynng.NNGException as exc:
            logger.error("Failed to bind to address %s: %s", addr, exc)
            sock.close()
            raise
