import pytest
import tempfile
import yaml
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

from service.cli import reconfigure_service
from service.core import Service
from service.settings import ServiceSettings
from service.features.config import BaseConfig
from pydantic import Field


# Test configs schema
class MockConfig(BaseConfig):
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    enabled: bool = Field(default=True)


# Test service that uses our test configs
class MockService(Service):
    def get_config_schema(self):
        return MockConfig

    def process(self, raw_message: bytes) -> bytes | None:
        return raw_message


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_data = {
            'config_file': str(Path(f.name).with_suffix('.params.yaml')),
            'engine_autostart': False
        }
        yaml.dump(config_data, f)
    yield f.name
    # Clean up
    if os.path.exists(f.name):
        os.unlink(f.name)


@pytest.fixture
def temp_params_file():
    """Create a temporary configs file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.params.yaml', delete=False) as f:
        params_data = {
            'threshold': 0.7,
            'enabled': False
        }
        yaml.dump(params_data, f)
    yield f.name
    # Clean up
    if os.path.exists(f.name):
        os.unlink(f.name)


@pytest.fixture
def test_service_mocked(temp_params_file):
    """Create a mocked test service instance for unit testing."""
    from service.settings import ServiceSettings

    # Create settings with the temp configs file
    settings = ServiceSettings(
        manager_addr="inproc://test_manager",
        engine_addr="inproc://test_engine",
        config_file=Path(temp_params_file),
        engine_autostart=False
    )

    # Mock the Manager and Engine initialization to avoid socket issues
    with patch.object(Service, '__init__', lambda self, settings: None):
        service = MockService(settings)
        service.settings = settings
        service.component_id = "test_id"
        service._stop_event = Mock()
        service.log = Mock()

        # Initialize config manager
        from service.features.config_manager import ConfigManager
        service.config_manager = ConfigManager(
            temp_params_file,
            MockConfig,
            service.log
        )

        yield service


def test_reconfigure_command_valid(temp_config_file, temp_params_file):
    """Test reconfigure command with valid configs."""
    # Update the config file to point to the params file
    with open(temp_config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    config_data['config_file'] = temp_params_file
    with open(temp_config_file, 'w') as f:
        yaml.dump(config_data, f)

    settings = ServiceSettings.from_yaml(temp_config_file)

    # Use context manager to ensure proper cleanup
    with MockService(settings=settings) as service:
        # Test valid reconfigure
        new_configs = {'threshold': 0.8, 'enabled': True}
        cmd = f'reconfigure {json.dumps(new_configs)}'
        result = service._handle_cmd(cmd)

        assert result == "reconfigure: ok"
        assert service.config_manager.get().threshold == 0.8
        assert service.config_manager.get().enabled is True


def test_reconfigure_command_invalid_json(temp_config_file, temp_params_file):
    """Test reconfigure command with invalid JSON."""
    # Update the config file to point to the params file
    with open(temp_config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    config_data['config_file'] = temp_params_file
    with open(temp_config_file, 'w') as f:
        yaml.dump(config_data, f)

    settings = ServiceSettings.from_yaml(temp_config_file)

    with MockService(settings=settings) as service:
        # Test invalid JSON
        result = service._handle_cmd('reconfigure invalid{json')
        assert "invalid JSON" in result


def test_reconfigure_command_validation_error(temp_config_file, temp_params_file):
    """Test reconfigure command with invalid config values."""
    # Update the config file to point to the params file
    with open(temp_config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    config_data['config_file'] = temp_params_file
    with open(temp_config_file, 'w') as f:
        yaml.dump(config_data, f)

    settings = ServiceSettings.from_yaml(temp_config_file)

    with MockService(settings=settings) as service:
        # Test invalid config value (threshold out of range)
        invalid_params = {'threshold': 2.0, 'enabled': True}
        cmd = f'reconfigure {json.dumps(invalid_params)}'
        result = service._handle_cmd(cmd)

        assert "error" in result.lower()
        # Should preserve original values
        assert service.config_manager.get().threshold == 0.7


def test_reconfigure_command_no_config_manager():
    """Test reconfigure command when no config manager is configured."""
    settings = ServiceSettings(engine_autostart=False)  # No config file

    with MockService(settings=settings) as service:
        result = service._handle_cmd('reconfigure {"threshold": 0.8}')
        assert "no config manager" in result


def test_reconfigure_command_no_payload(temp_config_file, temp_params_file):
    """Test reconfigure command with no payload."""
    # Update the config file to point to the params file
    with open(temp_config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    config_data['config_file'] = temp_params_file
    with open(temp_config_file, 'w') as f:
        yaml.dump(config_data, f)

    settings = ServiceSettings.from_yaml(temp_config_file)

    with MockService(settings=settings) as service:
        result = service._handle_cmd('reconfigure')
        assert "no payload" in result


# Tests with the persist functionality
def test_reconfigure_without_persist(test_service_mocked, temp_params_file):
    """Test reconfigure without persist flag - should update in memory but not save to file."""
    # Read original file content
    with open(temp_params_file, 'r') as f:
        original_content = yaml.safe_load(f)

    # New configs to test
    new_configs = {
        'threshold': 0.8,
        'enabled': True
    }

    # Call reconfigure without persist
    cmd = f'reconfigure {json.dumps(new_configs)}'
    result = test_service_mocked.reconfigure(cmd)

    # Should succeed
    assert result == "reconfigure: ok"

    # configs should be updated in memory
    current_params = test_service_mocked.config_manager.get()
    assert current_params.threshold == 0.8
    assert current_params.enabled is True

    # File should not be changed (no persist)
    with open(temp_params_file, 'r') as f:
        file_content = yaml.safe_load(f)
    assert file_content == original_content


def test_reconfigure_with_persist(test_service_mocked, temp_params_file):
    """Test reconfigure with persist flag - should update both in memory and in file."""
    # New configs to test
    new_configs = {
        'threshold': 0.8,
        'enabled': True
    }

    # Call reconfigure with persist
    cmd = f'reconfigure persist {json.dumps(new_configs)}'
    result = test_service_mocked.reconfigure(cmd)

    # Should succeed
    assert result == "reconfigure: ok"

    # configs should be updated in memory
    current_params = test_service_mocked.config_manager.get()
    assert current_params.threshold == 0.8
    assert current_params.enabled is True

    # File should be updated (with persist)
    with open(temp_params_file, 'r') as f:
        file_content = yaml.safe_load(f)
    assert file_content == new_configs


def test_cli_reconfigure_with_persist(temp_params_file):
    """Test CLI reconfigure command with persist flag."""
    # Create a temporary settings file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({
            'manager_addr': 'inproc://test_manager',
            'config_file': temp_params_file
        }, f)
        settings_path = f.name

    # Create a temporary new configs file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        new_configs = {
            'threshold': 0.9,
            'enabled': False
        }
        yaml.dump(new_configs, f)
        new_configs_path = f.name

    try:
        # Mock the pynng request to avoid actual socket communication
        with patch('pynng.Req0') as mock_req:
            mock_socket = Mock()
            mock_req.return_value.__enter__.return_value = mock_socket
            mock_socket.recv.return_value = b"reconfigure: ok"

            # Call reconfigure with persist
            reconfigure_service(Path(settings_path), Path(new_configs_path), persist=True)

            # Verify the request was sent with "persist" flag
            call_args = mock_socket.send.call_args[0][0]
            assert b"persist" in call_args
            assert b'"threshold": 0.9' in call_args

    finally:
        # Clean up
        for path in [settings_path, new_configs_path]:
            if os.path.exists(path):
                os.unlink(path)


def test_cli_reconfigure_without_persist(temp_params_file):
    """Test CLI reconfigure command without persist flag."""
    # Create a temporary settings file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({
            'manager_addr': 'inproc://test_manager',
            'config_file': temp_params_file
        }, f)
        settings_path = f.name

    # Create a temporary new configs file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        new_configs = {
            'threshold': 0.9,
            'enabled': False
        }
        yaml.dump(new_configs, f)
        new_configs_path = f.name

    try:
        # Mock the pynng request to avoid actual socket communication
        with patch('pynng.Req0') as mock_req:
            mock_socket = Mock()
            mock_req.return_value.__enter__.return_value = mock_socket
            mock_socket.recv.return_value = b"reconfigure: ok"

            # Call reconfigure without persist
            reconfigure_service(Path(settings_path), Path(new_configs_path), persist=False)

            # Verify the request was sent without "persist" flag
            call_args = mock_socket.send.call_args[0][0]
            assert b"persist" not in call_args
            assert b'"threshold": 0.9' in call_args

    finally:
        # Clean up
        for path in [settings_path, new_configs_path]:
            if os.path.exists(path):
                os.unlink(path)


# Integration test for persist functionality
def test_reconfigure_command_with_persist_integration(temp_config_file, temp_params_file):
    """Integration test for reconfigure command with persist flag."""
    # Update the config file to point to the params file
    with open(temp_config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    config_data['config_file'] = temp_params_file
    with open(temp_config_file, 'w') as f:
        yaml.dump(config_data, f)

    settings = ServiceSettings.from_yaml(temp_config_file)

    # Use context manager to ensure proper cleanup
    with MockService(settings=settings) as service:
        # Test reconfigure with persist
        new_configs = {'threshold': 0.8, 'enabled': True}
        cmd = f'reconfigure persist {json.dumps(new_configs)}'
        result = service._handle_cmd(cmd)

        assert result == "reconfigure: ok"

        # configs should be updated in memory
        assert service.config_manager.get().threshold == 0.8
        assert service.config_manager.get().enabled is True

        # File should be updated (with persist)
        with open(temp_params_file, 'r') as f:
            file_content = yaml.safe_load(f)
        assert file_content == new_configs
