import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from .settings import ServiceSettings
from .core import Service

logger = logging.getLogger(__name__)


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
    if args.settings and args.settings.exists():
        settings = ServiceSettings.from_yaml(args.settings)
    else:
        logger.error("Settings path must be defined.")
        parser.print_help()
        sys.exit(1)

    overrides: dict[str, Any] = {}
    if args.no_autostart:
        overrides["engine_autostart"] = False
    if args.config:
        overrides["config_file"] = args.config
    settings = settings.model_copy(update=overrides)
    logger.info("config file: %s", settings.config_file)
    service = Service(settings=settings)

    try:
        with service:
            # This blocks until _stop_event.set() or KeyboardInterrupt
            service.run()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received (Ctrl+C)...")
    finally:
        logger.info("Clean exit.")


if __name__ == "__main__":
    main()
