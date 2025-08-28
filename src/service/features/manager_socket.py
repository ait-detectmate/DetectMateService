from __future__ import annotations
from pathlib import Path
import errno
import socket
from typing import Protocol, runtime_checkable

import pynng
from service.features.types import Loggable


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
    def create(self, addr: str, logger: Loggable) -> ManagerSocket: ...


class NngRepSocketFactory:
    """Default factory using pynng.Rep0 with proper error handling."""
    def create(self, addr: str, logger: Loggable) -> ManagerSocket:
        sock = pynng.Rep0()

        # Handle IPC socket cleanup
        if addr.startswith("ipc://"):
            ipc_path = Path(addr.replace("ipc://", ""))
            try:
                if ipc_path.exists():
                    ipc_path.unlink()
            except OSError as exc:
                if exc.errno != errno.ENOENT:  # ignore file doesn't exist errors
                    logger.log.error("Failed to remove IPC file: %s", exc)
                    raise

        # Handle TCP port binding conflicts
        elif addr.startswith("tcp://"):
            try:
                # Parse host and port
                addr_parts = addr.replace("tcp://", "").split(":")
                host = addr_parts[0] if addr_parts[0] else "127.0.0.1"
                port = int(addr_parts[1])

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
                        logger.log.debug("Socket close error: %s", sock_err)
            except (ValueError, IndexError, OSError) as exc:
                logger.log.error("Invalid TCP address or port in use: %s", exc)
                raise

        try:
            sock.listen(addr)
            logger.log.info("Manager listening on %s", addr)
            return sock
        except pynng.NNGException as exc:
            logger.log.error("Failed to bind to address %s: %s", addr, exc)
            sock.close()
            raise
