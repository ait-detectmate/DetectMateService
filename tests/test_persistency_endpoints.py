import json
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from service.features.web.router import router, get_service
from detectmatelibrary.utils.persistency import PersistencyLoadError


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def mock_saver():
    saver = MagicMock()
    saver._config.path = "/state/detector"
    saver._config.save_interval_seconds = 300
    saver._config.events_until_save = None
    saver._config.auto_load = False
    saver._root = "/state/detector"
    saver._fs = MagicMock()
    saver._fs.exists.return_value = False
    saver._persistency = MagicMock()
    saver._persistency.get_events_seen.return_value = {1, 2, 3}
    saver._persistency.get_events_data.return_value = {1: MagicMock(), 2: MagicMock()}
    saver._persistency._events_since_save = 42
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
    def test_status_ok(self, client):
        resp = client.get("/admin/persistency/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == "/state/detector"
        assert body["save_interval_seconds"] == 300
        assert body["events_until_save"] is None
        assert body["auto_load"] is False
        assert body["events_seen_count"] == 3
        assert body["events_with_data_count"] == 2
        assert body["events_since_save"] == 42
        assert body["last_saved_at"] is None

    def test_status_includes_last_saved_at(self, client, mock_saver):
        import io
        mock_saver._fs.exists.return_value = True
        mock_saver._fs.open.return_value.__enter__.return_value = io.StringIO(
            json.dumps({"saved_at": "2026-06-16T12:00:00+00:00"})
        )

        resp = client.get("/admin/persistency/status")
        assert resp.status_code == 200
        assert resp.json()["last_saved_at"] == "2026-06-16T12:00:00+00:00"

    def test_status_metadata_read_error_is_tolerated(self, client, mock_saver):
        mock_saver._fs.exists.return_value = True
        mock_saver._fs.open.side_effect = OSError("disk error")
        resp = client.get("/admin/persistency/status")
        # should still return 200 with last_saved_at=None
        assert resp.status_code == 200
        assert resp.json()["last_saved_at"] is None

    def test_status_no_library_component(self, app):
        svc = MagicMock()
        svc.library_component = None
        app.dependency_overrides[get_service] = lambda: svc
        c = TestClient(app)
        resp = c.get("/admin/persistency/status")
        assert resp.status_code == 404
        app.dependency_overrides.clear()
