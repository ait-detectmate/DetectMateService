import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from service.features.web.router import router, get_service


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def mock_component():
    component = MagicMock()
    component.get_state.return_value = "Training."
    return component


@pytest.fixture
def service_with_component(mock_component):
    svc = MagicMock()
    svc.library_component = mock_component
    return svc


@pytest.fixture
def client(app, service_with_component):
    app.dependency_overrides[get_service] = lambda: service_with_component
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def no_component_client(app):
    svc = MagicMock()
    svc.library_component = None
    app.dependency_overrides[get_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- POST /admin/training/state ----------

class TestTrainingSetState:
    @pytest.mark.parametrize("state", [
        "keep_training", "stop_training", "keep_configuring", "stop_configuring"
    ])
    def test_valid_states_accepted(self, client, mock_component, state):
        resp = client.post("/admin/training/state", json={"state": state})
        assert resp.status_code == 200
        assert resp.json() == {"message": f"state updated to: {state}"}
        mock_component.update_state.assert_called_once_with(state)

    def test_invalid_state_rejected(self, client):
        resp = client.post("/admin/training/state", json={"state": "invalid_state"})
        assert resp.status_code == 422

    def test_missing_state_field_rejected(self, client):
        resp = client.post("/admin/training/state", json={})
        assert resp.status_code == 422

    def test_no_library_component(self, no_component_client):
        resp = no_component_client.post("/admin/training/state", json={"state": "stop_training"})
        assert resp.status_code == 404
        assert "No library component" in resp.json()["detail"]


# ---------- GET /admin/training/state ----------

class TestTrainingGetState:
    def test_returns_current_state(self, client, mock_component):
        resp = client.get("/admin/training/state")
        assert resp.status_code == 200
        assert resp.json() == {"state": "Training."}
        mock_component.get_state.assert_called_once()

    def test_reflects_updated_state(self, client, mock_component):
        mock_component.get_state.return_value = "Default"
        resp = client.get("/admin/training/state")
        assert resp.status_code == 200
        assert resp.json()["state"] == "Default"

    def test_no_library_component(self, no_component_client):
        resp = no_component_client.get("/admin/training/state")
        assert resp.status_code == 404
        assert "No library component" in resp.json()["detail"]
