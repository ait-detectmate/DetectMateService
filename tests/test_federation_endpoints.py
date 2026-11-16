import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from detectmatelibrary.common._core_op._fed_component import FedOperations

from service.features.engine import EngineState
from service.features.federation import FederationState
from service.features.web.auth import require_api_key
from service.features.web.router import router, get_service


@pytest.fixture
def service():
    svc = MagicMock()
    svc._state = EngineState.STOPPED
    svc.federation = FederationState()
    component = svc.library_component
    component.name = "NewValueDetector"
    component.config.allow_fed = True
    component.to_binary.return_value = b"local"
    component.aggregate.return_value = b"global"
    return svc


@pytest.fixture
def client(service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: None  # auth is covered in test_api_auth.py
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


def _files(*blobs):
    return [("files", (f"peer{i}.bin", blob)) for i, blob in enumerate(blobs)]


# (method, path, request kwargs) for every endpoint that changes or exports federation state
GUARDED = [
    ("get", "/api/v1/federation/export", {}),
    ("post", "/api/v1/federation/stack", {"files": _files(b"peer")}),
    ("post", "/api/v1/federation/aggregate", {}),
    ("post", "/api/v1/federation/adopt", {"files": {"file": ("global.bin", b"global")}}),
    ("post", "/api/v1/federation/finalize", {}),
]


class TestGuards:
    @pytest.mark.parametrize("method,path,kwargs", GUARDED)
    def test_no_component(self, client, service, method, path, kwargs):
        service.library_component = None
        assert client.request(method, path, **kwargs).status_code == 404

    @pytest.mark.parametrize("method,path,kwargs", GUARDED)
    def test_federation_disabled(self, client, service, method, path, kwargs):
        service.library_component.config.allow_fed = False
        resp = client.request(method, path, **kwargs)
        assert resp.status_code == 409
        assert "allow_fed" in resp.json()["detail"]

    @pytest.mark.parametrize("state", [EngineState.RUNNING, EngineState.STOPPING])
    @pytest.mark.parametrize("method,path,kwargs", GUARDED)
    def test_engine_not_stopped(self, client, service, method, path, kwargs, state):
        service._state = state
        resp = client.request(method, path, **kwargs)
        assert resp.status_code == 409
        assert "/api/v1/stop" in resp.json()["detail"]

    @pytest.mark.parametrize("method,path,kwargs", GUARDED)
    def test_finalized(self, client, service, method, path, kwargs):
        service.federation.finalized = True
        resp = client.request(method, path, **kwargs)
        assert resp.status_code == 409
        assert "finalized" in resp.json()["detail"]


class TestStatus:
    def test_reports_state(self, client, service):
        service.federation.stacked_peers = 2
        assert client.get("/api/v1/federation/status").json() == {
            "enabled": True,
            "stacked_peers": 2,
            "rounds_aggregated": 0,
            "last_aggregated_at": None,
            "finalized": False,
        }

    def test_disabled_is_reported_not_rejected(self, client, service):
        service.library_component.config.allow_fed = False
        resp = client.get("/api/v1/federation/status")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


class TestExport:
    def test_returns_binary(self, client):
        resp = client.get("/api/v1/federation/export")
        assert resp.status_code == 200
        assert resp.content == b"local"
        assert resp.headers["content-type"] == "application/octet-stream"
        assert "NewValueDetector_federation.bin" in resp.headers["content-disposition"]

    def test_unsupported_component(self, client, service):
        service.library_component.to_binary.return_value = b""
        assert client.get("/api/v1/federation/export").status_code == 409


class TestStack:
    def test_stacks_all_files(self, client, service):
        resp = client.post("/api/v1/federation/stack", files=_files(b"a", b"b"))
        assert resp.status_code == 200
        assert resp.json()["stacked_peers"] == 2
        service.library_component.stack.assert_called_once_with([b"a", b"b"])

    def test_counts_accumulate(self, client):
        client.post("/api/v1/federation/stack", files=_files(b"a"))
        assert client.post("/api/v1/federation/stack", files=_files(b"b")).json()["stacked_peers"] == 2

    def test_empty_file(self, client, service):
        assert client.post("/api/v1/federation/stack", files=_files(b"a", b"")).status_code == 422
        service.library_component.stack.assert_not_called()

    def test_invalid_binary(self, client, service):
        service.library_component.stack.side_effect = ValueError("bad frame")
        resp = client.post("/api/v1/federation/stack", files=_files(b"junk"))
        assert resp.status_code == 422
        assert "bad frame" in resp.json()["detail"]
        assert service.federation.stacked_peers == 0


class TestAggregate:
    def test_returns_global_binary_and_unstacks(self, client, service):
        service.federation.stacked_peers = 3
        resp = client.post("/api/v1/federation/aggregate")
        assert resp.status_code == 200
        assert resp.content == b"global"
        service.library_component.aggregate.assert_called_once_with(unstack=True)
        assert service.federation.stacked_peers == 0
        assert service.federation.rounds_aggregated == 1
        assert service.federation.last_aggregated_at is not None

    def test_keep_stack(self, client, service):
        service.federation.stacked_peers = 3
        client.post("/api/v1/federation/aggregate", params={"unstack": "false"})
        service.library_component.aggregate.assert_called_once_with(unstack=False)
        assert service.federation.stacked_peers == 3

    def test_nothing_stacked(self, client, service):
        assert client.post("/api/v1/federation/aggregate").status_code == 409
        service.library_component.aggregate.assert_not_called()


class TestAdopt:
    def test_loads_binary(self, client, service):
        resp = client.post("/api/v1/federation/adopt", files={"file": ("global.bin", b"global")})
        assert resp.status_code == 200
        service.library_component.load_binary.assert_called_once_with(b"global")

    def test_empty_file(self, client, service):
        assert client.post("/api/v1/federation/adopt", files={"file": ("global.bin", b"")}).status_code == 422
        service.library_component.load_binary.assert_not_called()

    def test_invalid_binary(self, client, service):
        service.library_component.load_binary.side_effect = ValueError("bad frame")
        resp = client.post("/api/v1/federation/adopt", files={"file": ("global.bin", b"junk")})
        assert resp.status_code == 422
        assert "bad frame" in resp.json()["detail"]

    def test_library_stub_is_not_supported(self, client, service):
        # The library's base load_binary() only warns; adopting through it would silently do nothing.
        component = service.library_component
        component.load_binary = FedOperations.load_binary.__get__(component)
        resp = client.post("/api/v1/federation/adopt", files={"file": ("global.bin", b"global")})
        assert resp.status_code == 501
        assert "/api/v1/persistency/export" in resp.json()["detail"]


class TestFinalize:
    def test_finalize_is_terminal(self, client, service):
        assert client.post("/api/v1/federation/finalize").status_code == 200
        service.library_component.finalize_federation.assert_called_once()
        assert client.get("/api/v1/federation/status").json()["finalized"] is True
        assert client.get("/api/v1/federation/export").status_code == 409
