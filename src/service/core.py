from __future__ import annotations
import logging
import sys
from abc import ABC
from pathlib import Path
import threading
import typing
import json
from typing import Optional, Type

from service.features.parameter_manager import ParameterManager
from service.features.parameters import BaseParameters
from service.settings import ServiceSettings
from service.features.manager import Manager, manager_command
from service.features.engine import Engine

from library.processor import BaseProcessor


class ServiceProcessorAdapter(BaseProcessor):
    """Adapter class to use a Service's process method as a BaseProcessor."""
    def __init__(self, service):
        self.service = service

    def process(self, raw_message: bytes) -> bytes | None:
        return self.service.process(raw_message)


class Service(Manager, Engine, ABC):
    """Abstract base for every DetectMate service/component."""
    # hard-code component type as class variable, overwrite in subclasses
    component_type: str = "core"

    def __init__(self, settings: ServiceSettings = ServiceSettings()):
        # Prepare attributes & logger first
        self.settings: ServiceSettings = settings
        self.component_id: str = settings.component_id  # type: ignore[assignment]
        self._stop_event: threading.Event = threading.Event()
        self.log: logging.Logger = self._build_logger()

        # Create processor instance
        self.processor = self.create_processor()

        # now init Manager (opens REP socket & discovers commands)
        Manager.__init__(self, settings=settings, logger=self.log)

        # then init Engine with the processor (opens PAIR socket, may autostart)
        Engine.__init__(self, settings=settings, processor=self.processor, logger=self.log)

        self.param_manager: Optional[ParameterManager] = None
        if hasattr(settings, 'parameter_file') and settings.parameter_file:
            self.log.debug(f"Initializing ParameterManager with file: {settings.parameter_file}")
            self.param_manager = ParameterManager(
                str(settings.parameter_file),
                self.get_parameters_schema()
            )
            # Check if parameters were loaded successfully
            params = self.param_manager.get()
            self.log.debug(f"Initial parameters: {params}")

        self.log.debug("%s[%s] created", self.component_type, self.component_id)

    def get_parameters_schema(self) -> Type[BaseParameters]:
        """Return the parameters schema for this service.

        Override in subclasses.
        """
        return BaseParameters

    def create_processor(self) -> BaseProcessor:
        """Create and return a processor instance for this service.

        Override this method in subclasses to provide custom processors.
        """
        return ServiceProcessorAdapter(self)

    # public API
    def setup_io(self) -> None:
        """Hook for loading models, etc."""
        self.log.info("setup_io: ready to process messages")

    def run(self) -> None:
        """Kick off the engine, then await stop.

        The Manager's command thread is already live, so external
        clients can pause/resume/stop at any time.
        """
        if not getattr(self, '_running', False):
            self.log.info(self.start())  # start engine loop
        self._stop_event.wait()
        if getattr(self, '_running', False):  # don't call stop() again if it was already called by a command
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
        if self._stop_event.is_set():
            return "already stopping or stopped"
        self.log.info("Stop command received")
        self._stop_event.set()
        try:
            Engine.stop(self)
            self.log.info("Engine stopped successfully")
            return "engine stopped"
        except RuntimeError as e:
            self.log.error("Failed to stop engine: %s", e)
            return f"error: failed to stop engine - {e}"

    @manager_command()
    def status(self, cmd: str | None = None) -> str:
        """Comprehensive status report including settings and parameters."""
        if self.param_manager:
            params = self.param_manager.get()
            print(f"DEBUG: Parameters from manager: {params}")

        running = getattr(self, "_running", False)
        paused = getattr(self, "_paused", None)
        is_paused = (paused.is_set() if paused is not None else False)

        # Debug logging
        self.log.debug(f"Parameter manager exists: {self.param_manager is not None}")
        if self.param_manager:
            params = self.param_manager.get()
            self.log.debug(f"Parameters: {params}")
            self.log.debug(f"Parameter file: {self.settings.parameter_file}")

        # Convert Path objects to strings for JSON serialization
        settings_dict = self.settings.model_dump()
        for key, value in settings_dict.items():
            if isinstance(value, Path):
                settings_dict[key] = str(value)

        # Handle parameters
        if self.param_manager:
            params = self.param_manager.get()
            if params is not None:
                if hasattr(params, 'model_dump'):
                    params_dict = params.model_dump()
                    # Convert any Path objects in parameters to strings
                    for key, value in params_dict.items():
                        if isinstance(value, Path):
                            params_dict[key] = str(value)
                else:
                    params_dict = params
            else:
                params_dict = {}
                self.log.warning("ParameterManager.get() returned None")
        else:
            params_dict = {}
            self.log.warning("No ParameterManager initialized")

        status_info = {
            "status": {
                "component_type": self.component_type,
                "component_id": self.component_id,
                "running": running,
                "paused": is_paused
            },
            "settings": settings_dict,
            "parameters": params_dict
        }

        return json.dumps(status_info, indent=2)

    @manager_command()
    def reconfigure(self, cmd: str | None = None) -> str:
        """Reconfigure service parameters dynamically."""
        if not self.param_manager:
            return "reconfigure: no parameter manager configured"

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

        try:
            self.param_manager.update(data)
            self.log.info("Reconfigured with: %s", data)
            return "reconfigure: ok"
        except Exception as e:
            return f"reconfigure: error - {e}"

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
        if not self._stop_event.is_set():  # only stop if not already stopped
            self.stop()  # shut down gracefully
        self._close_manager()  # close REP socket & thread
        return False  # propagate exceptions
