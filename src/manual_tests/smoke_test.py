import time
from service.settings import ServiceSettings
from service.core import Service


class SmokeComponent(Service):
    def __init__(self, settings: ServiceSettings | None = None):
        settings = settings or ServiceSettings(
            manager_addr="ipc:///tmp/smoke_cmd.ipc",
            engine_addr="ipc:///tmp/smoke_engine.ipc",
            engine_autostart=True,
        )
        super().__init__(settings=settings)

    def setup_io(self) -> None:
        # no real I/O, just notify
        self.log.info("SmokeComponent ready to receive commands")

    def process(self, raw_message: bytes) -> bytes | None:
        # echo back whatever we get
        self.log.debug(f"[engine] got raw: {raw_message!r}")
        return raw_message

    def _handle_cmd(self, cmd: str) -> str:
        print(f"[manager] Received command: {cmd!r}")
        return super()._handle_cmd(cmd)


if __name__ == "__main__":
    comp = SmokeComponent()
    print(f"[smoke_test] manager listening on {comp.settings.manager_addr}")
    print(f"[smoke_test] engine  listening on {comp.settings.engine_addr}")
    try:
        comp.run()
    except KeyboardInterrupt:
        print("\n[smoke_test] KeyboardInterrupt, shutting down")
        comp.stop()
    time.sleep(0.1)
    print("[smoke_test] done.")
