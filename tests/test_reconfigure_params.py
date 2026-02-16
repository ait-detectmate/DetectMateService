import pytest
import yaml
import socket
import threading
from unittest.mock import Mock, patch

from service.core import Service
from service.settings import ServiceSettings
from service.features.config_manager import ConfigManager
from detectmatelibrary.common.detector import CoreDetectorConfig


class MockService(Service):
    """Service implementation for testing."""

    def get_config_schema(self):
        return CoreDetectorConfig

    def process(self, raw_message: bytes) -> bytes | None:
        return raw_message


@pytest.fixture
def free_port():
    """Find a free port on the system."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary YAML file with config data."""
    config_path = tmp_path / "test_config.yaml"
    initial_data = {
        "detectors": {
            "TestDetector": {
                "method_type": "new_value_detector",
                "auto_config": False,
                "events": {
                    1: {
                        "default": {
                            "params": {},
                            "variables": [
                                {"pos": 0, "name": "var_0"}
                            ]
                        }
                    }
                }
            }
        }
    }
    config_path.write_text(yaml.dump(initial_data, sort_keys=False))
    return config_path


@pytest.fixture
def test_service(temp_config_file, free_port):
    """Create a mocked service instance."""
    settings = ServiceSettings(
        http_port=free_port,
        engine_addr="inproc://test_engine",
        config_file=temp_config_file,
        engine_autostart=False
    )

    with patch.object(Service, '__init__', lambda self, settings: None):
        service = MockService(settings)
        service.settings = settings
        service.component_id = "test_id"
        service.component_type = "core"
        service.log = Mock()
        service._service_exit_event = threading.Event()
        service.web_server = Mock()

        service.config_manager = ConfigManager(
            str(temp_config_file),
            CoreDetectorConfig,
            service.log
        )
        yield service


def test_reconfigure_updates_events(test_service):
    """Test that reconfigure updates event configuration in memory."""
    new_config = {
        "detectors": {
            "TestDetector": {
                "method_type": "new_value_detector",
                "events": {
                    1: {
                        "default": {
                            "params": {},
                            "variables": [
                                {"pos": 0, "name": "var_0"},
                                {"pos": 1, "name": "var_1"}
                            ]
                        }
                    }
                }
            }
        }
    }

    result = test_service.reconfigure(config_data=new_config)

    assert result == "reconfigure: ok"
    current_config = test_service.config_manager.get()
    detector = current_config.detectors["TestDetector"]
    assert len(detector["events"][1]["default"]["variables"]) == 2


def test_reconfigure_persist_no_defaults(test_service, temp_config_file):
    """Test that persist=True writes clean YAML without defaults."""
    new_config = {
        "detectors": {
            "TestDetector": {
                "method_type": "new_value_detector",
                "events": {
                    2: {
                        "default": {
                            "params": {},
                            "variables": [
                                {"pos": 0, "name": "username"}
                            ]
                        }
                    }
                }
            }
        }
    }

    result = test_service.reconfigure(config_data=new_config, persist=True)
    assert result == "reconfigure: ok"

    with open(temp_config_file, 'r') as f:
        disk_data = yaml.safe_load(f)

    # Verify structure exists
    assert 2 in disk_data["detectors"]["TestDetector"]["events"]

    # Verify NO unwanted defaults (parser, start_id, etc.)
    detector_config = disk_data["detectors"]["TestDetector"]
    assert "parser" not in detector_config
    assert "start_id" not in detector_config
    assert "comp_type" not in detector_config  # Should be stripped


def test_reconfigure_multiple_instances(test_service, temp_config_file):
    """Test reconfigure with multiple event instances."""
    new_config = {
        "detectors": {
            "TestDetector": {
                "method_type": "new_value_combo_detector",
                "events": {
                    1: {
                        "instance_1": {
                            "params": {},
                            "variables": [{"pos": 0, "name": "var_0"}]
                        },
                        "instance_2": {
                            "params": {},
                            "variables": [{"pos": 1, "name": "var_1"}]
                        }
                    }
                }
            }
        }
    }

    result = test_service.reconfigure(config_data=new_config, persist=True)
    assert result == "reconfigure: ok"

    with open(temp_config_file, 'r') as f:
        disk_data = yaml.safe_load(f)

    event_instances = disk_data["detectors"]["TestDetector"]["events"][1]
    assert "instance_1" in event_instances
    assert "instance_2" in event_instances
    assert len(event_instances) == 2


def test_reconfigure_header_variables(test_service, temp_config_file):
    """Test reconfigure with header variables."""
    new_config = {
        "detectors": {
            "TestDetector": {
                "method_type": "new_value_detector",
                "events": {
                    1: {
                        "default": {
                            "params": {},
                            "variables": [
                                {"pos": 0, "name": "var_0"}
                            ],
                            "header_variables": [
                                {"pos": "username", "params": {}}
                            ]
                        }
                    }
                }
            }
        }
    }

    result = test_service.reconfigure(config_data=new_config, persist=True)
    assert result == "reconfigure: ok"

    with open(temp_config_file, 'r') as f:
        disk_data = yaml.safe_load(f)

    instance = disk_data["detectors"]["TestDetector"]["events"][1]["default"]
    assert "header_variables" in instance
    assert instance["header_variables"][0]["pos"] == "username"

    result = test_service.reconfigure(config_data=new_config, persist=True)
    assert result == "reconfigure: ok"

    with open(temp_config_file, 'r') as f:
        disk_data = yaml.safe_load(f)

    events = disk_data["detectors"]["TestDetector"]["events"]
    assert 1 in events


def test_reconfigure_no_config_manager():
    """Test error handling when no config manager exists."""
    settings = ServiceSettings(config_file=None)

    with patch.object(Service, '__init__', lambda self, settings: None):
        service = MockService(settings)
        service.config_manager = None

        result = service.reconfigure(config_data={'a': 1})
        assert "no config manager" in result


def test_reconfigure_empty_payload(test_service):
    """Test that empty config data is handled as no-op."""
    result = test_service.reconfigure(config_data={})
    assert "no-op" in result


def test_reconfigure_persist_false(test_service, temp_config_file):
    """Test that persist=False updates memory but not disk."""
    original_content = temp_config_file.read_text()

    new_config = {
        "detectors": {
            "TestDetector": {
                "method_type": "new_value_detector",
                "events": {
                    99: {
                        "default": {
                            "params": {},
                            "variables": [{"pos": 0, "name": "new_var"}]
                        }
                    }
                }
            }
        }
    }

    result = test_service.reconfigure(config_data=new_config, persist=False)
    assert result == "reconfigure: ok"

    # Memory updated
    current_config = test_service.config_manager.get()
    assert 99 in current_config.detectors["TestDetector"]["events"]

    # Disk unchanged
    assert temp_config_file.read_text() == original_content


def test_reconfigure_with_params(test_service, temp_config_file):
    """Test reconfigure with instance params."""
    new_config = {
        "detectors": {
            "TestDetector": {
                "method_type": "new_value_detector",
                "events": {
                    1: {
                        "default": {
                            "params": {"threshold": 0.7, "window_size": 100},
                            "variables": [{"pos": 0, "name": "var_0"}]
                        }
                    }
                }
            }
        }
    }

    result = test_service.reconfigure(config_data=new_config, persist=True)
    assert result == "reconfigure: ok"

    with open(temp_config_file, 'r') as f:
        disk_data = yaml.safe_load(f)

    params = disk_data["detectors"]["TestDetector"]["events"][1]["default"]["params"]
    assert params["threshold"] == 0.7
    assert params["window_size"] == 100


def test_reconfigure_empty_events(test_service, temp_config_file):
    """Test reconfigure with empty events dict."""
    new_config = {
        "detectors": {
            "TestDetector": {
                "method_type": "new_value_detector",
                "events": {}
            }
        }
    }

    result = test_service.reconfigure(config_data=new_config, persist=True)
    assert result == "reconfigure: ok"

    with open(temp_config_file, 'r') as f:
        disk_data = yaml.safe_load(f)

    # Should handle empty events gracefully
    assert disk_data["detectors"]["TestDetector"]["events"] == {}
