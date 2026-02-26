from __future__ import annotations
import logging
import sys
from abc import ABC
from pathlib import Path
import threading
import json
from typing import Optional, Type, Literal, Dict, Any, cast
from types import TracebackType

from pydantic import BaseModel

from service.features.web.server import WebServer
from service.features.config_manager import ConfigManager
from service.settings import ServiceSettings
from service.features.engine import Engine, EngineException
from service.features.component_loader import ComponentLoader
from service.features.config_loader import ConfigClassLoader
from service.features.component_resolver import ComponentResolver
from detectmatelibrary.common.core import CoreComponent, CoreConfig
from prometheus_client import REGISTRY, Counter, Enum, Histogram


engine_running = Enum(
    "engine_running",
    "Whether the service engine is running (running or stopped)",
    ["component_type", "component_id"],
    states=['running', 'stopped'],
)

engine_starts_total = Counter(
    "engine_starts_total",
    "Number of times the engine was started",
    ["component_type", "component_id"]
)

processing_duration_seconds = Histogram(
    "processing_duration_seconds",
    "Time spent processing messages in seconds",
    ["component_type", "component_id"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)


def get_counter(name: str, documentation: str, labelnames: list[str]) -> Counter:
    """Safely get or create a Prometheus counter."""
    # Search the registry for an existing collector with this name
    for collector in REGISTRY._collector_to_names:
        if name in REGISTRY._collector_to_names[collector]:
            return collector
    # If not found, create it
    return Counter(name, documentation, labelnames)


data_processed_bytes_total = get_counter("data_processed_bytes_total",
                                         "Total bytes processed by the engine", [
                                             "component_type", "component_id"])


class Service(Engine, ABC):
    """Abstract base for every DetectMate service/component.

    Service acts as the processor - it implements the process() method
    that Engine calls directly.
    """

    def __init__(
            self,
            settings: ServiceSettings = ServiceSettings(),
            component_config: Dict[str, Any] | None = None
    ):
        # Prepare attributes & logger first
        self.settings: ServiceSettings = settings
        self.component_id: str = settings.component_id  # type: ignore[assignment]
        self._service_exit_event: threading.Event = threading.Event()
        self.web_server = None
        self.web_server = WebServer(self)

        self.log: logging.Logger = self._build_logger()
        # set component_type
        if hasattr(self, 'component_type'):  # prioritize class attribute over settings
            pass  # already set by the child class
        elif (hasattr(settings, "component_type") and
                settings.component_type not in ("core",) and
                not settings.component_type.startswith("core")):

            resolved_type, resolved_config = ComponentResolver.resolve(
                settings.component_type
            )
            old_component_type = settings.component_type
            settings.component_type = resolved_type

            # Keep self.component_type in sync with the resolved full path
            if not hasattr(self.__class__, 'component_type'):
                self.component_type = resolved_type

            # Now build the logger (which uses component_type)
            self.log = self._build_logger()

            # Log what resolver did
            if resolved_type != old_component_type:
                self.log.info(
                    "Resolved '%s'  →  component: %s  |  config: %s",
                    old_component_type, resolved_type, resolved_config,
                )

            if not settings.component_config_class:
                settings.component_config_class = resolved_config

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
                    config_to_use, logger=self.log
                )
                self.log.info(f"Successfully loaded component: {self.library_component}")
            except Exception as e:
                self.log.error(f"Failed to load component {settings.component_type}: {e}")
                raise

        # Service IS the processor - Engine will call self.process() directly
        Engine.__init__(self, settings=settings, processor=self, logger=self.log)
        self.log.debug("%s[%s] created and fully initialized", self.component_type, self.component_id)

    def get_config_schema(self) -> Type[CoreConfig]:
        """Return the configuration schema for this service.

        If component_config_class is specified in settings, load and
        return it. Otherwise, return the default CoreConfig.
        """
        if hasattr(self.settings, 'component_config_class') and self.settings.component_config_class:
            try:
                self.log.debug(f"Loading config class: {self.settings.component_config_class}")
                config_class = ConfigClassLoader.load_config_class(
                    self.settings.component_config_class, logger=self.log)
                self.log.debug(f"Successfully loaded config class: {config_class}")
                return config_class
            except Exception as e:
                self.log.error(f"Failed to load config class {self.settings.component_config_class}: {e}")
                raise
        return cast(Type[CoreConfig], CoreConfig)  # help mypy

    def process(self, raw_message: bytes) -> bytes | None | Any:
        """Process the raw message.

        This is the main processing method that Engine calls directly.

        Tracks metrics and delegates to library component if available,
        otherwise returns raw message unchanged.
        """
        if raw_message:
            data_processed_bytes_total.labels(
                component_type=self.component_type,
                component_id=self.component_id
            ).inc(len(raw_message))

        # Track processing time
        with processing_duration_seconds.labels(
            component_type=self.component_type,
            component_id=self.component_id
        ).time():
            if self.library_component:
                # Delegate to the library component's process method
                return self.library_component.process(raw_message)
            else:
                # Default passthrough behavior for core services without components
                return raw_message

    # public API
    def setup_io(self) -> None:
        """Hook for loading models, etc."""
        self.log.info("setup_io: ready to process messages")

    def run(self) -> None:
        """Starts the WebServer and waits for the shutdown signal."""
        # 1. Start Web Server (Admin API)
        if self.web_server:
            self.log.info(f"HTTP Admin active at {self.settings.http_host}:{self.settings.http_port}")
            self.web_server.start()

        # 2. Engine Start logic
        # __init__ is 100% finished
        if self.settings.engine_autostart:
            self.log.info("Auto-starting engine...")
            self.start()
        else:
            self.log.info("Engine idle. Awaiting /admin/start")

        # 3. Wait for the global shutdown event
        self._service_exit_event.wait()

        # 4. Final teardown
        if self.web_server:
            self.web_server.stop()
        if getattr(self, "_running", False):
            self.stop()  # This calls the Service.stop which calls Engine.stop
        else:
            self.log.debug("Engine already stopped")

    def start(self) -> str:
        """Expose engine start as a command."""
        # Check if already running to avoid redundant starts
        if getattr(self, '_running', False):
            msg = "Ignored: Engine is already running"
            self.log.debug(msg)
            return msg

        engine_starts_total.labels(
            component_type=self.component_type,
            component_id=self.component_id
        ).inc()

        msg = Engine.start(self)

        engine_running.labels(
            component_type=self.component_type,
            component_id=self.component_id
        ).state('running')

        self.log.info(msg)
        return msg

    def stop(self) -> str:
        """Stop both the engine loop and mark the component to exit."""
        if not getattr(self, "_running", False):
            return "engine already stopped"

        self.log.info("Stop command received")
        try:
            Engine.stop(self)
            engine_running.labels(
                component_type=self.component_type,
                component_id=self.component_id
            ).state('stopped')
            self.log.info("Engine stopped successfully")
            return "engine stopped"
        except EngineException as e:
            self.log.error("Failed to stop engine: %s", e)
            return f"error: failed to stop engine - {e}"

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

    def reconfigure(self, config_data: Dict[str, Any], persist: bool = False) -> str:
        """Reconfigure service configurations dynamically.

        Args:
            config_data: Configuration dictionary to apply
            persist: If True, save the configuration to disk using to_dict()
                    to preserve only user-specified values without defaults

        Returns:
            Status message indicating success or failure
        """
        if not self.config_manager:
            return "reconfigure: no config manager configured"

        if not config_data:
            return "reconfigure: no-op (empty config data)"

        try:
            # update in memory
            self.config_manager.update(config_data)

            if persist:
                # Get the validated config
                validated_config = self.config_manager.get()
                if validated_config is None:
                    config_dict = {}
                # Convert to dict using to_dict() to strip defaults and maintain YAML structure
                elif validated_config and hasattr(validated_config, 'to_dict'):
                    config_dict = validated_config.to_dict()
                    self.log.debug(f"Converted config to dict for persistence: {config_dict}")
                elif isinstance(validated_config, dict):
                    config_dict = validated_config
                elif isinstance(validated_config, BaseModel):
                    config_dict = validated_config.model_dump()
                else:
                    config_dict = {}

                # Save to disk
                self.config_manager.save(config_dict)
                self.log.info("Persisted configuration to disk")

            self.log.info("Reconfigured with: %s", config_data)
            return "reconfigure: ok"

        except Exception as e:
            self.log.error("Reconfiguration error: %s", e)
            return f"reconfigure: error - {e}"

    def shutdown(self) -> str:
        """Stops everything and exits the process."""
        self.log.info("Process shutdown initiated.")
        self._service_exit_event.set()
        return "Service is shutting down..."

    # helpers

    def _build_logger(self) -> logging.Logger:
        component_type = getattr(self, 'component_type', 'service')
        component_id = getattr(self, 'component_id', 'unknown')
        Path(self.settings.log_dir).mkdir(parents=True, exist_ok=True)
        name = f"{component_type}.{component_id}"
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
                Path(self.settings.log_dir) / f"{component_type}_{component_id}.log",
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
        if not self._service_exit_event.is_set():  # only stop if not already stopped
            self.shutdown()  # shut down gracefully  # close REP socket & thread
        return False  # propagate exceptions
