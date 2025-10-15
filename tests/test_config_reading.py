import yaml
import tempfile
import os
from pathlib import Path
from service.settings import ServiceSettings


def test_read_config_from_yaml():
    """Test that ServiceSettings can be loaded from a YAML file."""
    config_data = {
        'component_name': 'test_detector',
        'component_type': 'detector',
        'manager_addr': 'ipc:///tmp/test_cmd.ipc',
        'engine_addr': 'ipc:///tmp/test_engine.ipc',
        'log_level': 'DEBUG',
        'log_dir': './test_logs',
        'log_to_console': True,
        'log_to_file': False,
        'engine_autostart': False
    }

    # Create a temporary YAML config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_file_path = f.name

    try:
        # Load settings from the YAML file
        settings = ServiceSettings.from_yaml(temp_file_path)

        # Verify that the settings were loaded correctly
        assert settings.component_name == 'test_detector'
        assert settings.component_type == 'detector'
        assert settings.manager_addr == 'ipc:///tmp/test_cmd.ipc'
        assert settings.engine_addr == 'ipc:///tmp/test_engine.ipc'
        assert settings.log_level == 'DEBUG'
        assert settings.log_dir == Path('./test_logs')
        assert settings.log_to_console is True
        assert settings.log_to_file is False
        assert settings.engine_autostart is False

        # Verify that component_id was generated
        assert settings.component_id is not None
        assert len(settings.component_id) == 32  # UUID as hex string

    finally:
        # Clean up the temporary file
        os.unlink(temp_file_path)


def test_read_partial_config_from_yaml():
    """Test that ServiceSettings can handle partial YAML configs."""
    config_data = {
        'component_name': 'partial_detector',
        'log_level': 'WARNING'
    }

    # Create a temporary YAML config file with only some fields
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_file_path = f.name

    try:
        # Load settings from the YAML file
        settings = ServiceSettings.from_yaml(temp_file_path)

        # Verify that the provided settings were loaded
        assert settings.component_name == 'partial_detector'
        assert settings.log_level == 'WARNING'

        # Verify that defaults are used for missing values
        assert settings.component_type == 'core'  # default value
        assert settings.manager_addr == 'ipc:///tmp/detectmate.cmd.ipc'  # default value
        assert settings.engine_addr == 'ipc:///tmp/detectmate.engine.ipc'  # default value

        # Verify that component_id was generated
        assert settings.component_id is not None

    finally:
        # Clean up the temporary file
        os.unlink(temp_file_path)


def test_read_empty_config_from_yaml():
    """Test that ServiceSettings handles empty YAML files."""
    # Create a temporary empty YAML file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write('')  # Empty file
        temp_file_path = f.name

    try:
        # Load settings from the empty YAML file
        settings = ServiceSettings.from_yaml(temp_file_path)

        # Verify that all defaults are used
        assert settings.component_name is None
        assert settings.component_type == 'core'
        assert settings.manager_addr == 'ipc:///tmp/detectmate.cmd.ipc'
        assert settings.engine_addr == 'ipc:///tmp/detectmate.engine.ipc'
        assert settings.log_level == 'INFO'

        # Verify that component_id was generated
        assert settings.component_id is not None

    finally:
        # Clean up the temporary file
        os.unlink(temp_file_path)


def test_read_nonexistent_config_file():
    """Test that ServiceSettings handles nonexistent config files
    gracefully."""
    # Try to load from a nonexistent file
    settings = ServiceSettings.from_yaml('/nonexistent/path/config.yaml')

    # Should use all defaults
    assert settings.component_name is None
    assert settings.component_type == 'core'
    assert settings.manager_addr == 'ipc:///tmp/detectmate.cmd.ipc'
    assert settings.engine_addr == 'ipc:///tmp/detectmate.engine.ipc'
    assert settings.log_level == 'INFO'

    # Verify that component_id was generated
    assert settings.component_id is not None


def test_env_vars_override_yaml(tmpdir, monkeypatch):
    """Test that environment variables override YAML config values."""
    # Create a temporary YAML config file
    config_data = {
        'component_name': 'yaml_detector',
        'log_level': 'DEBUG',
        'manager_addr': 'ipc:///tmp/yaml_cmd.ipc'
    }
    config_file = tmpdir.join('config.yaml')
    with open(config_file, 'w') as f:
        yaml.dump(config_data, f)

    # Set environment variables that should override the YAML values
    monkeypatch.setenv('DETECTMATE_COMPONENT_NAME', 'env_detector')
    monkeypatch.setenv('DETECTMATE_LOG_LEVEL', 'ERROR')

    # Load settings -> env vars should override yaml
    settings = ServiceSettings.from_yaml(str(config_file))

    # Environment variables should take precedence
    assert settings.component_name == 'env_detector'
    assert settings.log_level == 'ERROR'

    # YAML values without environment overrides should remain
    assert settings.manager_addr == 'ipc:///tmp/yaml_cmd.ipc'

    # Verify that component_id was generated
    assert settings.component_id is not None
