"""Request/Reply command-manager for DetectMate services.

The Manager class starts a background thread with a REP socket that
waits for simple string commands. It is meant to be inherited
by Service, so every concrete component automatically exposes
the same management interface.

Default commands
----------------
ping   -> pong
<decorated commands> -> dynamically dispatched on self
<else> -> "unknown command"
"""
from __future__ import annotations
from typing import Optional, Callable
import threading
import pynng
import time
import logging
from service.settings import ServiceSettings
from service.features.manager_socket import ManagerSocketFactory, NngRepSocketFactory


# Decorator to mark callable commands on a component
def manager_command(name: str | None = None):
    """Decorator to tag methods as manager-exposed commands.

    Usage:
        @manager_command()          -> command name is the method name (lowercase)
        @manager_command("status")  -> explicit command name
    """
    def _wrap(fn):
        setattr(fn, "_manager_command", True)
        setattr(fn, "_manager_command_name", (name or fn.__name__).lower())
        return fn
    return _wrap


class Manager:
    """Mixin that starts a REP socket in the background and serves commands."""

    def __init__(
            self,
            *_args,
            settings: Optional[ServiceSettings] = None,
            socket_factory: Optional[ManagerSocketFactory] = None,
            logger: Optional[logging.Logger] = None,
            **_kwargs
    ):
        self._stop_event = threading.Event()
        self.settings: ServiceSettings = settings if settings is not None else ServiceSettings()
        self.log = logger or logging.getLogger(__name__)

        # Use socket factory abstraction
        self._manager_socket_factory: ManagerSocketFactory = (
            socket_factory if socket_factory is not None else NngRepSocketFactory()
        )

        listen_addr = str(self.settings.manager_addr)

        # Create socket using factory
        self._rep_sock = self._manager_socket_factory.create(listen_addr, self.log)
        self._rep_sock.recv_timeout = self.settings.manager_recv_timeout

        # background thread
        self._thread = threading.Thread(
            target=self._command_loop, name="ManagerCmdLoop", daemon=True
        )
        self._thread.start()

        # custom command handlers (explicit registrations)
        self._handlers: dict[str, Callable[[str], str]] = {}

        # discover @manager_command-decorated methods once
        self._decorated_handlers: dict[str, Callable[..., str]] = {}
        self._discover_decorated_commands()

    # discover decorated command methods on the instance/class
    def _discover_decorated_commands(self) -> None:
        for attr_name in dir(self):
            if attr_name.startswith("_"):
                continue
            attr = getattr(self, attr_name)
            # If it's a bound method, the function is on __func__
            func = getattr(attr, "__func__", None)
            if func is None:
                continue
            if getattr(func, "_manager_command", False):
                cmd_name = getattr(func, "_manager_command_name", attr_name).lower()
                # store the bound method; call directly later
                self._decorated_handlers[cmd_name] = attr

    # internal machinery
    def _command_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                raw: bytes = self._rep_sock.recv()  # blocks with timeout
                cmd = raw.decode("utf-8", errors="ignore").strip()
                if hasattr(self, 'log'):
                    self.log.debug(f"Received command: {cmd}")
            except pynng.Timeout:
                continue  # Timeout occurred, check stop event and continue
            except pynng.NNGException:
                break  # socket closed elsewhere

            # check if it's already stopping to prevent duplicate processing
            if hasattr(self, '_stop_event') and self._stop_event.is_set() and cmd.lower() == "stop":
                if hasattr(self, 'log'):
                    self.log.debug("Ignoring stop command - already stopping")
                continue

            try:
                reply: str = self._handle_cmd(cmd)
            except Exception as e:
                self.log.error(f"Unexpected error handling command '{cmd}': {e}")
                reply = "error: internal error processing command"

            try:
                self._rep_sock.send(reply.encode())
                if hasattr(self, 'log'):
                    self.log.debug(f"Sent response: {reply}")
            except pynng.NNGException:
                break

    def _handle_cmd(self, cmd: str) -> str:
        """Route a command string to the right handler.

        Priority:
          1. @manager_command-decorated methods on self
          2. Built-in 'ping'
          3. Unknown
        """
        if hasattr(self, 'log'):
            self.log.info(f"Processing command: {cmd}")

        verb = cmd.split(" ", 1)[0].lower()  # split: verb [args...]

        # 1. decorator-based dynamic dispatch
        fn = self._decorated_handlers.get(verb)
        if fn is not None:
            try:
                # Try to pass cmd; if the signature is zero-arg, call without
                try:
                    reply = fn(cmd)
                except TypeError:
                    reply = fn()
                if hasattr(self, 'log'):
                    self.log.debug(f"Executed command '{verb}': {reply}")
                return reply
            except Exception as e:
                if hasattr(self, 'log'):
                    self.log.error(f"Error executing command '{verb}': {e}")
                return f"error: {e}"

        # 2. built-in ping
        if verb == "ping":
            return "pong"

        # 3. unknown
        return f"unknown command: {cmd}"

    # tear-down helper
    def _close_manager(self) -> None:
        """Called by Service.__exit__."""
        self._stop_event.set()
        time.sleep(0.05)  # give the manager thread a moment to finish any current command processing
        try:
            # Just close; closing from another thread unblocks .recv() in pynng.
            self._rep_sock.close()
        except pynng.NNGException:
            pass

        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
