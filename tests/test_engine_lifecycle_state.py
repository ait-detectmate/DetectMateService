"""Tests for the STOPPING state guard and unexpected-thread-death self-healing.

- EngineState.STOPPING blocks a second start() while a stop() couldn't
  confirm the loop thread died, and a later stop() retries the join.
- _handle_unexpected_loop_exit() self-heals _state when the loop thread
  dies without stop() being called (e.g. an uncaught exception).
"""
import time

import pynng
import pytest

from service.settings import ServiceSettings
from service.features.engine import Engine, EngineException, EngineState


class SimpleProcessor:
    def process(self, raw_message: bytes) -> bytes:
        return raw_message


class SlowProcessor:
    """Blocks the loop thread inside process() so stop()'s join times out."""

    def process(self, raw_message: bytes) -> bytes:
        time.sleep(2.5)
        return raw_message


class CrashingEngine(Engine):
    """Simulates an uncaught exception escaping the loop body."""

    def _run_loop_body(self, labels):
        raise RuntimeError("simulated unexpected crash")


@pytest.fixture
def settings(tmp_path):
    return ServiceSettings(
        engine_addr=f"ipc://{tmp_path}/lifecycle_engine.ipc",
        engine_autostart=False,
    )


def test_stop_timeout_leaves_stopping_and_blocks_restart(settings):
    """A stop() that can't join the loop thread leaves _state at STOPPING,
    start() refuses to spin up a second thread, and a later stop() retries the
    join once the thread has exited."""
    engine = Engine(settings=settings, processor=SlowProcessor())
    # With no outputs configured the loop replies on the pair socket, so the
    # peer must stay connected and drain the reply or send() blocks forever.
    sender = pynng.Pair0(dial=str(settings.engine_addr), recv_timeout=5000)
    try:
        engine.start()
        time.sleep(0.1)
        sender.send(b"slow")
        time.sleep(0.1)  # let the loop thread enter process()
        thread = engine._thread

        with pytest.raises(EngineException, match="failed to stop cleanly"):
            engine.stop()
        assert engine._state == EngineState.STOPPING

        assert engine.start() == "engine already running"
        assert engine._thread is thread

        # the loop exits on its own once process() returns; it must not
        # self-heal, confirming the stop is stop()'s job
        assert sender.recv() == b"slow"
        thread.join(timeout=1.0)
        assert not thread.is_alive()
        assert engine._state == EngineState.STOPPING

        assert engine.stop() == "engine stopped"
        assert engine._state == EngineState.STOPPED
    finally:
        sender.close()


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_unhandled_loop_exception_self_heals_state(settings):
    """A crashed loop thread must mark the engine STOPPED and close its sockets
    so start() can recover."""
    engine = CrashingEngine(settings=settings, processor=SimpleProcessor())
    engine.start()
    # the self-heal runs in the loop thread's finally, so join() is enough
    engine._thread.join(timeout=2.0)

    assert engine._state == EngineState.STOPPED
    with pytest.raises(pynng.NNGException):
        engine._pair_sock.send(b"socket should be closed")

    assert engine.start() == "engine started"
    engine._thread.join(timeout=2.0)
    engine.stop()


def test_unexpected_exit_yields_when_stop_holds_lock(settings):
    """If stop() holds _lifecycle_lock when the loop dies, the self-heal must
    give up after its bounded acquire and leave the transition to stop()."""
    engine = Engine(settings=settings, processor=SimpleProcessor())
    engine._state = EngineState.RUNNING

    with engine._lifecycle_lock:
        started = time.monotonic()
        engine._handle_unexpected_loop_exit()
        assert time.monotonic() - started >= 0.4
        assert engine._state == EngineState.RUNNING

    # no loop thread was started, so clean up by hand
    engine._state = EngineState.STOPPED
    engine._pair_sock.close()
