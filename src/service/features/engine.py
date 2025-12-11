import threading
import pynng
import logging
from abc import ABC
from typing import Optional, List
from service.settings import ServiceSettings
from service.features.engine_socket import (
    EngineSocketFactory,
    NngPairSocketFactory,
)

# TODO: replace these imports with the actual library implementations
from library.processor import BaseProcessor, ProcessorException


class EngineException(Exception):
    """Custom exception for engine-related errors."""
    pass


class DefaultProcessor(BaseProcessor):
    """A default processor that does nothing.

    This is necessary to satisfy the abstract BaseProcessor requirement.
    """
    def __call__(self, raw: bytes) -> bytes | None:
        return raw


class Engine(ABC):
    """Engine drives a background thread that reads raw messages over PAIR0,
    calls 'self.process()', and sends outputs to multiple destinations.

    The socket implementation is provided by an EngineSocketFactory.
    Default: NngPairSocketFactory (pynng.Pair0).
    """

    def __init__(
            self,
            settings: Optional[ServiceSettings] = None,
            processor: BaseProcessor = DefaultProcessor(),
            socket_factory: Optional[EngineSocketFactory] = None,
            logger: Optional[logging.Logger] = None
    ):
        self.settings: ServiceSettings = settings if settings is not None else ServiceSettings()
        self.processor = processor
        self._stop_event = threading.Event()
        self.log = logger or logging.getLogger(__name__)

        # control flags
        self._running = False
        self._thread = threading.Thread(
            target=self._run_loop, name="EngineLoop", daemon=True
        )

        # set up the engine socket via the factory abstraction
        addr = str(self.settings.engine_addr)
        self._engine_socket_factory: EngineSocketFactory = (
            socket_factory if socket_factory is not None else NngPairSocketFactory()
        )
        self._pair_sock = self._engine_socket_factory.create(addr, self.log)
        self._pair_sock.recv_timeout = self.settings.engine_recv_timeout

        # set up output sockets for multiple destinations
        self._out_sockets: List[pynng.Socket] = []
        try:
            self._setup_output_sockets()
        except Exception:
            # if outputs fail to connect, also close input socket to avoid leaks
            try:
                self._pair_sock.close()
            except pynng.NNGException as e:
                self.log.warning("Failed to close engine input socket after setup failure: %s", e)
            raise

        # autostart if enabled
        if getattr(self.settings, "engine_autostart", True):
            self.start()

    def _setup_output_sockets(self) -> None:
        """Create and connect output sockets for all destinations in out_addr.

        Attempts to connect to all configured addresses. If a
        destination is unavailable, the socket remains in a dialing
        state (background retry).
        """
        if not self.settings.out_addr:
            self.log.info("No output addresses configured, processed messages will not be forwarded")
            return

        for addr in self.settings.out_addr:
            addr_str = str(addr)
            try:
                # Use Pair socket to match the input socket type of other services
                sock = pynng.Pair0()
                # Ensure blocking dial honors timeout
                sock.dial_timeout = self.settings.out_dial_timeout

                # Set buffer sizes to 0 to minimize buffering and drop messages if peer not ready
                sock.send_buffer_size = 0
                sock.recv_buffer_size = 0

                # Non-blocking dial: returns immediately, connects in background
                sock.dial(addr_str, block=False)
                self._out_sockets.append(sock)
                self.log.info(f"Initialized output socket for {addr_str} (background connect)")
            except Exception as e:
                # This catches invalid URLs or other immediate setup errors
                self.log.error(f"Failed to initialize output socket for {addr_str}: {e}")
                # We attempt to continue with other sockets rather than crashing entirely

    def start(self) -> str:
        if not self._running:
            self._running = True
            self._thread.start()
            return "engine started"
        return "engine already running"

    def _run_loop(self) -> None:
        while self._running and not self._stop_event.is_set():

            # recv phase
            try:
                raw = self._pair_sock.recv()
                if raw is None or len(raw) == 0:
                    self.log.debug("Engine: Received empty message, skipping")
                    continue

                self.log.debug(f"Engine: Received {len(raw)} bytes from socket")
            except pynng.Timeout:
                continue  # Timeout occurred, check running flag and continue
            except pynng.NNGException as e:
                # Socket likely closed during shutdown; leave loop if we're stopping.
                if not self._running or self._stop_event.is_set():
                    break
                self.log.exception("Engine error during receive: %s", e)
                continue
            except Exception as e:
                self.log.exception("Unexpected engine error during receive: %s", e)
                continue

            # process phase
            try:
                self.log.debug("Engine: Calling processor...")
                out = self.processor(raw)
                self.log.debug(f"Engine: Processor returned: {out!r}")
            except ProcessorException as e:
                self.log.error("Processor error: %s", e)
                continue
            except Exception as e:
                self.log.exception("Engine error during process: %s", e)
                continue

            if out is None:
                self.log.debug("Engine: Processor returned None, skipping send")
                continue

            # send phase
            if self._out_sockets:
                # Multi-destination mode: send to all configured outputs
                self._send_to_outputs(out)
            else:
                # Backwards-compatible mode: no outputs configured, reply on PAIR socket
                try:
                    self.log.debug(
                        "Engine: No output sockets configured, "
                        "sending reply back via engine socket"
                    )
                    self._pair_sock.send(out)
                    self.log.debug("Engine: Reply sent on engine socket")
                except pynng.NNGException as e:
                    self.log.error("Engine error sending reply on engine socket: %s", e)
                    continue

    def _send_to_outputs(self, data: bytes) -> None:
        """Send processed data to all configured output destinations."""
        if not self._out_sockets:
            self.log.debug("Engine: No output sockets configured, skipping send")
            return

        for i, sock in enumerate(self._out_sockets):
            try:
                self.log.debug(f"Engine: Sending {len(data)} bytes to output socket {i}")
                # Non-blocking send is preferred to avoid stalling the engine loop
                # Pair0 with block=False will raise TryAgain if the peer is disconnected
                sock.send(data, block=False)
                self.log.debug(f"Engine: Send completed to output socket {i}")
            except pynng.TryAgain:
                self.log.warning(f"Engine: Output socket {i} not ready or disconnected, dropping message")
            except pynng.NNGException as e:
                self.log.error(f"Engine error sending to output socket {i}: {e}")
                continue

    def stop(self) -> None | str:
        """Stop the engine loop and clean up resources.

        Returns:
            None on success
        Raises:
            EngineException: If stopping fails for any reason
        """
        if not self._running:
            if self.log:
                self.log.debug("Engine is not running, skipping stop")
            return None
        self._running = False
        self._stop_event.set()

        # Close input socket
        try:
            self._pair_sock.close()
        except pynng.NNGException as e:
            raise EngineException(f"Failed to close engine socket: {e}") from e

        # Close all output sockets
        for i, sock in enumerate(self._out_sockets):
            try:
                sock.close()
                self.log.debug(f"Closed output socket {i}")
            except pynng.NNGException as e:
                self.log.error(f"Failed to close output socket {i}: {e}")

        try:
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():
                raise EngineException("Engine thread failed to stop within timeout")
            elif self.log:
                self.log.debug("Engine stopped successfully")
        except Exception as e:
            raise EngineException(f"Failed to join engine thread: {e}") from e
        return None
