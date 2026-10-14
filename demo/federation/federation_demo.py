"""Federation demo controller.

1. Train each site on its own users.
2. Show that a site alerts on users it has never seen, even if another site knows them.
3. Run one stack-later federation round through the HTTP API.
4. Show that known users no longer alert anywhere, while unknown users still do.
"""
import os
import time
from typing import Any, Iterable, cast

import pynng
import requests
import detectmatelibrary.schemas as schemas

SITES = {
    "site-a": ["alice", "bob"],
    "site-b": ["carol", "dave"],
    "site-c": ["erin"],
}
HUB = "hub"
CHECKS = [("site-a", "carol"), ("site-c", "alice"), ("site-b", "mallory")]

session = requests.Session()
session.headers["X-Auth-Token"] = os.environ.get("DETECTMATE_HTTP_API_KEY", "")


def api(node: str, method: str, path: str, **kwargs: Any) -> requests.Response:
    resp = session.request(method, f"http://{node}:8000/api/v1/{path}", timeout=30, **kwargs)
    resp.raise_for_status()
    return resp


def wait_until_up(nodes: Iterable[str]) -> None:
    for node in nodes:
        for _ in range(120):
            try:
                api(node, "get", "status")
                break
            except requests.RequestException:
                time.sleep(1)
        else:
            raise SystemExit(f"{node} did not come up")


def login(user: str) -> bytes:
    return cast(bytes, schemas.ParserSchema({
        "parserType": "demo", "parserID": "demo", "EventID": 1, "template": "login <*>",
        "variables": [user], "logID": user, "parsedLogID": user, "log": f"login {user}",
        "logFormatVariables": {},
    }).serialize())


def send(node: str, users: Iterable[str], expect_reply: bool = False) -> bool:
    """Send login events to a node; return True if it answered with an
    alert."""
    with pynng.Pair0(dial=f"tcp://{node}:5000", recv_timeout=2000) as sock:
        for user in users:
            sock.send(login(user))
        if not expect_reply:
            time.sleep(1)  # let the engine process before the caller changes state
            return False
        try:
            sock.recv()
            return True
        except pynng.Timeout:
            return False


def run_checks(title: str) -> None:
    print(f"\n{title}")
    for node, user in CHECKS:
        alert = send(node, [user], expect_reply=True)
        print(f"  {node:7} login {user:8} -> {'ALERT' if alert else 'no alert'}")


def federate() -> None:
    nodes = [*SITES, HUB]
    for node in nodes:
        api(node, "post", "stop")

    binaries = [api(site, "get", "federation/export").content for site in SITES]
    api(HUB, "post", "federation/stack",
        files=[("files", (f"{site}.bin", b)) for site, b in zip(SITES, binaries)])
    global_binary = api(HUB, "post", "federation/aggregate").content
    print(f"  hub aggregated {len(binaries)} sites")

    for site in SITES:
        resp = session.post(f"http://{site}:8000/api/v1/federation/adopt",
                            files={"file": ("global.bin", global_binary)}, timeout=30)
        if resp.status_code == 501:
            # Detector without its own load_binary(): adopt the hub's learned state instead.
            state = api(HUB, "get", "persistency/export").content
            api(site, "post", "persistency/import", files={"file": ("hub_state.zip", state)})
            print(f"  {site} adopted the hub state via /api/v1/persistency/import")
        else:
            resp.raise_for_status()
            print(f"  {site} adopted the global binary")
        api(site, "post", "start")


def main() -> None:
    wait_until_up([*SITES, HUB])

    print("Training")
    for site, users in SITES.items():
        api(site, "post", "training/state", json={"state": "keep_training"})
        send(site, users)
        api(site, "post", "training/state", json={"state": "stop_training"})
        print(f"  {site} learned {', '.join(users)}")

    run_checks("Before federation")
    print("\nFederation round")
    federate()
    run_checks("After federation")
    print("\nHub:", api(HUB, "get", "federation/status").json())


if __name__ == "__main__":
    main()
