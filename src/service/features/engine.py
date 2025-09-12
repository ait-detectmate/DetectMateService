import threading
import time
import pynng
from abc import ABC
from typing import Optional
from service.settings import ServiceSettings
from service.features.engine_socket import (
    EngineSocketFactory,
    NngPairSocketFactory,
)

from library.processor import BaseProcessor


class DefaultProcessor(BaseProcessor):
    """A default processor that does nothing.

    This is necessary to satisfy the abstract BaseProcessor requirement.
    """
    def process(self, raw: bytes) -> bytes | None:
        return raw


class Engine(ABC):
    """Engine drives a background thread that reads raw messages over PAIR0,
    calls 'self.process()', and sends outputs back over the same socket.

    The socket implementation is provided by an EngineSocketFactory.
    Default: NngPairSocketFactory (pynng.Pair0).
    """

    def __init__(
            self,
            settings: Optional[ServiceSettings] = None,
            processor: BaseProcessor = DefaultProcessor(),
            socket_factory: Optional[EngineSocketFactory] = None
    ):
        self.settings: ServiceSettings = settings if settings is not None else ServiceSettings()
        self.processor = processor
        self._stop_event = threading.Event()

        # control flags
        self._running = False
        self._paused = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop, name="EngineLoop", daemon=True
        )

        # set up the engine socket via the factory abstraction
        addr = str(self.settings.engine_addr)
        self._engine_socket_factory: EngineSocketFactory = (
            socket_factory if socket_factory is not None else NngPairSocketFactory()
        )
        self._pair_sock = self._engine_socket_factory.create(addr)
        self._pair_sock.recv_timeout = self.settings.engine_recv_timeout

        # autostart if enabled
        if getattr(self.settings, "engine_autostart", True):
            self.start()

    def start(self) -> str:
        if not self._running:
            self._running = True
            self._thread.start()
            return "engine started"
        return "engine already running"

    def _run_loop(self) -> None:
        while self._running and not self._stop_event.is_set():
            if self._paused.is_set():
                time.sleep(0.1)
                continue

            # recv phase
            try:
                raw = self._pair_sock.recv()
            except pynng.Timeout:
                continue  # Timeout occurred, check running flag and continue
            except pynng.NNGException as e:
                # Socket likely closed during shutdown; leave loop if we're stopping.
                if not self._running or self._stop_event.is_set():
                    break
                self._log_engine_error("recv", e)
                continue

            # process phase
            try:
                out = self.processor.process(raw)
            except Exception as e:
                # Log unexpected processing errors; don't silently swallow them.
                self._log_engine_error("process", e)
                continue

            if out is None:
                continue

            # send phase
            try:
                self._pair_sock.send(out)
            except pynng.NNGException as e:
                self._log_engine_error("send", e)
                continue

    def _log_engine_error(self, phase: str, exc: Exception) -> None:
        logger = getattr(self, "log", None)
        if logger:
            logger.exception("Engine error during %s: %s", phase, exc)

    def stop(self) -> None:
        """Stop the engine loop and clean up resources.

        Returns:
            None on success
        Raises:
            RuntimeError: If stopping fails for any reason
        """
        if not self._running:
            return None
        self._running = False
        self._stop_event.set()
        # Closing the socket will raise in the recv() and let the thread exit
        try:
            self._pair_sock.close()
        except pynng.NNGException as e:
            raise RuntimeError(f"Failed to close engine socket: {e}") from e
        try:
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():
                raise RuntimeError("Engine thread failed to stop within timeout")
        except Exception as e:
            raise RuntimeError(f"Failed to join engine thread: {e}") from e
        return None
