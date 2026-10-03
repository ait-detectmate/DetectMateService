"""Tests that the engine_running Prometheus metric tracks every engine state
transition, including an unexpected loop-thread exit."""
import uuid

import pytest
from prometheus_client import REGISTRY

from service.core import Service
from service.features.engine import EngineState
from service.settings import ServiceSettings

pytestmark = pytest.mark.filterwarnings(
    "ignore::pytest.PytestUnhandledThreadExceptionWarning"
)


class EchoService(Service):
    component_type = "metric_test"

    def process(self, raw_message: bytes) -> bytes | None:
        return raw_message


class CrashingService(EchoService):
    """Crashes the loop body while `crash` is set; runs normally otherwise."""
    crash = True

    def _run_loop_body(self, labels):
        if self.crash:
            raise RuntimeError("simulated unexpected crash")
        super()._run_loop_body(labels)


class FailingHookService(CrashingService):
    def _on_state_change(self, new_state):
        raise RuntimeError("hook failed")


def make_service(cls, tmp_path):
    return cls(settings=ServiceSettings(
        engine_addr=f"ipc://{tmp_path}/metric_engine.ipc",
        component_id=uuid.uuid4().hex,  # fresh metric label set per test
        engine_autostart=False,
        log_level="ERROR",
    ))


def labels(service):
    return {"component_type": service.component_type, "component_id": service.component_id}


def metric_state(service):
    """The engine_running state currently set to 1."""
    active = [s for s in ("running", "stopped")
              if REGISTRY.get_sample_value("engine_running", {**labels(service), "engine_running": s}) == 1]
    assert len(active) == 1, active
    return active[0]


def starts_total(service):
    return REGISTRY.get_sample_value("engine_starts_total", labels(service)) or 0.0


def wait_for_crash(service):
    # the self-heal runs in the loop thread's finally, so join() is enough
    service._thread.join(timeout=2.0)
    assert service._state == EngineState.STOPPED


def test_metric_follows_normal_start_stop(tmp_path):
    service = make_service(EchoService, tmp_path)
    service.start()
    assert metric_state(service) == "running"
    service.stop()
    assert metric_state(service) == "stopped"


def test_metric_follows_crash_and_restart(tmp_path):
    service = make_service(CrashingService, tmp_path)
    service.start()
    wait_for_crash(service)
    assert metric_state(service) == "stopped"

    # stop() after a crash is a no-op and must not flip the metric back
    assert service.stop() == "engine already stopped"
    assert metric_state(service) == "stopped"

    service.crash = False
    before = starts_total(service)
    assert service.start() == "engine started"
    try:
        assert metric_state(service) == "running"
        assert starts_total(service) == before + 1
    finally:
        service.stop()


def test_failing_hook_does_not_break_crash_path(tmp_path):
    service = make_service(FailingHookService, tmp_path)
    service.start()
    wait_for_crash(service)

    # sockets closed and lock released despite the hook raising
    with pytest.raises(Exception):
        service._pair_sock.send(b"socket should be closed")
    assert service._lifecycle_lock.acquire(timeout=0.1)
    service._lifecycle_lock.release()
