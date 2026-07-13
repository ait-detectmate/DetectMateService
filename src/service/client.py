#!/usr/bin/env python3
import argparse
import sys
import json
import yaml
import requests


class DetectMateClient:
    def __init__(self, base_url: str):
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
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

    def metrics(self) -> None:
        response = requests.get(f"{self.base_url}/metrics", timeout=self.timeout)
        try:
            response.raise_for_status()
            # Prometheus returns plain text
            print(response.text)
        except requests.exceptions.HTTPError as e:
            print(f"Error: {e}")
            sys.exit(1)

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

    def persistency_status(self) -> None:
        response = requests.get(f"{self.base_url}/admin/persistency/status", timeout=self.timeout)
        self._handle_response(response)

    def persistency_save(self) -> None:
        print(f"Sending PERSISTENCY SAVE to {self.base_url}...")
        response = requests.post(f"{self.base_url}/admin/persistency/save", timeout=self.timeout)
        self._handle_response(response)

    def persistency_load(self) -> None:
        print(f"Sending PERSISTENCY LOAD to {self.base_url}...")
        response = requests.post(f"{self.base_url}/admin/persistency/load", timeout=self.timeout)
        self._handle_response(response)

    def persistency_export(self, outfile: str) -> None:
        print(f"Exporting state from {self.base_url} to {outfile}...")
        try:
            response = requests.get(f"{self.base_url}/admin/persistency/export", timeout=self.timeout)
            response.raise_for_status()
            with open(outfile, "wb") as f:
                f.write(response.content)
            print(f"State saved to {outfile}")
        except requests.exceptions.HTTPError as e:
            print(f"Error: {e}")
            if response.text:
                print(f"Details: {response.text}")
            sys.exit(1)

    def persistency_import(self, filepath: str) -> None:
        print(f"Sending PERSISTENCY IMPORT from {filepath} to {self.base_url}...")
        try:
            with open(filepath, "rb") as f:
                response = requests.post(
                    f"{self.base_url}/admin/persistency/import",
                    files={"file": (filepath, f, "application/zip")},
                    timeout=self.timeout,
                )
            self._handle_response(response)
        except FileNotFoundError:
            print(f"Error: File '{filepath}' not found.")
            sys.exit(1)

    def training_get_state(self) -> None:
        response = requests.get(f"{self.base_url}/admin/training/state", timeout=self.timeout)
        self._handle_response(response)

    def training_set_state(self, state: str) -> None:
        print(f"Sending TRAINING STATE '{state}' to {self.base_url}...")
        response = requests.post(
            f"{self.base_url}/admin/training/state", timeout=self.timeout,
            json={"state": state}
        )
        self._handle_response(response)


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

    subparsers.add_parser("metrics", help="Get service metrics")

    # Reconfigure
    reconf = subparsers.add_parser("reconfigure", help="Update configuration from a YAML file")
    reconf.add_argument("file", help="Path to the YAML configuration file")
    reconf.add_argument(
        "--persist",
        action="store_true",
        help="Persist changes to the service's config file"
    )

    # Persistency
    subparsers.add_parser("persistency-status", help="Show persistency config, counters, and last save time")
    subparsers.add_parser("persistency-save", help="Force an immediate save of learned state to storage")
    subparsers.add_parser("persistency-load", help="Restore learned state from storage")
    pe = subparsers.add_parser("persistency-export", help="Download current state as a zip archive")
    pe.add_argument("outfile", help="Path to save the downloaded state archive")
    pi = subparsers.add_parser("persistency-import", help="Upload and restore state from a zip archive")
    pi.add_argument("file", help="Path to the state archive to import")

    # Training state
    subparsers.add_parser("training-get-state", help="Get current training/configure phase state")
    ts = subparsers.add_parser("training-set-state", help="Override training or configure phase")
    ts.add_argument(
        "state",
        choices=["keep_training", "stop_training", "keep_configuring", "stop_configuring"],
        help="State to set"
    )

    args = parser.parse_args()
    client = DetectMateClient(args.url)

    if args.command == "start":
        client.start()
    elif args.command == "stop":
        client.stop()
    elif args.command == "status":
        client.status()
    elif args.command == "metrics":
        client.metrics()
    elif args.command == "reconfigure":
        client.reconfigure(args.file, args.persist)
    elif args.command == "persistency-status":
        client.persistency_status()
    elif args.command == "persistency-save":
        client.persistency_save()
    elif args.command == "persistency-load":
        client.persistency_load()
    elif args.command == "persistency-export":
        client.persistency_export(args.outfile)
    elif args.command == "persistency-import":
        client.persistency_import(args.file)
    elif args.command == "training-get-state":
        client.training_get_state()
    elif args.command == "training-set-state":
        client.training_set_state(args.state)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
