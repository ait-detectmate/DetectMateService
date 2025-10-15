"""Tests that demonstrate how to build a parser+detector pipeline on top of the
Service's Engine/Manager.

- Demo 1: two detectors; anomaly-based (unknown events) and signature-based (count in window)
- Demo 2: update Detector_2 config (limit_count) at runtime after 5 logs
- Demo 3: training Detector_1 mid-stream to expand known events
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from typing import Any, List, Optional, Tuple

import pynng

from service.core import Service
from service.settings import ServiceSettings
from service.schemas.schemas import ParserSchema


# Minimal app logic classes
class Parser1:
    """Mirrors basic_methods/methods.py."""
    def parse(self, raw_log: str) -> ParserSchema:
        # Expected format: "LEVEL YYYY-MM-DD HH:MM:SS - message"
        format_part, msg = raw_log.split(" - ", 1)
        level, date, time_ = format_part.split(" ", 2)

        out = ParserSchema(
            parserType="demo-parser",
            parserID=0,
            logID=0,
            log=raw_log,
            logFormatVariables={"LEVEL": level, "DATE": date, "TIME": time_},
        )

        if "Server" in msg:
            # "Server started" or "Server running"
            out.template = "Server<*>"
            out.variables = [msg.split(" ")[1]]
            out.EventID = 0
        elif "Connection failed" in msg:
            out.template = "Connection failed"
            out.variables = []
            out.EventID = 1
        elif "New log message" in msg:
            out.template = "New log message:<*>"
            out.variables = [msg.split(": ", 1)[1]]
            out.EventID = 2
        else:
            # any unknown template -> new ID 99 for this test
            out.template = "UNKNOWN"
            out.variables = [msg]
            out.EventID = 99

        return out


class Detector1:
    """Anomaly-based detector: alerts on EventIDs NOT in known_events."""

    def __init__(self, known_events: Optional[set[int]] = None) -> None:
        self.known_events: set[int] = set() if known_events is None else set(known_events)

    def detect(self, parsed: ParserSchema) -> Tuple[bool, float]:
        if parsed.EventID not in self.known_events:
            # score 0.8
            return True, 0.8
        return False, 0.0

    def train_union(self, new_events: set[int]) -> None:
        self.known_events |= set(new_events)


class Detector2:
    """Signature-based detector: count target_event in a rolling window (> limit_count)."""

    def __init__(self, limit_count: int = 2, target_event: int = 1, window_size: int = 3) -> None:
        self.limit_count = limit_count
        self.target_event = target_event
        self.window_size = window_size
        self._window: deque[int] = deque(maxlen=window_size)

    def set_limit(self, limit_count: int) -> None:
        self.limit_count = int(limit_count)

    def detect(self, parsed: ParserSchema) -> Tuple[bool, float]:
        self._window.append(parsed.EventID)
        count = sum(1 for eid in self._window if eid == self.target_event)
        return (count > self.limit_count), float(count)


def _payload_to_bytes(payload: dict[str, Any]) -> bytes:
    """Helper to JSON-encode a dict coming from pydantic models."""
    return json.dumps(payload, default=str).encode("utf-8")


# Service-based demo classes
class Demo1Component(Service):
    """Demo 1: two detectors; D1 (unknown events) and D2 (windowed count)."""

    component_type = "demo1"

    def __init__(self, settings: ServiceSettings) -> None:
        super().__init__(settings=settings)
        self.parser = Parser1()
        self.det1 = Detector1(known_events={0, 1})  # known: Server and Connection failed
        self.det2 = Detector2(limit_count=2, target_event=1, window_size=3)

    def process(self, raw: bytes) -> bytes | None:
        txt = raw.decode("utf-8", "ignore")
        p = self.parser.parse(txt)

        d1_alert, d1_score = self.det1.detect(p)
        d2_alert, d2_score = self.det2.detect(p)
        winner = "detector_1" if d1_alert else ("detector_2" if d2_alert else "none")

        return _payload_to_bytes(
            {
                "input": txt,
                "parsed": p.model_dump(),
                "alerts": {
                    "detector_1": {"prediction": d1_alert, "score": d1_score},
                    "detector_2": {"prediction": d2_alert, "score": d2_score},
                },
                "winner": winner,
            }
        )


class Demo2Component(Service):
    component_type = "demo2"

    def __init__(self, settings: ServiceSettings):
        super().__init__(settings=settings)
        self.parser = Parser1()
        self.det1 = Detector1({0, 1})
        self.det2 = Detector2(limit_count=2, target_event=1, window_size=3)
        self._idx = 0

    def process(self, raw: bytes) -> bytes | None:
        if self._idx == 5:  # update after 5 logs
            self.det2.set_limit(10)
        self._idx += 1

        txt = raw.decode("utf-8", "ignore")
        p = self.parser.parse(txt)
        d1_alert, d1_score = self.det1.detect(p)
        d2_alert, d2_score = self.det2.detect(p)
        winner = "detector_1" if d1_alert else ("detector_2" if d2_alert else "none")

        return _payload_to_bytes(
            {
                "input": txt,
                "idx": self._idx - 1,
                "detector_2_limit": self.det2.limit_count,
                "parsed": p.model_dump(),
                "alerts": {
                    "detector_1": {"prediction": d1_alert, "score": d1_score},
                    "detector_2": {"prediction": d2_alert, "score": d2_score},
                },
                "winner": winner,
            }
        )


class Demo3Component(Service):
    component_type = "demo3"

    def __init__(self, settings: ServiceSettings):
        super().__init__(settings=settings)
        self.parser = Parser1()
        self.det1 = Detector1(set())   # start with empty set
        self._idx = 0

    def process(self, raw: bytes) -> bytes | None:
        if self._idx == 5:
            self.det1.train_union({0, 1, 2})  # training mid-stream
        self._idx += 1

        txt = raw.decode("utf-8", "ignore")
        p = self.parser.parse(txt)
        d1_alert, d1_score = self.det1.detect(p)

        return _payload_to_bytes(
            {
                "input": txt,
                "idx": self._idx - 1,
                "parsed": p.model_dump(),
                "alerts": {"detector_1": {"prediction": d1_alert, "score": d1_score}},
                "winner": "detector_1" if d1_alert else "none",
                "trained_after_idx_5": self._idx > 5,
            }
        )


# pytest infrastructure
def run_component_in_thread(comp: Service) -> threading.Thread:
    t = threading.Thread(target=comp.run, daemon=True)
    t.start()
    time.sleep(0.2)  # let sockets/threads spin up
    return t


def dial_pair(addr: str) -> pynng.Pair0:
    sock = pynng.Pair0(dial=addr)
    # wait brief handshake
    time.sleep(0.1)
    return sock


# Demo 1 test
def test_demo1_pipeline(tmp_path):
    """End-to-end: Parser + two Detectors riding on Service Engine."""
    settings = ServiceSettings(
        manager_addr=f"ipc://{tmp_path}/d1_cmd.ipc",
        engine_addr=f"ipc://{tmp_path}/d1_engine.ipc",
        engine_autostart=True,
        log_level="DEBUG",
    )
    comp = Demo1Component(settings=settings)
    thread = run_component_in_thread(comp)

    logs = [
        "INFO 2025-02-01 12:00:00 - Server started",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "INFO 2025-02-01 12:10:00 - Server running",
        "INFO 2025-02-01 12:20:00 - Server running",
        "INFO 2025-02-01 12:30:00 - Server running",
        "INFO 2025-02-01 12:40:00 - Server running",
        "INFO 2025-02-01 12:41:00 - New log message: Lol I hacked you <3",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
    ]

    winners: List[str] = []

    with dial_pair(comp.settings.engine_addr) as sock:
        for log in logs:
            sock.send(log.encode("utf-8"))
            resp = sock.recv()
            obj = json.loads(resp.decode("utf-8"))
            winners.append(obj["winner"])

    assert winners == [
        "none", "none", "none", "none", "none", "none",
        "detector_1",  # unknown EventID 2
        "none", "none",
        "detector_2", "detector_2", "detector_2", "detector_2",
    ]

    comp.stop()
    time.sleep(0.1)
    # Check that stop event is set and thread is not alive
    assert comp._stop_event.is_set()
    assert not thread.is_alive() or comp._stop_event.is_set()


# Demo 2 test
def test_demo2_update_detector_config_midstream(tmp_path):
    """Detector 2 limit updated after 5 logs -> alerts stop after update."""
    cfg = ServiceSettings(
        manager_addr=f"ipc://{tmp_path}/d2_cmd.ipc",
        engine_addr=f"ipc://{tmp_path}/d2_eng.ipc",
        engine_autostart=True,
        log_level="DEBUG",
    )
    comp = Demo2Component(cfg)
    thr = run_component_in_thread(comp)

    logs = [
        "INFO 2025-02-01 12:00:00 - Server started",
        "INFO 2025-02-01 12:10:00 - Server running",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "ERROR 2025-02-01 12:05:00 - Connection failed",  # alert (limit=2)
        "INFO 2025-02-01 12:10:00 - Server running",  # limit now 10
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "ERROR 2025-02-01 12:05:00 - Connection failed",  # no alert
    ]

    winners, limits = [], []
    with dial_pair(cfg.engine_addr) as sock:
        for log in logs:
            sock.send(log.encode())
            resp = json.loads(sock.recv())
            winners.append(resp["winner"])
            limits.append(resp["detector_2_limit"])

    assert winners == ["none", "none", "none", "none", "detector_2", "none", "none", "none", "none"]
    assert limits[:5] == [2]*5 and limits[5:] == [10]*4

    comp.stop()
    time.sleep(0.1)
    assert comp._stop_event.is_set()
    assert not thr.is_alive() or comp._stop_event.is_set()


# Demo 3 test
def test_demo3_training_midstream(tmp_path):
    """Detector 1 starts with known_events = {} so everything alerts.

    After 5 logs we train with {0,1,2}; subsequent logs should be OK.
    """
    cfg = ServiceSettings(
        manager_addr=f"ipc://{tmp_path}/d3_cmd.ipc",
        engine_addr=f"ipc://{tmp_path}/d3_eng.ipc",
        engine_autostart=True,
        log_level="DEBUG",
    )
    comp = Demo3Component(cfg)
    thr = run_component_in_thread(comp)

    logs = [
        "INFO 2025-02-01 12:00:00 - Server started",  # EventID 0
        "ERROR 2025-02-01 12:05:00 - Connection failed",  # EventID 1
        "INFO 2025-02-01 12:10:00 - Server running",  # 0
        "INFO 2025-02-01 12:20:00 - Server running",  # 0
        "ERROR 2025-02-01 12:05:00 - Connection failed",  # 1
        "INFO 2025-02-01 12:30:00 - Server running",  # training done before this
        "INFO 2025-02-01 12:40:00 - Server running",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "INFO 2025-02-01 12:30:00 - Server running",
        "INFO 2025-02-01 12:40:00 - Server running",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
        "ERROR 2025-02-01 12:05:00 - Connection failed",
    ]

    winners = []
    with dial_pair(cfg.engine_addr) as sock:
        for log in logs:
            sock.send(log.encode())
            winners.append(json.loads(sock.recv())["winner"])

    assert winners[:5] == ["detector_1"]*5
    assert winners[5:] == ["none"]*(len(winners)-5)

    comp.stop()
    time.sleep(0.1)
    assert comp._stop_event.is_set()
    assert not thr.is_alive() or comp._stop_event.is_set()
