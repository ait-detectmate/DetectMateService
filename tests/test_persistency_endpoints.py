import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from service.features.web.router import router, get_service
from detectmatelibrary.utils.persistency import PersistencyLoadError

_STATUS_RESPONSE = {
    "path": "/state/detector",
    "save_interval_seconds": 300,
    "events_until_save": None,
    "auto_load": False,
    "events_seen_count": 3,
    "events_with_data_count": 2,
    "events_since_save": 42,
    "last_saved_at": None,
}


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def mock_saver():
    saver = MagicMock()
    saver.get_status.return_value = _STATUS_RESPONSE
    return saver


@pytest.fixture
def service_with_saver(mock_saver):
    svc = MagicMock()
    svc.library_component = MagicMock()
    svc.library_component.saver = mock_saver
    return svc


@pytest.fixture
def client(app, service_with_saver):
    app.dependency_overrides[get_service] = lambda: service_with_saver
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- /admin/persistency/save ----------

class TestPersistencySave:
    def test_save_ok(self, client, mock_saver):
        resp = client.post("/admin/persistency/save")
        assert resp.status_code == 200
        assert resp.json() == {"message": "state saved"}
        mock_saver.save.assert_called_once()

    def test_save_no_library_component(self, app):
        svc = MagicMock()
        svc.library_component = None
        app.dependency_overrides[get_service] = lambda: svc
        c = TestClient(app)
        resp = c.post("/admin/persistency/save")
        assert resp.status_code == 404
        assert "No library component" in resp.json()["detail"]
        app.dependency_overrides.clear()

    def test_save_no_saver(self, app):
        svc = MagicMock()
        svc.library_component = MagicMock(spec=[])  # saver attribute absent
        app.dependency_overrides[get_service] = lambda: svc
        c = TestClient(app)
        resp = c.post("/admin/persistency/save")
        assert resp.status_code == 404
        assert "Persistency not configured" in resp.json()["detail"]
        app.dependency_overrides.clear()


# ---------- /admin/persistency/load ----------

class TestPersistencyLoad:
    def test_load_ok(self, client, mock_saver):
        resp = client.post("/admin/persistency/load")
        assert resp.status_code == 200
        assert resp.json() == {"message": "state loaded"}
        mock_saver.load.assert_called_once()

    def test_load_no_saved_state(self, client, mock_saver):
        mock_saver.load.side_effect = PersistencyLoadError("metadata.json missing")
        resp = client.post("/admin/persistency/load")
        assert resp.status_code == 404
        assert "metadata.json missing" in resp.json()["detail"]

    def test_load_no_library_component(self, app):
        svc = MagicMock()
        svc.library_component = None
        app.dependency_overrides[get_service] = lambda: svc
        c = TestClient(app)
        resp = c.post("/admin/persistency/load")
        assert resp.status_code == 404
        app.dependency_overrides.clear()


# ---------- /admin/persistency/status ----------

class TestPersistencyStatus:
    def test_status_ok(self, client, mock_saver):
        resp = client.get("/admin/persistency/status")
        assert resp.status_code == 200
        assert resp.json() == _STATUS_RESPONSE
        mock_saver.get_status.assert_called_once()

    def test_status_no_library_component(self, app):
        svc = MagicMock()
        svc.library_component = None
        app.dependency_overrides[get_service] = lambda: svc
        c = TestClient(app)
        resp = c.get("/admin/persistency/status")
        assert resp.status_code == 404
        app.dependency_overrides.clear()
