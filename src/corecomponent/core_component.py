from __future__ import annotations
import logging
import sys
from abc import ABC
from pathlib import Path
import time
import typing

from corecomponent.settings import CoreComponentSettings
from corecomponent.features.manager import Manager
from corecomponent.features.engine import Engine


class CoreComponent(Manager, Engine, ABC):
    """Abstract base for every DetectMate component."""
    # hard-code component type as class variable, overwrite in subclasses
    component_type: str = "core"

    def __init__(self, settings: CoreComponentSettings | None = None):
        settings = settings or CoreComponentSettings()

        # Initialize Manager first (opens REP socket & thread)
        Manager.__init__(self, settings=settings)

        # Then initialize Engine (opens Pub/Sub sockets & thread)
        Engine.__init__(self, settings=settings)

        self.settings = settings
        self.component_id = settings.component_id
        self.log = self._build_logger()
        self._stop_flag = False

        # register control commands
        self.register_command("start", lambda _: self.start())
        self.register_command("stop", lambda _: self.stop())
        self.register_command("pause", lambda _: self.pause())
        self.register_command("resume", lambda _: self.resume())
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

    def stop(self) -> str:
        """Stop both the engine loop and mark the component to exit."""
        self._stop_flag = True
        self.log.info("Stop flag set for %s[%s]", self.component_type, self.component_id)
        return Engine.stop(self)  # calls Engine.stop()

    # ensure pause/resume are logged
    def pause(self) -> str:
        msg = Engine.pause(self)
        self.log.info(msg)
        return msg

    def resume(self) -> str:
        msg = Engine.resume(self)
        self.log.info(msg)
        return msg

    # helpers
    def _build_logger(self) -> logging.Logger:
        Path(self.settings.log_dir).mkdir(parents=True, exist_ok=True)
        name = f"{self.component_type}.{self.component_id}"
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, self.settings.log_level.upper(), logging.INFO))

        fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
        if self.settings.log_to_console:
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(fmt)
            logger.addHandler(sh)
        if self.settings.log_to_file:
            fh = logging.FileHandler(
                Path(self.settings.log_dir) /
                f"{self.component_type}_{self.component_id}.log"
            )
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        return logger

    # context-manager sugar
    def __enter__(self) -> "CoreComponent":
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
