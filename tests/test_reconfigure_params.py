import pytest
import tempfile
import yaml
import json
from pathlib import Path
from service.core import Service
from service.settings import ServiceSettings
from service.features.parameters import BaseParameters
from service.features.parameter_manager import ParameterManager
from pydantic import Field


# Test parameters schema
class MockParameters(BaseParameters):
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    enabled: bool = Field(default=True)


# Test service that uses our test parameters
class MockService(Service):
    def get_parameters_schema(self):
        return MockParameters


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_data = {
            'parameter_file': str(Path(f.name).with_suffix('.params.yaml')),
            'engine_autostart': False
        }
        yaml.dump(config_data, f)
        yield f.name


@pytest.fixture
def temp_params_file():
    """Create a temporary parameters file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.params.yaml', delete=False) as f:
        params_data = {
            'threshold': 0.7,
            'enabled': False
        }
        yaml.dump(params_data, f)
        yield f.name


def test_reconfigure_command_valid(temp_config_file, temp_params_file):
    """Test reconfigure command with valid parameters."""
    # Update the config file to point to the params file
    with open(temp_config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    config_data['parameter_file'] = temp_params_file
    with open(temp_config_file, 'w') as f:
        yaml.dump(config_data, f)

    settings = ServiceSettings.from_yaml(temp_config_file)

    # Use context manager to ensure proper cleanup
    with MockService(settings=settings) as service:
        # Test valid reconfigure
        new_params = {'threshold': 0.8, 'enabled': True}
        cmd = f'reconfigure {json.dumps(new_params)}'
        result = service._handle_cmd(cmd)

        assert result == "reconfigure: ok"
        assert service.param_manager.get().threshold == 0.8
        assert service.param_manager.get().enabled is True


def test_reconfigure_command_invalid_json(temp_config_file, temp_params_file):
    """Test reconfigure command with invalid JSON."""
    # Update the config file to point to the params file
    with open(temp_config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    config_data['parameter_file'] = temp_params_file
    with open(temp_config_file, 'w') as f:
        yaml.dump(config_data, f)

    settings = ServiceSettings.from_yaml(temp_config_file)

    with MockService(settings=settings) as service:
        # Test invalid JSON
        result = service._handle_cmd('reconfigure invalid{json')
        assert "invalid JSON" in result


def test_reconfigure_command_validation_error(temp_config_file, temp_params_file):
    """Test reconfigure command with invalid parameter values."""
    # Update the config file to point to the params file
    with open(temp_config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    config_data['parameter_file'] = temp_params_file
    with open(temp_config_file, 'w') as f:
        yaml.dump(config_data, f)

    settings = ServiceSettings.from_yaml(temp_config_file)

    with MockService(settings=settings) as service:
        # Test invalid parameter value (threshold out of range)
        invalid_params = {'threshold': 2.0, 'enabled': True}
        cmd = f'reconfigure {json.dumps(invalid_params)}'
        result = service._handle_cmd(cmd)

        assert "error" in result.lower()
        # Should preserve original values
        assert service.param_manager.get().threshold == 0.7


def test_reconfigure_command_no_param_manager():
    """Test reconfigure command when no parameter manager is configured."""
    settings = ServiceSettings(engine_autostart=False)  # No parameter file

    with Service(settings=settings) as service:
        result = service._handle_cmd('reconfigure {"threshold": 0.8}')
        assert "no parameter manager" in result


def test_reconfigure_command_no_payload(temp_config_file, temp_params_file):
    """Test reconfigure command with no payload."""
    # Update the config file to point to the params file
    with open(temp_config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    config_data['parameter_file'] = temp_params_file
    with open(temp_config_file, 'w') as f:
        yaml.dump(config_data, f)

    settings = ServiceSettings.from_yaml(temp_config_file)

    with MockService(settings=settings) as service:
        result = service._handle_cmd('reconfigure')
        assert "no payload" in result


def test_reconfigure_persists_to_file(temp_config_file, temp_params_file):
    """Test that reconfigure persists changes to the parameter file."""
    # Update the config file to point to the params file
    with open(temp_config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    config_data['parameter_file'] = temp_params_file
    with open(temp_config_file, 'w') as f:
        yaml.dump(config_data, f)

    settings = ServiceSettings.from_yaml(temp_config_file)

    with MockService(settings=settings) as service:
        # Modify parameters
        new_params = {'threshold': 0.9, 'enabled': False}
        cmd = f'reconfigure {json.dumps(new_params)}'
        service._handle_cmd(cmd)

    # Reload from file to verify persistence
    new_manager = ParameterManager(temp_params_file, MockParameters)
    params = new_manager.get()

    assert params.threshold == 0.9
    assert params.enabled is False
