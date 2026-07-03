import threading
import pynng
import logging
import time
from abc import ABC
from enum import Enum, auto
from typing import Any, Dict, Optional, List, Protocol
from prometheus_client import Counter
from service.settings import ServiceSettings
from service.features.engine_socket import (
    EngineSocketFactory,
    NngPairSocketFactory,
)

data_read_bytes_total = Counter(
    "data_read_bytes_total",
    "Total bytes read from input interfaces",
    ["component_type", "component_id"]
)

data_read_lines_total = Counter(
    "data_read_lines_total",
    "Total lines read from input interfaces",
    ["component_type", "component_id"]
)

data_written_bytes_total = Counter(
    "data_written_bytes_total",
    "Total bytes written to output interfaces",
    ["component_type", "component_id"]
)

data_written_lines_total = Counter(
    "data_written_lines_total",
    "Total lines written to output interfaces",
    ["component_type", "component_id"]
)

data_dropped_bytes_total = Counter(
    "data_dropped_bytes_total",
    "Total bytes dropped due to disconnected or slow downstream peers",
    ["component_type", "component_id"]
)

data_dropped_lines_total = Counter(
    "data_dropped_lines_total",
    "Total lines dropped due to disconnected or slow downstream peers",
    ["component_type", "component_id"]
)

processing_errors_total = Counter(
    "processing_errors_total",
    "Total number of exceptions raised during process()",
    ["component_type", "component_id"]
)


class EngineException(Exception):
    """Custom exception for engine-related errors."""


class EngineState(Enum):
    """Lifecycle state of an Engine, transitioned only under _lifecycle_lock.

    READY    - sockets open, no loop thread running (initial state)
    RUNNING  - loop thread active, processing messages
    STOPPING - stop() requested; _run_loop must exit but its death isn't
               confirmed yet. Distinct from RUNNING so the loop notices the
               request immediately, and distinct from STOPPED so start()
               can't spin up a second thread while the first might still be
               alive.
    STOPPED  - the loop thread is confirmed dead and its sockets closed (or
               close was attempted); start() must recreate the sockets
    """
    READY = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()


class Processor(Protocol):
    """Protocol defining the interface for message processors.

    Any object with a process() method can be used as a processor. This
    is typically a Service instance.
    """

    def process(self, raw_message: bytes) -> bytes | None:
        """Process a raw message and return the result or None."""
        ...


class Engine(ABC):
    """Engine drives a background thread that reads raw messages over PAIR0,
    calls processor.process(), and sends outputs to multiple destinations.

    The socket implementation is provided by an EngineSocketFactory.
    Default: NngPairSocketFactory (pynng.Pair0).

    The processor must be an object with a process(bytes) -> bytes | None method.
    Typically this is a Service instance that delegates to library components.
    """

    def __init__(
            self,
            settings: Optional[ServiceSettings] = None,
            processor: Optional[Processor] = None,
            socket_factory: Optional[EngineSocketFactory] = None,
            logger: Optional[logging.Logger] = None
    ):
        self.settings: ServiceSettings = settings if settings is not None else ServiceSettings()

        if processor is None:
            raise ValueError(
                "Engine requires a processor with a process() method. "
                "Typically you should pass 'self' from the Service class."
            )

        self.processor = processor
        self.log = logger or logging.getLogger(__name__)

        # serializes start()/stop() transitions so concurrent callers can't
        # both pass the "not running" guard and double-start/double-close
        self._lifecycle_lock = threading.Lock()

        self._state = EngineState.READY
        # created fresh on every start(); no thread exists until then
        self._thread: Optional[threading.Thread] = None

        # set up the engine socket via the factory abstraction
        addr = str(self.settings.engine_addr)
        self._engine_socket_factory: EngineSocketFactory = (
            socket_factory if socket_factory is not None else NngPairSocketFactory()
        )
        self._pair_sock = self._engine_socket_factory.create(
            addr, self.log, tls_config=self.settings.tls_input
        )
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

        self.log.debug("Engine initialized and ready.")

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
                sock.send_buffer_size = self.settings.engine_buffer_size
                sock.recv_buffer_size = self.settings.engine_buffer_size

                if addr_str.startswith("tls+tcp://"):
                    tls_out = self.settings.tls_output
                    # model_validator should catch this actually at startup
                    if tls_out is None:
                        sock.close()
                        raise ValueError(
                            f"Output address {addr_str} uses tls+tcp:// but tls_output "
                            "is not configured. Add a tls_output block with ca_file."
                        )
                    cfg = pynng.TLSConfig(
                        pynng.TLSConfig.MODE_CLIENT,
                        ca_files=str(tls_out.ca_file),
                        server_name=tls_out.server_name,
                    )
                    sock.tls_config = cfg

                # Non-blocking dial: returns immediately, connects in background
                sock.dial(addr_str, block=False)
                self._out_sockets.append(sock)
                self.log.info(f"Initialized output socket for {addr_str} (background connect)")
            except Exception as e:
                # This catches invalid URLs or other immediate setup errors
                self.log.error(f"Failed to initialize output socket for {addr_str}: {e}")
                # We attempt to continue with other sockets rather than crashing entirely

    def start(self) -> str:
        """Start the engine loop.

        Returns:
            "engine started" or "engine already running"
        Raises:
            EngineException: If the loop thread fails to start
        """
        with self._lifecycle_lock:
            if self._state in (EngineState.RUNNING, EngineState.STOPPING):
                # STOPPING means a previous stop() couldn't confirm the loop
                # thread died.  refuse to start a second one on top of it.
                return "engine already running"

            previous_state = self._state  # READY or STOPPED, to roll back to on failure

            if self._state == EngineState.STOPPED:
                # stop() closed _pair_sock and _out_sockets. recreate them
                # here, otherwise the loop spins forever calling recv() on
                # a dead socket.
                addr = str(self.settings.engine_addr)
                self._pair_sock = self._engine_socket_factory.create(
                    addr, self.log, tls_config=self.settings.tls_input
                )
                self._pair_sock.recv_timeout = self.settings.engine_recv_timeout
                self._out_sockets = []
                self._setup_output_sockets()

            self._state = EngineState.RUNNING
            thread = threading.Thread(
                target=self._run_loop,
                name="EngineLoop",
                daemon=True
            )
            try:
                thread.start()
            except Exception as e:
                # Thread creation can fail under OS resource exhaustion. Roll
                # back so start() can retry, instead of leaving _state at
                # RUNNING with no thread for stop() to join.
                self._state = previous_state
                raise EngineException(f"Failed to start engine thread: {e}") from e

            self._thread = thread
            return "engine started"

    def _run_loop(self) -> None:
        labels = {
            "component_type": getattr(self, "component_type", "core"),
            "component_id": self.settings.component_id
        }

        try:
            self._run_loop_body(labels)
        finally:
            self._handle_unexpected_loop_exit()

    def _handle_unexpected_loop_exit(self) -> None:
        """Self-heal _state if the loop thread died without stop() being
        called.

        Without this, an uncaught exception in the loop would leave
        _state stuck at RUNNING with a dead thread — start() would
        refuse to restart, and status would keep reporting healthy.

        _state must be checked *before* acquiring _lifecycle_lock: a
        normal stop() holds this lock while blocked in
        self._thread.join() waiting for this thread, so acquiring it
        unconditionally here would deadlock. If _state is already non-
        RUNNING, a stop() call already owns the shutdown — nothing to
        do.

        The acquire below is bounded (not indefinite) for the rare case
        where a stop() call starts concurrently, wins the lock, and
        joins us while we're still waiting on it.
        """
        if self._state != EngineState.RUNNING:
            return

        if not self._lifecycle_lock.acquire(timeout=0.5):
            # A concurrent stop() is holding the lock and already
            # responsible for shutting things down — let this thread finish
            # so that stop()'s join() can succeed.
            self.log.warning(
                "Engine loop thread exiting unexpectedly, but a concurrent "
                "stop() already holds the lifecycle lock; leaving it to finish shutdown"
            )
            return
        try:
            # Re-check: a concurrent stop() may have won the race and
            # already be blocked joining us since the check above.
            if self._state != EngineState.RUNNING:
                return
            self.log.critical(
                "Engine loop thread exiting unexpectedly; marking engine stopped"
            )
            self._state = EngineState.STOPPED
            try:
                self._pair_sock.close()
            except Exception as e:
                self.log.error("Failed to close engine socket after unexpected exit: %s", e)
            for i, sock in enumerate(self._out_sockets):
                try:
                    sock.close()
                except Exception as e:
                    self.log.error("Failed to close output socket %d after unexpected exit: %s", i, e)
        finally:
            self._lifecycle_lock.release()

    def _run_loop_body(self, labels: Dict[str, Any]) -> None:
        while self._state == EngineState.RUNNING:

            # recv phase
            try:
                raw = self._pair_sock.recv()
                if raw is None or len(raw) == 0:
                    self.log.debug("Engine: Received empty message, skipping")
                    continue

                # TRACK read bytes and lines
                data_read_bytes_total.labels(**labels).inc(len(raw))
                data_read_lines_total.labels(**labels).inc(raw.count(b'\n') or 1)

                self.log.debug(f"Engine: Received {len(raw)} bytes from socket")
            except pynng.Timeout:
                continue  # Timeout occurred, check running flag and continue
            except pynng.NNGException as e:
                if self._state != EngineState.RUNNING:
                    break
                self.log.exception("Engine error during receive: %s", e)
                continue
            except Exception as e:
                self.log.exception("Unexpected engine error during receive: %s", e)
                continue

            # process phase
            try:
                self.log.debug("Engine: Calling processor.process()...")
                out = self.processor.process(raw)
                self.log.debug(f"Engine: Processor returned: {out!r}")
            except Exception as e:
                processing_errors_total.labels(**labels).inc()
                self.log.exception("Engine error during process: %s", e)
                continue

            if out is None:
                self.log.debug("Engine: Processor returned None, skipping send")
                continue

            # send phase
            if self._out_sockets:
                # Multi-destination mode: send to all configured outputs
                if self._send_to_outputs(out):
                    data_written_bytes_total.labels(**labels).inc(len(out))
                    data_written_lines_total.labels(**labels).inc(out.count(b'\n') or 1)
            else:
                # Backwards-compatible mode: no outputs configured, reply on PAIR socket
                try:
                    self.log.debug(
                        "Engine: No output sockets configured, "
                        "sending reply back via engine socket"
                    )
                    self._pair_sock.send(out)
                    # TRACK written bytes and lines (Fallback mode)
                    data_written_bytes_total.labels(**labels).inc(len(out))
                    data_written_lines_total.labels(**labels).inc(out.count(b'\n') or 1)
                    self.log.debug("Engine: Reply sent on engine socket")
                except pynng.NNGException as e:
                    data_dropped_bytes_total.labels(**labels).inc(len(out))
                    data_dropped_lines_total.labels(**labels).inc(out.count(b'\n') or 1)
                    self.log.error("Engine error sending reply on engine socket: %s", e)
                    continue
                except Exception as e:
                    data_dropped_bytes_total.labels(**labels).inc(len(out))
                    data_dropped_lines_total.labels(**labels).inc(out.count(b'\n') or 1)
                    self.log.exception("Unexpected engine error sending reply on engine socket: %s", e)
                    continue

    def _send_to_outputs(self, data: bytes) -> bool:
        """Send processed data to all configured output destinations.

        Returns True if at least one send succeeded.
        """
        labels = {
            "component_type": getattr(self, "component_type", "core"),
            "component_id": self.settings.component_id
        }
        if not self._out_sockets:
            self.log.debug("Engine: No output sockets configured, skipping send")
            return False

        any_sent = False
        for i, sock in enumerate(self._out_sockets):
            for attempt in range(self.settings.engine_retry_count):
                try:
                    self.log.debug(f"Engine: Sending {len(data)} bytes to output socket {i}")
                    # Non-blocking send is preferred to avoid stalling the engine loop
                    # Pair0 with block=False will raise TryAgain if the peer is disconnected
                    sock.send(data, block=False)
                    any_sent = True
                    self.log.debug(f"Engine: Send completed to output socket {i}")
                    break
                except pynng.TryAgain:
                    time.sleep(0.01)
                    if attempt == self.settings.engine_retry_count - 1:
                        data_dropped_bytes_total.labels(**labels).inc(len(data))
                        data_dropped_lines_total.labels(**labels).inc(data.count(b'\n') or 1)
                        self.log.warning(
                            f"Engine: Output socket {i} not ready or disconnected, dropping message")
                except pynng.NNGException as e:
                    data_dropped_bytes_total.labels(**labels).inc(len(data))
                    data_dropped_lines_total.labels(**labels).inc(data.count(b'\n') or 1)
                    self.log.error(f"Engine error sending to output socket {i}: {e}")
                    break
                except Exception as e:
                    data_dropped_bytes_total.labels(**labels).inc(len(data))
                    data_dropped_lines_total.labels(**labels).inc(data.count(b'\n') or 1)
                    self.log.exception(f"Unexpected engine error sending to output socket {i}: {e}")
                    break
        return any_sent

    def stop(self) -> str:
        """Stop the engine loop and clean up resources.

        Returns:
            "engine stopped" if this call actually stopped it, or
            "engine already stopped" if it was a no-op. Callers should
            branch on this (rather than re-checking state themselves
            outside the lock) to know whether they were the one that did it.
        Raises:
            EngineException: If stopping fails for any reason
        """
        with self._lifecycle_lock:
            if self._state not in (EngineState.RUNNING, EngineState.STOPPING):
                if self.log:
                    self.log.debug("Engine is not running, skipping stop")
                return "engine already stopped"

            # Signal _run_loop to exit *before* attempting to join it — this must
            # happen immediately, independent of whether the join below confirms
            # the thread actually died within the timeout.
            self._state = EngineState.STOPPING

            if self._thread is None:
                raise EngineException("Engine state is STOPPING but no thread was started")

            # WAIT for engine loop to exit recv()
            self._thread.join(timeout=2.0)

            if self._thread.is_alive():
                # Leave _state as STOPPING: the loop's exit can't be confirmed, so a
                # later start() must not spin up a second thread on top of this one.
                # A later stop() call will retry the join.
                raise EngineException("Engine thread failed to stop cleanly")

            # The loop is confirmed dead, so the engine is stopped regardless of
            # whether the socket cleanup below succeeds.
            self._state = EngineState.STOPPED

            # Close every socket regardless of individual failures, then report
            # them together instead of raising on the first one and leaking the rest.
            close_failures: List[pynng.NNGException] = []

            try:
                self._pair_sock.close()
            except pynng.NNGException as e:
                close_failures.append(e)

            for i, sock in enumerate(self._out_sockets):
                try:
                    sock.close()
                    self.log.debug(f"Closed output socket {i}")
                except pynng.NNGException as e:
                    self.log.error(f"Failed to close output socket {i}: {e}")
                    close_failures.append(e)

            if close_failures:
                raise EngineException(
                    f"Failed to close {len(close_failures)} socket(s) during stop: "
                    + "; ".join(str(e) for e in close_failures)
                ) from close_failures[0]

            if self.log:
                self.log.debug("Engine stopped successfully")

            return "engine stopped"
