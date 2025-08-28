from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import pynng
import errno
import socket


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
    def create(self, addr: str) -> EngineSocket: ...


class NngPairSocketFactory:
    """Default factory using pynng.Pair0 and binding to the given address."""
    def create(self, addr: str) -> EngineSocket:
        sock = pynng.Pair0()
        if addr.startswith("ipc://"):
            ipc_path = Path(addr.replace("ipc://", ""))
            try:
                if ipc_path.exists():
                    ipc_path.unlink()
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise

        elif addr.startswith("tcp://"):
            addr_parts = addr.replace("tcp://", "").split(":")
            host = addr_parts[0] or "127.0.0.1"
            port = int(addr_parts[1])

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((host, port)) == 0:
                    raise OSError(f"Port {port} is already in use")

        try:
            sock.listen(addr)
            return sock
        except pynng.NNGException:
            sock.close()
            raise
