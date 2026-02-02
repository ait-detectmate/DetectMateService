#!/usr/bin/env python3
import argparse
import sys
import json
import yaml
import requests


class DetectMateClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.timeout: int = 10

    def _handle_response(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
            print(json.dumps(response.json(), indent=2))
        except requests.exceptions.HTTPError as e:
            print(f"Error: {e}")
            if response.text:
                print(f"Details: {response.text}")
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}")
            sys.exit(1)

    def start(self) -> None:
        print(f"Sending START to {self.base_url}...")
        response = requests.post(f"{self.base_url}/admin/start", timeout=self.timeout)
        self._handle_response(response)

    def stop(self) -> None:
        print(f"Sending STOP to {self.base_url}...")
        response = requests.post(f"{self.base_url}/admin/stop", timeout=self.timeout)
        self._handle_response(response)

    def status(self) -> None:
        response = requests.get(f"{self.base_url}/admin/status", timeout=self.timeout)
        self._handle_response(response)

    def reconfigure(self, yaml_file: str, persist: bool) -> None:
        try:
            with open(yaml_file, 'r') as f:
                config_data = yaml.safe_load(f)

            payload = {
                "config": config_data,
                "persist": persist
            }

            print(f"Sending RECONFIGURE (persist={persist}) to {self.base_url}...")
            response = requests.post(
                f"{self.base_url}/admin/reconfigure", timeout=self.timeout,
                json=payload
            )
            self._handle_response(response)
        except FileNotFoundError:
            print(f"Error: File '{yaml_file}' not found.")
        except yaml.YAMLError as e:
            print(f"Error parsing YAML: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="detectmate-client",
        description="CLI Client for DetectMateService HTTP Admin API"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the service (default: http://localhost:8000)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Start
    subparsers.add_parser("start", help="Start the detection engine")

    # Stop
    subparsers.add_parser("stop", help="Stop the detection engine")

    # Status
    subparsers.add_parser("status", help="Get service status and configuration")

    # Reconfigure
    reconf = subparsers.add_parser("reconfigure", help="Update configuration from a YAML file")
    reconf.add_argument("file", help="Path to the YAML configuration file")
    reconf.add_argument(
        "--persist",
        action="store_true",
        help="Persist changes to the service's config file"
    )

    args = parser.parse_args()
    client = DetectMateClient(args.url)

    if args.command == "start":
        client.start()
    elif args.command == "stop":
        client.stop()
    elif args.command == "status":
        client.status()
    elif args.command == "reconfigure":
        client.reconfigure(args.file, args.persist)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
