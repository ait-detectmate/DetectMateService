from __future__ import annotations
import logging
import sys
from abc import ABC
from pathlib import Path
import threading
import json
from typing import Optional, Type, Literal, Dict, Any, cast
from types import TracebackType

from service.features.config_manager import ConfigManager
from service.settings import ServiceSettings
from service.features.manager import Manager, manager_command
from service.features.engine import Engine, EngineException
from service.features.component_loader import ComponentLoader
from service.features.config_loader import ConfigClassLoader

from library.processor import BaseProcessor
from detectmatelibrary.common.core import CoreComponent, CoreConfig


class ServiceProcessorAdapter(BaseProcessor):
    """Adapter class to use a Service's process method as a BaseProcessor."""
    def __init__(self, service: Service) -> None:
        self.service = service

    def __call__(self, raw_message: bytes) -> bytes | None:
        return self.service.process(raw_message)


class LibraryComponentProcessor(BaseProcessor):
    """Adapter to use DetectMate library components as BaseProcessor."""

    def __init__(self, component: CoreComponent) -> None:
        self.component = component

    def __call__(self, raw_message: bytes) -> bytes | None | Any:
        """Process message using the library component."""
        try:
            result = self.component.process(raw_message)
            return result
        except Exception as e:
            logging.getLogger(__name__).error(f"Component processing error: {e}")
            return None


class Service(Manager, Engine, ABC):
    """Abstract base for every DetectMate service/component."""

    def __init__(
            self,
            settings: ServiceSettings = ServiceSettings(),
            component_config: Dict[str, Any] | None = None
    ):
        # Prepare attributes & logger first
        self.settings: ServiceSettings = settings
        self.component_id: str = settings.component_id  # type: ignore[assignment]
        self._stop_event: threading.Event = threading.Event()

        # set component_type
        if hasattr(self, 'component_type'):  # prioritize class attribute over settings
            pass  # already set by the child class
        elif (hasattr(settings, 'component_type') and
                settings.component_type != "core" and
                not settings.component_type.startswith("core")):
            self.component_type = settings.component_type  # this is a library component, use its type
        else:
            self.component_type = "core"  # default to core

        # Now build the logger (which uses component_type)
        self.log: logging.Logger = self._build_logger()

        # Initialize config manager before loading the library component
        # so we can pass the loaded configs to the component
        self.config_manager: Optional[ConfigManager] = None
        loaded_config_dict: Dict[str, Any] = {}

        if hasattr(settings, 'config_file') and settings.config_file:
            self.log.debug(f"Initializing ConfigManager with file: {settings.config_file}")
            self.config_manager = ConfigManager(
                str(settings.config_file),
                self.get_config_schema(),
                logger=self.log
            )
            # Get the loaded configs to pass to library component
            configs = self.config_manager.get()
            self.log.debug(f"Initial configs: {configs}")
            if configs is not None:
                if hasattr(configs, 'model_dump'):
                    loaded_config_dict = configs.model_dump()
                elif isinstance(configs, dict):
                    loaded_config_dict = configs

        # Load library component if component_type is specified and not core
        self.library_component: Optional[CoreComponent] = None
        if (hasattr(settings, 'component_type') and
                settings.component_type != "core" and
                not settings.component_type.startswith("core")):

            try:
                self.log.info(f"Loading library component: {settings.component_type}")
                # use loaded configs from config_manager, fall back to component_config
                config_to_use = loaded_config_dict or component_config or {}
                self.library_component = ComponentLoader.load_component(
                    settings.component_type,
                    config_to_use
                )
                self.log.info(f"Successfully loaded component: {self.library_component}")
            except Exception as e:
                self.log.error(f"Failed to load component {settings.component_type}: {e}")
                raise

        # Create processor instance
        self.processor = self.create_processor()

        # now init Manager (opens REP socket & discovers commands)
        Manager.__init__(self, settings=settings, logger=self.log)

        # then init Engine with the processor (opens PAIR socket, may autostart)
        Engine.__init__(self, settings=settings, processor=self.processor, logger=self.log)

        self.log.debug("%s[%s] created", self.component_type, self.component_id)

    def get_config_schema(self) -> Type[CoreConfig]:
        """Return the configuration schema for this service.

        If component_config_class is specified in settings, load and
        return it. Otherwise return the default CoreConfig.
        """
        if hasattr(self.settings, 'component_config_class') and self.settings.component_config_class:
            try:
                self.log.debug(f"Loading config class: {self.settings.component_config_class}")
                config_class = ConfigClassLoader.load_config_class(self.settings.component_config_class)
                self.log.debug(f"Successfully loaded config class: {config_class}")
                return config_class
            except Exception as e:
                self.log.error(f"Failed to load config class {self.settings.component_config_class}: {e}")
                raise
        return cast(Type[CoreConfig], CoreConfig)  # help mypy

    def process(self, raw_message: bytes) -> bytes | None | Any:
        """Process the raw message using the library component or default
        implementation."""
        if self.library_component:
            # use the library component's process method
            return self.library_component.process(raw_message)
        else:
            # default implementation for core service
            return raw_message

    def create_processor(self) -> BaseProcessor:
        """Create processor based on available components."""
        if self.library_component:
            return LibraryComponentProcessor(self.library_component)
        else:
            # fall back to service's own process method
            # TODO: do we need this?
            return ServiceProcessorAdapter(self)

    # public API
    def setup_io(self) -> None:
        """Hook for loading models, etc."""
        self.log.info("setup_io: ready to process messages")

    def run(self) -> None:
        """Kick off the engine, then await stop."""
        if not getattr(self, '_running', False):
            self.log.info(self.start())  # start engine loop
        else:
            self.log.debug("Engine already running")
        self._stop_event.wait()
        if getattr(self, '_running', False):  # don't call stop() again if it was already called by a command
            self.log.info(self.stop())  # ensure engine thread is joined
        else:
            self.log.debug("Engine already stopped")

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
        except EngineException as e:
            self.log.error("Failed to stop engine: %s", e)
            return f"error: failed to stop engine - {e}"

    @manager_command()
    def status(self, cmd: str | None = None) -> str:
        """Comprehensive status report including settings and configs."""
        if self.config_manager:
            configs = self.config_manager.get()
            print(f"DEBUG: Configs from manager: {configs}")

        running = getattr(self, "_running", False)

        # Debug logging
        self.log.debug(f"Config manager exists: {self.config_manager is not None}")
        if self.config_manager:
            configs = self.config_manager.get()
            self.log.debug(f"Configurations: {configs}")
            self.log.debug(f"Config file: {self.settings.config_file}")

        # Create status report
        status_info = self._create_status_report(running)
        return json.dumps(status_info, indent=2)

    @manager_command()
    def reconfigure(self, cmd: str | None = None) -> str:
        """Reconfigure service configurations dynamically."""
        if not self.config_manager:
            return "reconfigure: no config manager configured"

        payload = ""
        persist = False

        if cmd:
            # Parse the command: "reconfigure [persist] <json>"
            parts = cmd.split(maxsplit=2)  # Split into at most 3 parts
            if len(parts) >= 2:
                # Check if the second part is "persist"
                if parts[1].lower() == "persist":
                    persist = True
                    # Use the third part as payload if it exists
                    payload = parts[2] if len(parts) > 2 else ""
                else:
                    # Use the rest of the command as payload
                    payload = cmd.split(maxsplit=1)[1] if len(parts) > 1 else ""

        if not payload:
            return "reconfigure: no-op (no payload)"

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return "reconfigure: invalid JSON"

        try:
            self.config_manager.update(data)
            if persist:
                self.config_manager.save()
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

    def _create_status_report(self, running: bool) -> Dict[str, Any]:
        """Create a status report dictionary with settings and configs."""
        # Convert Path objects in settings to strings for JSON serialization
        settings_dict = self.settings.model_dump()
        for key, value in settings_dict.items():
            if isinstance(value, Path):
                settings_dict[key] = str(value)

        # Handle configs
        if self.config_manager:
            configs = self.config_manager.get()
            if configs is not None:
                if hasattr(configs, 'model_dump'):
                    config_dict = configs.model_dump()
                    # Convert any Path objects in configs to strings
                    for key, value in config_dict.items():
                        if isinstance(value, Path):
                            config_dict[key] = str(value)
                else:
                    config_dict = configs
            else:
                config_dict = {}
                self.log.warning("ConfigManager.get() returned None")
        else:
            config_dict = {}
            self.log.warning("No ConfigManager initialized")

        return {
            "status": {
                "component_type": self.component_type,
                "component_id": self.component_id,
                "running": running
            },
            "settings": settings_dict,
            "configs": config_dict
        }

    # context-manager sugar
    def __enter__(self) -> "Service":
        self.setup_io()
        return self

    def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc_val: BaseException | None,
            _exc_tb: TracebackType | None
    ) -> Literal[False]:
        if not self._stop_event.is_set():  # only stop if not already stopped
            self.stop()  # shut down gracefully
        self._close_manager()  # close REP socket & thread
        return False  # propagate exceptions
