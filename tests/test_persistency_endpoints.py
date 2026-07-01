import io
import zipfile

import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from service.features.web.router import router, get_service
from detectmatelibrary.utils.persistency import PersistencyLoadError


def _make_zip(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


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
    svc._running = False
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

    def test_load_rejected_when_engine_running(self, app):
        svc = MagicMock()
        svc._running = True
        app.dependency_overrides[get_service] = lambda: svc
        c = TestClient(app)
        resp = c.post("/admin/persistency/load")
        assert resp.status_code == 409
        assert "/admin/stop" in resp.json()["detail"]
        app.dependency_overrides.clear()

    def test_load_no_library_component(self, app):
        svc = MagicMock()
        svc._running = False
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


# ---------- /admin/persistency/export ----------

class TestPersistencyExport:
    def test_export_ok(self, client, service_with_saver):
        service_with_saver.library_component.export_state.return_value = b"fake zip bytes"
        service_with_saver.library_component.name = "MyDetector"
        resp = client.get("/admin/persistency/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert 'filename="MyDetector_state.zip"' in resp.headers["content-disposition"]
        assert resp.content == b"fake zip bytes"

    def test_export_no_persistency_configured(self, client, service_with_saver):
        service_with_saver.library_component.export_state.return_value = None
        resp = client.get("/admin/persistency/export")
        assert resp.status_code == 404
        assert "Persistency not configured" in resp.json()["detail"]

    def test_export_no_library_component(self, app):
        svc = MagicMock()
        svc.library_component = None
        app.dependency_overrides[get_service] = lambda: svc
        c = TestClient(app)
        resp = c.get("/admin/persistency/export")
        assert resp.status_code == 404
        app.dependency_overrides.clear()


# ---------- /admin/persistency/import ----------

class TestPersistencyImport:
    def test_import_ok(self, client, service_with_saver):
        data = _make_zip({"metadata.json": b"{}", "events/1.msgpack": b"x"})
        resp = client.post("/admin/persistency/import",
                           files={"file": ("state.zip", data, "application/zip")})
        assert resp.status_code == 200
        assert resp.json() == {"message": "state imported"}
        service_with_saver.library_component.import_state.assert_called_once_with(data)

    def test_import_ok_with_leading_slash_metadata(self, client, service_with_saver):
        # Guards against archives produced by library versions with the
        # leading-slash zip-entry bug (fsspec MemoryFileSystem path handling).
        data = _make_zip({"/metadata.json": b"{}", "/events/1.msgpack": b"x"})
        resp = client.post("/admin/persistency/import",
                           files={"file": ("state.zip", data, "application/zip")})
        assert resp.status_code == 200
        service_with_saver.library_component.import_state.assert_called_once_with(data)

    def test_import_invalid_zip(self, client):
        resp = client.post(
            "/admin/persistency/import", files={"file": ("state.zip", b"not a zip", "application/zip")}
        )
        assert resp.status_code == 422
        assert "not a valid zip archive" in resp.json()["detail"]

    def test_import_missing_metadata(self, client):
        data = _make_zip({"events/1.msgpack": b"x"})
        resp = client.post("/admin/persistency/import",
                           files={"file": ("state.zip", data, "application/zip")})
        assert resp.status_code == 422
        assert "metadata.json not found" in resp.json()["detail"]

    def test_import_load_error(self, client, service_with_saver):
        service_with_saver.library_component.import_state.side_effect = PersistencyLoadError("bad state")
        data = _make_zip({"metadata.json": b"{}"})
        resp = client.post("/admin/persistency/import",
                           files={"file": ("state.zip", data, "application/zip")})
        assert resp.status_code == 422
        assert "bad state" in resp.json()["detail"]

    def test_import_rejected_when_engine_running(self, app):
        svc = MagicMock()
        svc._running = True
        app.dependency_overrides[get_service] = lambda: svc
        c = TestClient(app)
        data = _make_zip({"metadata.json": b"{}"})
        resp = c.post("/admin/persistency/import", files={"file": ("state.zip", data, "application/zip")})
        assert resp.status_code == 409
        assert "/admin/stop" in resp.json()["detail"]
        app.dependency_overrides.clear()

    def test_import_no_library_component(self, app):
        svc = MagicMock()
        svc._running = False
        svc.library_component = None
        app.dependency_overrides[get_service] = lambda: svc
        c = TestClient(app)
        data = _make_zip({"metadata.json": b"{}"})
        resp = c.post("/admin/persistency/import", files={"file": ("state.zip", data, "application/zip")})
        assert resp.status_code == 404
        app.dependency_overrides.clear()
