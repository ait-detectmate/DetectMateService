import argparse
import logging
import sys
from pathlib import Path

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


# def start_service(settings_path: Optional[Path] = None, config_path: Optional[Path] = None) -> None:
#     """Start the service with given settings and component configuration."""

#     # Load service settings
#     try:
#         # if no settings path provided, use default settings
#         if settings_path is None:
#             settings = ServiceSettings()
#         # if settings path provided but doesn't exist, raise error
#         elif not settings_path.exists():
#             logger.error(f"Settings file not found: {settings_path}")
#             sys.exit(1)
#         # otherwise, load settings from file
#         else:
#             settings = ServiceSettings.from_yaml(settings_path)
#     except Exception as e:
#         logger.error(f"Error loading settings: {e}")
#         sys.exit(1)

#     # Load parameters (if provided)
#     try:
#         if config_path is not None:
#             # if parameters file provided but doesn't exist, raise error
#             if not config_path.exists():
#                 logger.error(f"Config file not found: {config_path}")
#                 sys.exit(1)
#             # if parameters file exists, set it
#             settings.config_file = config_path
#     except Exception as e:
#         logger.error(f"Error loading config file: {e}")
#         sys.exit(1)

#     service = CLIService(settings=settings)
#     try:
#         with service:
#             service.run()
#     except KeyboardInterrupt:
#         logger.info("Shutting down service...")
#         service.stop()
#     except Exception as e:
#         logger.error(f"Service failed: {e}")
#         raise


# def stop_service(settings_path: Path) -> None:
#     """Stop a running service."""
#     try:
#         settings = ServiceSettings.from_yaml(settings_path)
#     except Exception as e:
#         logger.error(f"Error loading settings from yaml file: {e}")
#         sys.exit(1)

#     try:
#         with pynng.Req0(dial=settings.manager_addr) as req:
#             req.send(b"stop")
#             response = req.recv().decode()
#             logger.info(f"Service response: {response}")
#     except pynng.exceptions.NNGException as e:
#         logger.error(f"Communication error stopping service: {e}")
#         sys.exit(1)
#     except Exception as e:
#         logger.error(f"Unexpected error stopping service: {e}")
#         sys.exit(1)


# def reconfigure_service(settings_path: Path, config_path: Path, persist: bool) -> None:
#     """Reconfigure a running service with new parameters."""
#     try:
#         settings = ServiceSettings.from_yaml(settings_path)
#     except Exception as e:
#         logger.error(f"Error loading settings: {e}")
#         sys.exit(1)

#     # Load new parameters from YAML file
#     try:
#         with open(config_path, 'r') as f:
#             config_data = yaml.safe_load(f)
#     except FileNotFoundError:
#         logger.error(f"Parameters file not found: {config_path}")
#         sys.exit(1)
#     except PermissionError:
#         logger.error(f"Permission denied reading configuration file: {config_path}")
#         sys.exit(1)
#     except yaml.YAMLError as e:
#         logger.error(f"Invalid YAML in parameters file: {e}")
#         sys.exit(1)
#     except Exception as e:
#         logger.error(f"Unexpected error reading parameters file: {e}")
#         sys.exit(1)

#     # Convert to JSON string for the reconfigure command
#     try:
#         config_json = json.dumps(config_data)
#         if persist:
#             config_json = f"persist {config_json}"
#     except TypeError as e:
#         logger.error(f"Invalid parameters format: {e}")
#         sys.exit(1)
#     except Exception as e:
#         logger.error(f"Unexpected error serializing parameters: {e}")
#         sys.exit(1)

#     try:
#         with pynng.Req0(dial=settings.manager_addr) as req:
#             req.send(f"reconfigure {config_json}".encode())
#             response = req.recv().decode()
#             logger.info(f"Reconfiguration response: {response}")
#     except pynng.exceptions.NNGException as e:
#         logger.error(f"Communication error during reconfiguration: {e}")
#         sys.exit(1)
#     except Exception as e:
#         logger.error(f"Unexpected error during reconfiguration: {e}")
#         sys.exit(1)


# def get_status(settings_path: Path) -> None:
#     """Get the current status of the service."""
#     try:
#         settings = ServiceSettings.from_yaml(settings_path)
#     except Exception as e:
#         logger.error(f"Error loading settings: {e}")
#         sys.exit(1)

#     try:
#         with pynng.Req0(dial=settings.manager_addr) as req:
#             req.send(b"status")
#             response = req.recv().decode()

#             try:
#                 # Try to parse as JSON for pretty printing
#                 data = json.loads(response)
#                 logger.info(f"Service Status:\n {json.dumps(data, indent=2)}")
#             except json.JSONDecodeError:
#                 # Fallback to raw response if not json
#                 logger.info(f"Service status: {response}")
#     except pynng.exceptions.NNGException as e:
#         logger.error(f"Communication error getting status: {e}")
#         sys.exit(1)
#     except Exception as e:
#         logger.error(f"Unexpected error getting service status: {e}")
#         sys.exit(1)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="DetectMate Service Launcher")
    parser.add_argument("--settings", type=Path, help="Path to service settings YAML")
    parser.add_argument("--config", type=Path, help="Path to component config YAML")

    args = parser.parse_args()

    # Load settings
    if args.settings and args.settings.exists():
        settings = ServiceSettings.from_yaml(args.settings)
    else:
        settings = ServiceSettings()

    if args.config:
        settings.config_file = args.config
    logger.info("config file: %s", settings.config_file)
    # Initialize and run
    # Note: Service now inherits from Service, not CLIService
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
