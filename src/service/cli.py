import argparse
import json
from typing import Optional
from pathlib import Path
import pynng
import yaml

from .settings import ServiceSettings
from .core import Service


def start_service(settings_path: Path, params_path: Optional[Path] = None):
    """Start the service with given settings and parameters."""
    settings = ServiceSettings.from_yaml(settings_path)

    if params_path:
        settings.parameter_file = params_path

    service = Service(settings=settings)
    try:
        with service:
            service.run()
    except KeyboardInterrupt:
        print("Shutting down service...")
        service.stop()


def stop_service(settings_path: Path):
    """Stop a running service."""
    settings = ServiceSettings.from_yaml(settings_path)

    try:
        with pynng.Req0(dial=settings.manager_addr) as req:
            req.send(b"stop")
            response = req.recv().decode()
            print(f"Service response: {response}")
    except Exception as e:
        print(f"Error stopping service: {e}")


def reconfigure_service(settings_path: Path, params_path: Path):
    """Reconfigure a running service with new parameters."""
    settings = ServiceSettings.from_yaml(settings_path)

    # Load new parameters from YAML file
    try:
        with open(params_path, 'r') as f:
            params_data = yaml.safe_load(f)

        # Convert to JSON string for the reconfigure command
        params_json = json.dumps(params_data)

        with pynng.Req0(dial=settings.manager_addr) as req:
            req.send(f"reconfigure {params_json}".encode())
            response = req.recv().decode()
            print(f"Reconfiguration response: {response}")

    except Exception as e:
        print(f"Error reconfiguring service with file {params_path}: {e}")


def get_status(settings_path: Path):
    """Get the current status of the service."""
    settings = ServiceSettings.from_yaml(settings_path)

    try:
        with pynng.Req0(dial=settings.manager_addr) as req:
            req.send(b"status")
            response = req.recv().decode()

            try:
                # Try to parse as JSON for pretty printing
                data = json.loads(response)
                print("Service Status:")
                print(json.dumps(data, indent=2))
            except json.JSONDecodeError:
                # Fallback to raw response if not json
                print(f"Service status: {response}")

    except Exception as e:
        print(f"Error getting service status: {e}")


def main():
    parser = argparse.ArgumentParser(description="DetectMate Service CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Start command
    start_parser = subparsers.add_parser("start", help="Start the service")
    start_parser.add_argument("--settings", required=True, type=Path, help="Service settings YAML file")
    start_parser.add_argument("--params", type=Path, help="Service parameters YAML file")

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop the service")
    stop_parser.add_argument("--settings", required=True, type=Path, help="Service settings YAML file")

    # Status command
    status_parser = subparsers.add_parser("status", help="Get service status")
    status_parser.add_argument("--settings", required=True, type=Path, help="Service settings YAML file")

    # Reconfigure command
    reconfigure_parser = subparsers.add_parser("reconfigure", help="Reconfigure service parameters")
    reconfigure_parser.add_argument("--settings", required=True, type=Path,
                                    help="Service settings YAML file (to get manager address)")
    reconfigure_parser.add_argument("--params", required=True, type=Path, help="New parameters YAML file")

    args = parser.parse_args()

    if args.command == "start":
        start_service(args.settings, args.params)
    elif args.command == "stop":
        stop_service(args.settings)
    elif args.command == "status":
        get_status(args.settings)
    elif args.command == "reconfigure":
        reconfigure_service(args.settings, args.params)


if __name__ == "__main__":
    main()
