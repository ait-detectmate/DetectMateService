from typing import Dict, Any
import pytest
import yaml
import socket
import threading
from unittest.mock import Mock, patch
from pydantic import BaseModel, Field

from service.core import Service
from service.settings import ServiceSettings
from service.features.config_manager import ConfigManager
from detectmatelibrary.common.core import CoreConfig


class MockConfig(BaseModel):  # Your component's specific params
    threshold: float = Field(default=0.5)


class MockDetectorEntry(BaseModel):
    method_type: str = "random_detector"
    params: Dict[str, Any]


class ServiceConfigWrapper(CoreConfig):
    """Matches the actual YAML structure."""
    detectors: Dict[str, MockDetectorEntry]


class MockService(Service):
    """Service implementation that uses MockConfig."""

    def get_config_schema(self):
        return MockConfig

    def process(self, raw_message: bytes) -> bytes | None:
        return raw_message


@pytest.fixture
def free_port():
    """Find a free port on the system."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
def temp_params_file(tmp_path):
    """Create a temporary YAML file with nested structure."""
    params_path = tmp_path / "test_params.yaml"
    initial_data = {
        "detectors": {
            "RandomDetector": {
                "method_type": "random_detector",
                "auto_config": False,
                "params": {
                    "log_variables": [
                        {
                            "id": "test",
                            "event": 1,
                            "template": "dummy_template",
                            "variables": [
                                {
                                    "pos": 0,
                                    "name": "var1",
                                    "params": {"threshold": 0.7}
                                }
                            ],
                            "header_variables": []
                        }
                    ]
                }
            }
        }
    }
    params_path.write_text(yaml.dump(initial_data))
    return params_path


@pytest.fixture
def test_service_mocked(temp_params_file, free_port):
    """Create a mocked service instance.

    We bypass __init__ to avoid starting real network sockets, but
    manually inject the pieces the Service needs.
    """
    settings = ServiceSettings(
        http_port=free_port,
        engine_addr="inproc://test_engine",
        config_file=temp_params_file,
        engine_autostart=False
    )

    with patch.object(Service, '__init__', lambda self, settings: None):
        service = MockService(settings)
        service.settings = settings
        service.component_id = "test_id"
        service.component_type = "core"
        service.log = Mock()

        # Necessary for shutdown() and context manager cleanup
        service._service_exit_event = threading.Event()
        service.web_server = Mock()

        # Initialize real ConfigManager so we can test logic
        service.config_manager = ConfigManager(
            str(temp_params_file),
            MockConfig,
            service.log
        )
        yield service


def test_reconfigure_deep_structure(test_service_mocked):
    nested_config = {
        "detectors": {
            "RandomDetector": {
                "params": {
                    "log_variables": [{"variables": [{"params": {"threshold": 0.8}}]}]
                }
            }
        }
    }
    result = test_service_mocked.reconfigure(config_data=nested_config)
    # assert here if threshold got reconfigured in memory
    current_config = test_service_mocked.config_manager.get()
    updated_threshold = (
        current_config.detectors
        ["RandomDetector"]
        ["params"]
        ["log_variables"][0]
        ["variables"][0]
        ["params"]
        ["threshold"])
    assert updated_threshold == 0.8
    assert result == "reconfigure: ok"


def test_reconfigure_with_persist(test_service_mocked, temp_params_file):
    """Test that persist=True actually writes the new values to the YAML
    file."""
    nested_config = {
        "detectors": {
            "RandomDetector": {
                "params": {
                    "log_variables": [{"variables": [{"params": {"threshold": 0.1}}]}]
                }
            }
        }
    }

    # Act
    result = test_service_mocked.reconfigure(config_data=nested_config, persist=True)

    # Assert
    assert result == "reconfigure: ok"

    # Verify file content
    with open(temp_params_file, 'r') as f:
        disk_data = yaml.safe_load(f)
    threshold_on_disk = (
        disk_data['detectors']
        ['RandomDetector']
        ['params']
        ['log_variables'][0]
        ['variables'][0]
        ['params']
        ['threshold'])
    assert threshold_on_disk == 0.1


def test_reconfigure_no_config_manager():
    """Test error handling when the service has no config_file/manager
    initialized."""
    settings = ServiceSettings(config_file=None)

    # We use a real init here but avoid the sockets by just testing the method
    with patch.object(Service, '__init__', lambda self, settings: None):
        service = MockService(settings)
        service.config_manager = None

        result = service.reconfigure(config_data={'a': 1})
        assert "no config manager" in result


def test_reconfigure_empty_payload(test_service_mocked):
    """Test that an empty dictionary is handled as a no-op."""
    result = test_service_mocked.reconfigure(config_data={})
    assert "no-op" in result
