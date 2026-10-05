import logging
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from service.client import DetectMateClient
from service.core import Service
from service.features.web.server import WebServer
from service.settings import ServiceSettings

API_KEY = "s3cret-test-key"


def make_client(api_key=None):
    service = MagicMock()
    service.settings = ServiceSettings(http_api_key=api_key)
    service.component_type, service.component_id, service.config_manager = "test", "test", None
    service._create_status_report.side_effect = (
        lambda running: Service._create_status_report(service, running)
    )
    return TestClient(WebServer(service).app), service


@pytest.mark.parametrize("configured_key,headers,expected", [
    (API_KEY, {"X-Auth-Token": API_KEY}, 200),
    (API_KEY, {}, 401),
    (API_KEY, {"X-Auth-Token": "wrong"}, 401),
    (None, {}, 200),
])
def test_admin_auth(configured_key, headers, expected):
    client, _ = make_client(configured_key)
    assert client.get("/admin/status", headers=headers).status_code == expected


def test_rejected_request_does_not_reach_service():
    client, svc = make_client(API_KEY)
    assert client.post("/admin/shutdown").status_code == 401
    svc.shutdown.assert_not_called()


@pytest.mark.parametrize("path", ["/metrics", "/openapi.json", "/docs", "/redoc"])
def test_public_routes_need_no_key(path):
    client, _ = make_client(API_KEY)
    assert client.get(path).status_code == 200


def test_status_does_not_leak_key():
    client, service = make_client(API_KEY)
    resp = client.get("/admin/status", headers={"X-Auth-Token": API_KEY})
    assert API_KEY not in resp.text
    # Service.status() json.dumps the report itself, without FastAPI's encoder
    report = Service.status(service)
    assert API_KEY not in report
    assert '"http_api_key": "**********"' in report


@pytest.mark.parametrize("env_value,expected", [(API_KEY, API_KEY), ("", None)])
def test_key_from_env(monkeypatch, env_value, expected):
    monkeypatch.setenv("DETECTMATE_HTTP_API_KEY", env_value)
    key = ServiceSettings.from_yaml(None).http_api_key
    assert (key.get_secret_value() if key else None) == expected


@pytest.mark.parametrize("api_key,warns", [(None, True), (API_KEY, False)])
def test_startup_warning(caplog, api_key, warns):
    svc = MagicMock(settings=ServiceSettings(http_api_key=api_key), log=logging.getLogger("auth-test"))
    with caplog.at_level(logging.WARNING, logger="auth-test"):
        Service._warn_if_admin_api_unauthenticated(svc)
    assert ("unauthenticated" in caplog.text) == warns


def test_client_sends_key():
    assert DetectMateClient("localhost:8000", api_key=API_KEY).session.headers["X-Auth-Token"] == API_KEY
    assert "X-Auth-Token" not in DetectMateClient("localhost:8000").session.headers
