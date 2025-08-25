from __future__ import annotations
import logging
import sys
from abc import ABC
from pathlib import Path
import time
import typing
import json

from service.settings import ServiceSettings
from service.features.manager import Manager, manager_command
from service.features.engine import Engine


class Service(Manager, Engine, ABC):
    """Abstract base for every DetectMate service/component."""
    # hard-code component type as class variable, overwrite in subclasses
    component_type: str = "core"

    def __init__(self, settings: ServiceSettings = ServiceSettings()):
        # Prepare attributes & logger first
        self.settings = settings
        self.component_id = settings.component_id
        self._stop_flag = False
        self.log = self._build_logger()

        # now init Manager (opens REP socket & discovers commands)
        Manager.__init__(self, settings=settings)

        # then init Engine (opens PAIR socket, may autostart)
        Engine.__init__(self, settings=settings)

        self.log.debug("%s[%s] created", self.component_type, self.component_id)

    # public API
    def setup_io(self) -> None:
        """Hook for loading models, etc."""
        self.log.info("setup_io: ready to process messages")

    def run(self) -> None:
        """Kick off the engine, then await stop.

        The Manager's command thread is already live, so external
        clients can pause/resume/stop at any time.
        """
        self.log.info(self.start())  # start engine loop
        while not self._stop_flag:
            time.sleep(0.5)
        self.log.info(self.stop())  # ensure engine thread is joined

    @manager_command()
    def start(self) -> str:
        """Expose engine start as a command."""
        msg = Engine.start(self)
        self.log.info(msg)
        return msg

    @manager_command()
    def stop(self) -> str:
        """Stop both the engine loop and mark the component to exit."""
        self._stop_flag = True
        self.log.info("Stop flag set for %s[%s]", self.component_type, self.component_id)
        return Engine.stop(self)  # calls Engine.stop()

    @manager_command()
    def pause(self) -> str:
        msg = Engine.pause(self)
        self.log.info(msg)
        return msg

    @manager_command()
    def resume(self) -> str:
        msg = Engine.resume(self)
        self.log.info(msg)
        return msg

    @manager_command()
    def status(self) -> str:
        """Basic status report for this component."""
        running = getattr(self, "_running", False)
        paused = getattr(self, "_paused", None)
        is_paused = (paused.is_set() if paused is not None else False)
        return f"{self.component_type}[{self.component_id}] " + (
            ("running (paused)" if is_paused else "running") if running else "stopped"
        )

    @manager_command()
    def reconfigure(self, cmd: str | None = None) -> str:
        """Accepts 'reconfigure {json}' to demonstrate dynamic config updates.

        This is a placeholder; TODO: adapt later to real configuration
        """
        payload = ""
        if cmd:
            _, _, tail = cmd.partition(" ")
            payload = tail.strip()
        if not payload:
            return "reconfigure: no-op (no payload)"

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return "reconfigure: invalid JSON"

        # Example: record the last reconfigure payload
        setattr(self, "_last_reconfigure", data)
        self.log.info("Reconfigured with: %s", data)
        return "reconfigure: ok"

    # helpers
    def _build_logger(self) -> logging.Logger:
        Path(self.settings.log_dir).mkdir(parents=True, exist_ok=True)
        name = f"{self.component_type}.{self.component_id}"
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, self.settings.log_level.upper(), logging.INFO))
        logger.propagate = False  # don't bubble to root logger -> avoid duplicate lines

        # Avoid duplicate handlers if this gets called again with same name
        if logger.handlers:
            return logger

        fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")

        # Point the console handler at the real, uncaptured stream & avoid re-adding handlers repeatedly
        if self.settings.log_to_console:
            safe_stdout = getattr(sys, "__stdout__", sys.stdout)
            sh = logging.StreamHandler(safe_stdout)
            sh.setFormatter(fmt)
            logger.addHandler(sh)
        if self.settings.log_to_file:
            fh = logging.FileHandler(
                Path(self.settings.log_dir) / f"{self.component_type}_{self.component_id}.log",
                encoding="utf-8",
                delay=True,  # don't open until first write
            )
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        return logger

    # context-manager sugar
    def __enter__(self) -> "Service":
        self.setup_io()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> typing.Literal[False]:
        self.stop()  # shut down gracefully
        self._close_manager()   # close REP socket & thread

        # close log handlers
        for h in list(self.log.handlers):
            h.close()
            self.log.removeHandler(h)
        self.log.info("Bye")
        return False  # propagate exceptions
