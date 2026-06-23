import logging
import sys
import yaml
import pytest
from unittest.mock import MagicMock, patch

from service.cli import main
from service.settings import ServiceSettings


@pytest.fixture(autouse=True)
def reset_root_logger():
    """Restore root logger handlers after each test.

    main() calls setup_logging() which unconditionally appends handlers;
    without cleanup they accumulate across tests in this session.
    """
    original_handlers = logging.root.handlers[:]
    original_level = logging.root.level
    yield
    logging.root.handlers = original_handlers
    logging.root.setLevel(original_level)


@pytest.fixture
def settings_yaml(tmp_path):
    """Write a minimal settings YAML and return its path."""
    data = {
        "component_type": "core",
        "engine_addr": f"ipc://{tmp_path}/test.ipc",
        "log_to_file": False,
        "engine_autostart": True,
    }
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.dump(data))
    return path


def run_main(argv: list[str]) -> ServiceSettings:
    """Run main() with the given argv and return the ServiceSettings that
    Service was instantiated with."""
    mock_service = MagicMock()
    mock_service.return_value.__enter__ = MagicMock(return_value=mock_service.return_value)
    mock_service.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(sys, "argv", argv), patch("service.cli.Service", mock_service):
        main()

    assert mock_service.called, "Service() was never instantiated — main() exited early"
    args, kwargs = mock_service.call_args
    return args[0] if args else kwargs["settings"]


def test_no_autostart_flag_overrides_yaml(settings_yaml):
    """--no-autostart sets engine_autostart=False even when YAML says True."""
    settings = run_main(["detectmate-service", "--settings", str(settings_yaml), "--no-autostart"])
    assert settings.engine_autostart is False


def test_without_no_autostart_yaml_value_is_kept(settings_yaml):
    """Without --no-autostart the YAML value (True) is preserved."""
    settings = run_main(["detectmate-service", "--settings", str(settings_yaml)])
    assert settings.engine_autostart is True


def test_no_autostart_uses_model_copy_not_mutation(settings_yaml):
    """--no-autostart creates a new settings object via model_copy, not direct mutation."""
    original = ServiceSettings.from_yaml(settings_yaml)

    with patch("service.cli.ServiceSettings.from_yaml", return_value=original):
        settings = run_main(["detectmate-service", "--settings", str(settings_yaml), "--no-autostart"])

    assert settings is not original, "model_copy must produce a new object, not mutate in place"
    assert original.engine_autostart is True, "original settings must not be mutated"
    assert settings.engine_autostart is False


def test_config_flag_sets_config_file(settings_yaml, tmp_path):
    """--config sets config_file on the settings passed to Service."""
    config_file = tmp_path / "component.yaml"
    config_file.write_text("{}")

    settings = run_main([
        "detectmate-service",
        "--settings", str(settings_yaml),
        "--config", str(config_file),
    ])
    assert settings.config_file == config_file


def test_no_autostart_and_config_combined(settings_yaml, tmp_path):
    """Both --no-autostart and --config apply in the same model_copy call."""
    config_file = tmp_path / "component.yaml"
    config_file.write_text("{}")

    settings = run_main([
        "detectmate-service",
        "--settings", str(settings_yaml),
        "--no-autostart",
        "--config", str(config_file),
    ])
    assert settings.engine_autostart is False
    assert settings.config_file == config_file


def test_missing_settings_exits(tmp_path):
    """Pointing --settings at a non-existent file causes sys.exit(1)."""
    with patch.object(sys, "argv", ["detectmate-service", "--settings", str(tmp_path / "missing.yaml")]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1
