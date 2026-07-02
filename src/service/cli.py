import argparse
import logging
import sys
import os
import signal
from pathlib import Path
from typing import Any

from .settings import ServiceSettings
from .core import Service

logger = logging.getLogger(__name__)
DEFAULT_SETTINGS_FILES = ["./settings", "/etc/detectmate/settings"]
DEFAULT_SETTINGS_EXTENSIONS = [".yml", ".yaml", ".YML", ".YAML"]


def setup_logging(level: int = logging.INFO) -> None:
    """Set up logging with errors to stderr and others to stdout."""
    # create separate handlers for stdout and stderr
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    # set filter to allow only non-error messages
    stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)

    # common formatter
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s')
    stdout_handler.setFormatter(formatter)
    stderr_handler.setFormatter(formatter)

    # configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="DetectMate Service Launcher")
    parser.add_argument("--settings", type=Path, help="Path to service settings YAML")
    parser.add_argument("--config", type=Path, help="Path to component config YAML")
    parser.add_argument(
        "--no-autostart",
        action="store_true",
        help="Start the service without auto-starting the engine. "
             "Use POST /admin/start to begin processing.",
    )

    args = parser.parse_args()

    # Load settings
    if not args.settings:
        for file in DEFAULT_SETTINGS_FILES:
            for ext in DEFAULT_SETTINGS_EXTENSIONS:
                settings_file = file + ext
                if os.path.exists(settings_file):
                    resolved = Path(settings_file).resolve()
                    if not Path(settings_file).is_absolute():
                        logger.warning(
                            f"No --settings provided; found config at relative path '{settings_file}' "
                            f"(resolved to '{resolved}' from CWD '{Path.cwd()}'). "
                            f"Set --settings explicitly to avoid loading an unintended file."
                        )
                    else:
                        logger.info(f"No --settings provided, using discovered config: {settings_file}")
                    args.settings = resolved
                    break
            if args.settings:
                break
        if not args.settings:
            logger.error(
                f"No --settings provided and none of the default settings paths {DEFAULT_SETTINGS_FILES} "
                f"with the extensions {DEFAULT_SETTINGS_EXTENSIONS} exists. Settings path must be defined "
                f"using the --settings argument.")
            parser.print_help()
            sys.exit(1)
    if not args.settings.exists():
        logger.error(f"Settings path {args.settings} does not exist.")
        sys.exit(1)
    settings = ServiceSettings.from_yaml(args.settings)

    overrides: dict[str, Any] = {}
    if args.no_autostart:
        overrides["engine_autostart"] = False
    if args.config:
        overrides["config_file"] = args.config
    settings = settings.model_copy(update=overrides)
    logger.info("config file: %s", settings.config_file)

    service = Service(settings=settings)
    signal.signal(signal.SIGINT, lambda s, f: service.service_exit_event.set())
    signal.signal(signal.SIGTERM, lambda s, f: service.service_exit_event.set())

    try:
        with service:
            # This blocks until service_exit_event.set() happens
            service.run()
    finally:
        logger.info("Clean exit.")


if __name__ == "__main__":
    main()
