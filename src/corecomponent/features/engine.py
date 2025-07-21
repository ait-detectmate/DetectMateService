import threading
import time
import pynng
from abc import ABC, abstractmethod


class Engine(ABC):
    """Engine drives a background thread that reads raw messages over PAIR0,
    calls 'self.process()', and sends outputs back over the same socket."""

    def __init__(self, settings):
        self.settings = settings

        # control flags
        self._running = False
        self._paused = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop, name="EngineLoop", daemon=True
        )

        # set up a PAIR0 socket on its own channel
        self._pair_sock = pynng.Pair0()
        addr = str(settings.engine_addr)
        if addr.startswith("ipc://"):
            from pathlib import Path
            Path(addr.replace("ipc://", "")).unlink(missing_ok=True)
        self._pair_sock.listen(addr)

        # autostart if enabled
        if getattr(settings, "engine_autostart", True):
            self.start()

    def start(self) -> str:
        if not self._running:
            self._running = True
            self._thread.start()
            return "engine started"
        return "engine already running"

    def _run_loop(self) -> None:
        while self._running:
            if self._paused.is_set():
                time.sleep(0.1)
                continue

            try:
                raw = self._pair_sock.recv()
                out = self.process(raw)
                if out is not None:
                    self._pair_sock.send(out)
            except Exception:
                # TODO: we might want to log this
                continue

    def stop(self) -> str:
        if self._running:
            self._running = False
            self._thread.join(timeout=1.0)
            return "engine stopped"
        return "engine not running"

    def pause(self) -> str:
        self._paused.set()
        return "engine paused"

    def resume(self) -> str:
        self._paused.clear()
        return "engine resumed"

    @abstractmethod
    def process(self, raw_message: bytes) -> bytes | None:
        """Decode raw_message, run parser(s)/detector(s), and return something
        to publish (or None to skip)."""
        pass
