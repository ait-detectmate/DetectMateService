"""Request/Reply command-manager for DetectMate components.

The Manager class starts a background thread with a REP socket that
waits for simple string commands. It is meant to be inherited
by CoreComponent, so every concrete component automatically exposes
the same management interface.

Default commands
----------------
ping   -> pong
stop   -> sets the component's stop flag and replies "stopping"
<else> -> "unknown command"
TODO: implement actual commands
"""
from __future__ import annotations
from typing import Optional, Callable
import threading
import pynng

from corecomponent.settings import CoreComponentSettings


class Manager:
    """Mixin that starts a REP socket in the background and serves commands."""

    _default_addr: str = "ipc:///tmp/detectmate.cmd.ipc"

    def __init__(
        self,
        *_args,
        settings: Optional[CoreComponentSettings] = None,
        **_kwargs,
    ):
        self._stop_flag: bool = False
        self.settings: CoreComponentSettings = (
            settings if settings is not None else CoreComponentSettings()
        )

        # bind REP socket
        self._rep_sock = pynng.Rep0()
        listen_addr = str(self.settings.manager_addr or self._default_addr)

        if listen_addr.startswith("ipc://"):
            from pathlib import Path
            Path(listen_addr.replace("ipc://", "")).unlink(missing_ok=True)

        self._rep_sock.listen(listen_addr)
        print(f"[manager] listening on {listen_addr}")

        # background thread
        self._thread = threading.Thread(
            target=self._command_loop, name="ManagerCmdLoop", daemon=True
        )
        self._thread.start()

        # custom command handlers
        self._handlers: dict[str, Callable[[str], str]] = {}

    # public helper
    def register_command(self, name: str, handler: Callable[[str], str]) -> None:
        self._handlers[name.lower()] = handler

    # internal machinery
    def _command_loop(self) -> None:
        while not self._stop_flag:
            try:
                raw: bytes = self._rep_sock.recv()  # blocks
                cmd = raw.decode("utf-8", errors="ignore").strip()
            except pynng.NNGException:
                break  # socket closed elsewhere

            reply: str = self._handle_cmd(cmd)
            try:
                self._rep_sock.send(reply.encode())
            except pynng.NNGException:
                break

        # graceful shutdown
        try:
            self._rep_sock.close()
        except pynng.NNGException:
            pass

    def _handle_cmd(self, cmd: str) -> str:
        lcmd = cmd.lower()

        if lcmd in self._handlers:
            return self._handlers[lcmd](cmd)

        if lcmd == "ping":
            return "pong"
        if lcmd == "stop":
            # Reply immediately, stop asynchronously to avoid blocking the REP send.
            def _do_stop():
                stop_fn = getattr(self, "stop", None)
                if callable(stop_fn):
                    stop_fn()
                else:
                    self._stop_flag = True
            threading.Thread(target=_do_stop, daemon=True).start()
            return "stopping"

        if lcmd == "pause":
            pause_fn = getattr(self, "pause", None)
            return pause_fn() if callable(pause_fn) else "no pause()"
        if lcmd == "resume":
            resume_fn = getattr(self, "resume", None)
            return resume_fn() if callable(resume_fn) else "no resume()"

        return f"unknown command: {cmd}"

    # tear-down helper
    def _close_manager(self) -> None:
        """Called by CoreComponent.__exit__."""
        self._stop_flag = True
        try:
            # Just close; closing from another thread unblocks .recv() in pynng.
            self._rep_sock.close()
        except pynng.NNGException:
            pass

        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
