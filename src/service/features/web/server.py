from __future__ import annotations
import threading
from typing import TYPE_CHECKING
import uvicorn
from fastapi import FastAPI, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from service.features.web.router import router, get_service


if TYPE_CHECKING:
    from service.core.service import Service


class WebServer(threading.Thread):
    # Wraps a FastAPI web server in a thread
    def __init__(self, service: Service) -> None:
        super().__init__(name="WebServerThread", daemon=True)
        self.service = service
        self.app = FastAPI(title=f"DetectMate Admin - {service.component_id}")

        # Prometheus metrics endpoint
        @self.app.get("/metrics")  # type: ignore[misc]
        def metrics() -> Response:
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST
            )

        # Inject service instance into the router
        self.app.include_router(router)
        self.app.dependency_overrides[get_service] = lambda: self.service

        self.config = uvicorn.Config(
            app=self.app,
            host=service.settings.http_host,
            port=service.settings.http_port,
            log_level="info",
        )
        self.server = uvicorn.Server(self.config)
        self.server.install_signal_handlers = False  # Important for running in thread,
        # pythons signal module only allows the Main Thread to register signal handlers
        # uvicorns default behaviour to listen for shutdown signals will raise ValueError

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True
